"""
ComfyUI 显存管理节点 - 改进版
支持智能显存预留、自动清理、多GPU管理
"""

from typing import Any, Tuple, Optional, Union, Dict
import logging
import threading
import atexit
import gc
import subprocess
import sys
import time
import torch
from comfy import model_management

# ============================================================================
# 日志配置
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("GPUMemoryManager")

# ============================================================================
# 常量定义
# ============================================================================

GB_TO_BYTES = 1024 * 1024 * 1024
MB_TO_BYTES = 1024 * 1024
MIN_RESERVED_GB = 0.6
DEFAULT_RESERVED_GB = 4.0
MIN_SAFE_RESERVE_GB = 4.0
MAX_RESERVED_RATIO = 0.9  # 最大预留比例

# 显存使用策略
MEMORY_STRATEGY = {
    "tight": 0.8,    # 紧张：可用<20%
    "medium": 0.85,  # 中等：可用20-40%
    "loose": 0.9     # 充足：可用>40%
}

# ============================================================================
# GPU管理类 (线程安全单例)
# ============================================================================

class GPUManager:
    """GPU管理类，封装pynvml相关操作 - 线程安全单例"""
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(GPUManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if not GPUManager._initialized:
            with GPUManager._lock:
                if not GPUManager._initialized:
                    self.pynvml = None
                    self._pynvml_available = False
                    self._initialize_pynvml()
                    GPUManager._initialized = True
    
    def _initialize_pynvml(self) -> None:
        """初始化pynvml"""
        try:
            import pynvml
            self.pynvml = pynvml
            pynvml.nvmlInit()
            self._pynvml_available = True
            logger.info("GPU监控已初始化 (pynvml)")
        except ImportError:
            self._pynvml_available = False
            logger.warning("未安装nvidia-ml-py库（提供pynvml模块），GPU监控功能不可用。安装命令: pip install nvidia-ml-py")
        except Exception as e:
            self._pynvml_available = False
            logger.error(f"初始化pynvml失败: {e}")
    
    def is_available(self) -> bool:
        """检查GPU监控是否可用"""
        return self._pynvml_available
    
    def get_gpu_count(self) -> int:
        """获取GPU数量"""
        if not self._pynvml_available:
            return torch.cuda.device_count() if torch.cuda.is_available() else 0
        
        try:
            return self.pynvml.nvmlDeviceGetCount()
        except Exception as e:
            logger.error(f"获取GPU数量失败: {e}")
            return 0
    
    def validate_gpu_index(self, gpu_index: int) -> bool:
        """验证GPU索引是否有效"""
        gpu_count = self.get_gpu_count()
        if gpu_index < 0 or gpu_index >= gpu_count:
            logger.warning(f"无效的GPU索引: {gpu_index}，可用范围: 0-{gpu_count-1}")
            return False
        return True
    
    def get_gpu_memory_info(self, gpu_index: int = 0) -> Optional[Tuple[float, float, float]]:
        """获取GPU显存信息
        
        Args:
            gpu_index: GPU索引，默认为0
            
        Returns:
            (总显存GB, 已用显存GB, 可用显存GB) 或 None
        """
        if not self._pynvml_available:
            return None
        
        if not self.validate_gpu_index(gpu_index):
            return None
            
        try:
            handle = self.pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            memory_info = self.pynvml.nvmlDeviceGetMemoryInfo(handle)
            
            total_gb = memory_info.total / GB_TO_BYTES
            used_gb = memory_info.used / GB_TO_BYTES
            free_gb = memory_info.free / GB_TO_BYTES
            
            return total_gb, used_gb, free_gb
        except Exception as e:
            logger.error(f"获取GPU{gpu_index}信息时出错: {e}")
            return None
    
    def get_gpu_name(self, gpu_index: int = 0) -> Optional[str]:
        """获取GPU名称"""
        if not self._pynvml_available:
            return None
        
        try:
            handle = self.pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            name = self.pynvml.nvmlDeviceGetName(handle)
            return name.decode('utf-8') if isinstance(name, bytes) else name
        except Exception as e:
            logger.error(f"获取GPU{gpu_index}名称失败: {e}")
            return None
    
    def get_gpu_temperature(self, gpu_index: int = 0) -> Optional[int]:
        """获取GPU温度"""
        if not self._pynvml_available:
            return None
        
        try:
            handle = self.pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            temp = self.pynvml.nvmlDeviceGetTemperature(
                handle, 
                self.pynvml.NVML_TEMPERATURE_GPU
            )
            return temp
        except Exception as e:
            logger.debug(f"获取GPU{gpu_index}温度失败: {e}")
            return None
    
    def get_gpu_utilization(self, gpu_index: int = 0) -> Optional[int]:
        """获取GPU利用率"""
        if not self._pynvml_available:
            return None
        
        try:
            handle = self.pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            utilization = self.pynvml.nvmlDeviceGetUtilizationRates(handle)
            return utilization.gpu
        except Exception as e:
            logger.debug(f"获取GPU{gpu_index}利用率失败: {e}")
            return None
    
    def get_detailed_info(self, gpu_index: int = 0) -> Dict[str, Any]:
        """获取GPU详细信息"""
        info = {
            "index": gpu_index,
            "available": False,
            "name": None,
            "memory": None,
            "temperature": None,
            "utilization": None
        }
        
        if not self.validate_gpu_index(gpu_index):
            return info
        
        info["available"] = True
        info["name"] = self.get_gpu_name(gpu_index)
        info["memory"] = self.get_gpu_memory_info(gpu_index)
        info["temperature"] = self.get_gpu_temperature(gpu_index)
        info["utilization"] = self.get_gpu_utilization(gpu_index)
        
        return info
    
    def cleanup(self) -> None:
        """清理资源"""
        if self._pynvml_available and self.pynvml:
            try:
                self.pynvml.nvmlShutdown()
                logger.info("GPU监控已关闭")
            except Exception as e:
                logger.error(f"关闭GPU监控时出错: {e}")

# ============================================================================
# 内存清理类
# ============================================================================

class MemoryCleaner:
    """内存清理器 - 线程安全"""
    
    _lock = threading.Lock()
    
    @staticmethod
    def clear_gpu_memory(gpu_index: int = 0) -> Dict[str, Any]:
        """清理GPU内存 - 线程安全
        
        Args:
            gpu_index: GPU索引
            
        Returns:
            清理结果信息
        """
        with MemoryCleaner._lock:
            result = {
                "success": False,
                "torch_cuda": False,
                "gc_collected": 0,
                "before_memory": None,
                "after_memory": None,
                "freed_memory_gb": 0.0,
                "freed_memory_mb": 0.0
            }
            
            gpu_manager = GPUManager()
            
            # 获取清理前内存
            result["before_memory"] = gpu_manager.get_gpu_memory_info(gpu_index)
            
            try:
                # 清理PyTorch CUDA缓存
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    result["torch_cuda"] = True
                    logger.info("PyTorch CUDA缓存已清理")
                
                # 执行垃圾回收
                collected = gc.collect()
                result["gc_collected"] = collected
                logger.info(f"垃圾回收完成，回收对象数: {collected}")
                
                # 获取清理后内存
                result["after_memory"] = gpu_manager.get_gpu_memory_info(gpu_index)
                
                # 计算释放的内存
                if result["before_memory"] and result["after_memory"]:
                    _, used_before, _ = result["before_memory"]
                    _, used_after, _ = result["after_memory"]
                    freed_gb = used_before - used_after
                    freed_mb = freed_gb * 1024
                    
                    result["freed_memory_gb"] = freed_gb
                    result["freed_memory_mb"] = freed_mb
                    result["success"] = True
                    
                    if freed_gb > 0:
                        logger.info(f"显存清理成功: 释放了 {freed_gb:.2f}GB ({freed_mb:.0f}MB)")
                    else:
                        logger.info("显存清理完成，未释放额外显存")
                else:
                    result["success"] = True
                    logger.info("显存清理完成")
                    
            except Exception as e:
                logger.error(f"清理显存时出错: {e}")
                result["success"] = False
            
            return result

# ============================================================================
# 占位显存管理器
# ============================================================================

class VRAMOccupier:
    """占位显存管理器 - 独立进程真占显存，支持延时占用、到时自动释放"""

    _process = None
    _thread = None
    _cancel = None
    _lock = threading.RLock()

    @classmethod
    def schedule(cls, size_gb: float, gpu_index: int, delay: float, hold: float) -> None:
        """安排一次占位：延时 delay 秒后占用 size_gb，保持 hold 秒后自动释放"""
        with cls._lock:
            cls.cancel()
            cls._cancel = threading.Event()
            cancel = cls._cancel
            cls._thread = threading.Thread(
                target=cls._run, args=(size_gb, gpu_index, delay, hold, cancel), daemon=True
            )
            cls._thread.start()

    @classmethod
    def _run(cls, size_gb: float, gpu_index: int, delay: float, hold: float, cancel) -> None:
        if delay > 0 and cancel.wait(delay):
            return
        if not cls.occupy(size_gb, gpu_index):
            return
        if cancel.wait(hold):
            cls.release()
        else:
            cls.release()

    @classmethod
    def occupy(cls, size_gb: float, gpu_index: int) -> bool:
        """启动独立进程占用 size_gb 显存"""
        with cls._lock:
            cls.release()
            try:
                code = (
                    "import torch, time\n"
                    f"size_gb = {size_gb}\n"
                    f"gpu_index = {gpu_index}\n"
                    "elements = int(size_gb * (1024 ** 3) / 4)\n"
                    "torch.zeros(elements, device=f'cuda:{gpu_index}')\n"
                    "print('occupied', size_gb, 'GB on GPU', gpu_index)\n"
                    "time.sleep(3600)\n"
                )
                cls._process = subprocess.Popen(
                    [sys.executable, "-u", "-c", code],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                time.sleep(1.5)
                if cls._process.poll() is not None:
                    cls._process = None
                    logger.error("占位显存进程提前退出（显存可能不足），占位失败")
                    return False
                return True
            except Exception as e:
                cls._process = None
                logger.error(f"启动占位显存进程失败: {e}")
                return False

    @classmethod
    def release(cls) -> None:
        """关闭占位显存进程，释放显存"""
        with cls._lock:
            if cls._process is not None:
                try:
                    cls._process.terminate()
                    cls._process.wait(timeout=5)
                except Exception:
                    pass
                cls._process = None

    @classmethod
    def cancel(cls) -> None:
        """取消已安排或正在进行的占位"""
        if cls._cancel is not None:
            cls._cancel.set()
        cls.release()

    @classmethod
    def is_scheduled(cls) -> bool:
        """是否已有安排的占位（等待中或已占用）"""
        return cls._thread is not None and cls._thread.is_alive()

    @classmethod
    def is_occupying(cls) -> bool:
        return cls._process is not None and cls._process.poll() is None

# ============================================================================
# 通用类型代理
# ============================================================================

class AlwaysEqualProxy(str):
    """始终相等的代理字符串，用于通用输入类型"""
    
    def __eq__(self, _) -> bool:
        return True

    def __ne__(self, _) -> bool:
        return False

# ============================================================================
# 显存策略计算器
# ============================================================================

class MemoryStrategyCalculator:
    """显存预留策略计算器"""
    
    @staticmethod
    def calculate_reserved_memory(
        reserved: float,
        mode: str,
        gpu_index: int,
        min_safe_reserve: float,
        gpu_manager: GPUManager
    ) -> Tuple[int, str]:
        """计算预留显存大小
        
        Args:
            reserved: 用户设置的预留值
            mode: 模式选择
            gpu_index: GPU索引
            min_safe_reserve: 最小安全保留显存
            gpu_manager: GPU管理器实例
            
        Returns:
            (预留显存字节数, 详细说明)
        """
        # 获取GPU信息
        memory_info = gpu_manager.get_gpu_memory_info(gpu_index)
        
        if mode == "manual":
            return MemoryStrategyCalculator._manual_mode(
                reserved, min_safe_reserve, memory_info
            )
        elif mode == "auto":
            return MemoryStrategyCalculator._auto_mode(
                reserved, min_safe_reserve, memory_info
            )
        elif mode == "smart":
            return MemoryStrategyCalculator._smart_mode(
                reserved, min_safe_reserve, memory_info
            )
        else:
            logger.warning(f"未知模式: {mode}，使用默认值")
            return int(max(reserved, min_safe_reserve) * GB_TO_BYTES), "默认模式"
    
    @staticmethod
    def _manual_mode(
        reserved: float,
        min_safe_reserve: float,
        memory_info: Optional[Tuple[float, float, float]]
    ) -> Tuple[int, str]:
        """手动模式"""
        # 确保不低于最小安全值
        manual_reserved = max(reserved, min_safe_reserve)
        
        if memory_info:
            total_gb, used_gb, free_gb = memory_info
            max_allowed = total_gb * MAX_RESERVED_RATIO
            
            if manual_reserved > max_allowed:
                safe_reserved = max_allowed
                detail = f"手动模式: {reserved:.2f}GB → {safe_reserved:.2f}GB (限制为总显存的{MAX_RESERVED_RATIO*100:.0f}%)"
                logger.warning(detail)
                return int(safe_reserved * GB_TO_BYTES), detail
            
            detail = f"手动模式: {manual_reserved:.2f}GB (总{total_gb:.2f}GB, 已用{used_gb:.2f}GB)"
            return int(manual_reserved * GB_TO_BYTES), detail
        else:
            detail = f"手动模式: {manual_reserved:.2f}GB (无GPU信息)"
            return int(manual_reserved * GB_TO_BYTES), detail
    
    @staticmethod
    def _auto_mode(
        reserved: float,
        min_safe_reserve: float,
        memory_info: Optional[Tuple[float, float, float]]
    ) -> Tuple[int, str]:
        """自动模式: 当前使用量 + 预留缓冲"""
        if memory_info is None:
            logger.warning("无法获取GPU信息，自动模式回退到手动模式")
            return MemoryStrategyCalculator._manual_mode(reserved, min_safe_reserve, None)
        
        total_gb, used_gb, free_gb = memory_info
        
        # 计算: 当前使用 + 缓冲
        auto_reserved = used_gb + reserved
        
        # 确保不低于最小安全值
        auto_reserved = max(auto_reserved, min_safe_reserve)
        
        # 确保不超过总显存的85%
        max_allowed = total_gb * 0.85
        safe_reserved = min(auto_reserved, max_allowed)
        
        if auto_reserved != safe_reserved:
            detail = f"自动模式: {auto_reserved:.2f}GB → {safe_reserved:.2f}GB (已用{used_gb:.2f}GB + 缓冲{reserved:.2f}GB, 限制为85%)"
        else:
            detail = f"自动模式: {safe_reserved:.2f}GB (已用{used_gb:.2f}GB + 缓冲{reserved:.2f}GB)"
        
        return int(safe_reserved * GB_TO_BYTES), detail
    
    @staticmethod
    def _smart_mode(
        reserved: float,
        min_safe_reserve: float,
        memory_info: Optional[Tuple[float, float, float]]
    ) -> Tuple[int, str]:
        """智能模式: 根据显存使用情况动态调整"""
        if memory_info is None:
            logger.warning("无法获取GPU信息，智能模式使用安全默认值")
            default_value = max(reserved + 1.0, min_safe_reserve)
            return int(default_value * GB_TO_BYTES), f"智能模式(无GPU信息): {default_value:.2f}GB"
        
        total_gb, used_gb, free_gb = memory_info
        
        # 计算可用显存比例
        available_ratio = free_gb / total_gb
        
        # 基础预留值
        base_reserved = used_gb + reserved
        
        # 根据可用显存比例选择策略
        if available_ratio < 0.2:  # 显存紧张
            strategy_ratio = MEMORY_STRATEGY["tight"]
            smart_reserved = max(base_reserved, total_gb * strategy_ratio)
            status = "紧张"
        elif available_ratio < 0.4:  # 显存中等
            strategy_ratio = MEMORY_STRATEGY["medium"]
            smart_reserved = base_reserved
            status = "中等"
        else:  # 显存充足
            strategy_ratio = MEMORY_STRATEGY["loose"]
            smart_reserved = max(base_reserved, min_safe_reserve)
            status = "充足"
        
        # 确保不低于最小安全值
        smart_reserved = max(smart_reserved, min_safe_reserve)
        
        # 确保不超过总显存的90%
        max_allowed = total_gb * MAX_RESERVED_RATIO
        safe_reserved = min(smart_reserved, max_allowed)
        
        detail = (
            f"智能模式: {safe_reserved:.2f}GB "
            f"(状态:{status}, 可用{free_gb:.2f}GB/{total_gb:.2f}GB={available_ratio*100:.1f}%)"
        )
        
        if smart_reserved != safe_reserved:
            detail += f" [调整: {smart_reserved:.2f}→{safe_reserved:.2f}]"
        
        return int(safe_reserved * GB_TO_BYTES), detail

# ============================================================================
# 主节点类
# ============================================================================

class ReservedMemorySetter:
    """预留显存设置节点 - 改进版"""
    
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "输入": (AlwaysEqualProxy("*"), {
                    "tooltip": "通用输入，用于连接工作流数据"
                }),
                "预留大小": ("FLOAT", {
                    "default": DEFAULT_RESERVED_GB,
                    "min": MIN_RESERVED_GB,
                    "max": 32.0,
                    "step": 0.1,
                    "tooltip": "预留显存大小(GB)\n• 手动模式: 固定预留\n• 自动模式: 额外缓冲\n• 智能模式: 动态优化"
                }),
                "模式": (["智能", "自动", "手动"], {
                    "default": "手动",
                    "tooltip": (
                        "模式选择:\n"
                        "• 智能(推荐): 根据显存状态智能调整\n"
                        "• 自动: 当前使用量 + 预留缓冲\n"
                        "• 手动: 固定预留值"
                    )
                }),
                "GPU索引": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 7,
                    "step": 1,
                    "tooltip": "GPU设备索引 (0-7)"
                }),
                "最小安全保留": ("FLOAT", {
                    "default": MIN_SAFE_RESERVE_GB,
                    "min": 0.5,
                    "max": 8.0,
                    "step": 0.5,
                    "tooltip": "最小安全保留显存(GB)，确保系统稳定"
                }),
                "执行前清理": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✓ 清理显存",
                    "label_off": "✗ 不清理",
                    "tooltip": "执行前清理GPU显存缓存"
                }),
                "显示GPU信息": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✓ 显示信息",
                    "label_off": "✗ 隐藏信息",
                    "tooltip": "显示详细的GPU状态信息"
                }),
                "占位显存": ("BOOLEAN", {
                    "default": False,
                    "label_on": "✓ 占用",
                    "label_off": "✗ 释放",
                    "tooltip": "启动独立进程真占显存，按下方延时/保持自动占用并释放，防止ComfyUI占满显存卡住"
                }),
                "占位显存量": ("FLOAT", {
                    "default": 1.0,
                    "min": 1.0,
                    "max": 4.0,
                    "step": 0.5,
                    "tooltip": "独立进程占用的显存(GB)，范围 1-4"
                }),
                "占位延时": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.0,
                    "max": 60.0,
                    "step": 1.0,
                    "tooltip": "占位启动延时(秒)：节点运行后等待多久再开始占用，0=立即"
                }),
                "占位保持": ("FLOAT", {
                    "default": 10.0,
                    "min": 1.0,
                    "max": 300.0,
                    "step": 5.0,
                    "tooltip": "占位保持时长(秒)：占用后保持多久自动释放，根据流的运行时间填写"
                })
            }
        }

    RETURN_TYPES = (AlwaysEqualProxy("*"),)
    RETURN_NAMES = ("输出",)
    OUTPUT_NODE = True
    FUNCTION = "set_memory"
    CATEGORY = "ARES/显存管理"
    DESCRIPTION = "智能管理GPU显存预留，支持三种模式和自动清理"
    
    def __init__(self):
        self.gpu_manager = GPUManager()
        self.memory_cleaner = MemoryCleaner()
        self.calculator = MemoryStrategyCalculator()
    
    def set_memory(
        self, 
        输入: Any, 
        预留大小: float, 
        模式: str = "智能",
        GPU索引: int = 0,
        最小安全保留: float = MIN_SAFE_RESERVE_GB,
        执行前清理: bool = False,
        显示GPU信息: bool = True,
        占位显存: bool = False,
        占位显存量: float = 2.0,
        占位延时: float = 0.0,
        占位保持: float = 30.0
    ) -> Tuple[Any]:
        """设置预留显存
        
        Args:
            输入: 通用输入数据
            预留大小: 预留显存大小(GB)
            模式: 模式选择 (智能/自动/手动)
            GPU索引: GPU设备索引
            最小安全保留: 最小安全保留显存
            执行前清理: 是否清理显存
            显示GPU信息: 是否显示GPU信息
            占位显存: 是否启动独立进程真占显存
            占位显存量: 独立进程占用的显存(GB)
            占位延时: 占位启动延时(秒)
            占位保持: 占位保持时长(秒)，到时自动释放
            
        Returns:
            输入数据的元组
        """
        try:
            mode = {"智能": "smart", "自动": "auto", "手动": "manual"}.get(模式, "smart")
            
            # 验证GPU索引
            if not self.gpu_manager.validate_gpu_index(GPU索引):
                logger.error(f"GPU索引 {GPU索引} 无效，使用GPU 0")
                GPU索引 = 0
            
            # 显示GPU信息
            if 显示GPU信息:
                self._show_gpu_info(GPU索引)
            
            # 清理显存（如果需要）
            if 执行前清理:
                clean_result = self.memory_cleaner.clear_gpu_memory(GPU索引)
                if clean_result["success"] and clean_result["freed_memory_gb"] > 0:
                    logger.info(
                        f"✓ 显存清理成功: 释放 {clean_result['freed_memory_gb']:.2f}GB "
                        f"({clean_result['freed_memory_mb']:.0f}MB)"
                    )
            
            # 计算预留显存
            reserved_bytes, detail = self.calculator.calculate_reserved_memory(
                预留大小, mode, GPU索引, 最小安全保留, self.gpu_manager
            )
            
            # 设置预留显存
            model_management.EXTRA_RESERVED_VRAM = reserved_bytes
            
            # 占位显存（独立进程真占显存，按延时/保持自动占用与释放）
            if 占位显存:
                VRAMOccupier.schedule(占位显存量, GPU索引, 占位延时, 占位保持)
                logger.info(
                    f"✓ 占位显存已安排: {占位延时:.0f}秒后占用 {占位显存量:.1f}GB (GPU{GPU索引}), "
                    f"保持 {占位保持:.0f}秒后自动释放"
                )
            else:
                if VRAMOccupier.is_scheduled():
                    VRAMOccupier.cancel()
                    logger.info("✓ 占位显存已取消/释放")
            
            # 输出设置信息
            reserved_gb = reserved_bytes / GB_TO_BYTES
            logger.info(f"✓ {detail}")
            logger.info(f"已设置预留显存: {reserved_gb:.2f}GB ({reserved_bytes / MB_TO_BYTES:.0f}MB)")
            
        except Exception as e:
            # 出错时使用安全的默认值
            safe_default = max(DEFAULT_RESERVED_GB, 最小安全保留)
            model_management.EXTRA_RESERVED_VRAM = int(safe_default * GB_TO_BYTES)
            logger.error(f"设置预留显存时出错: {e}，使用安全默认值 {safe_default:.2f}GB")

        return (输入,)
    
    def _show_gpu_info(self, gpu_index: int) -> None:
        """显示GPU详细信息"""
        info = self.gpu_manager.get_detailed_info(gpu_index)
        
        if not info["available"]:
            logger.warning(f"GPU {gpu_index} 不可用")
            return
        
        # 构建信息字符串
        info_parts = [f"GPU {gpu_index}"]
        
        if info["name"]:
            info_parts.append(f"型号: {info['name']}")
        
        if info["memory"]:
            total_gb, used_gb, free_gb = info["memory"]
            usage_percent = (used_gb / total_gb) * 100
            info_parts.append(
                f"显存: {used_gb:.2f}GB/{total_gb:.2f}GB "
                f"(使用率{usage_percent:.1f}%, 可用{free_gb:.2f}GB)"
            )
        
        if info["temperature"] is not None:
            info_parts.append(f"温度: {info['temperature']}°C")
        
        if info["utilization"] is not None:
            info_parts.append(f"利用率: {info['utilization']}%")
        
        logger.info(" | ".join(info_parts))

# ============================================================================
# 节点注册
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "ReservedMemorySetter": ReservedMemorySetter
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ReservedMemorySetter": "🎛️ 智能显存预留"
}

# ============================================================================
# 清理函数
# ============================================================================

def cleanup():
    """程序退出时清理资源"""
    try:
        VRAMOccupier.release()
        gpu_manager = GPUManager()
        gpu_manager.cleanup()
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")

# 注册退出清理函数
atexit.register(cleanup)

# ============================================================================
# 模块信息
# ============================================================================

__version__ = "2.2.0"
__author__ = "ARES"
__description__ = "ComfyUI GPU显存智能管理节点集"
