"""
ComfyUI 显存管理节点 - 改进版
支持智能显存预留、自动清理、多GPU管理
"""

from typing import Any, Tuple, Optional, Union, Dict
import logging
import threading
import atexit
import gc
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
DEFAULT_RESERVED_GB = 1.0
MIN_SAFE_RESERVE_GB = 2.0
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
            logger.warning("未安装pynvml库，GPU监控功能不可用。安装命令: pip install pynvml")
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
    
    @staticmethod
    def clear_all_caches() -> None:
        """清理所有可能的缓存"""
        try:
            # PyTorch缓存
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    with torch.cuda.device(i):
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
            
            # ComfyUI缓存
            if hasattr(model_management, 'cleanup_models'):
                model_management.cleanup_models()
            
            # Python垃圾回收
            gc.collect()
            
            logger.info("所有缓存已清理")
        except Exception as e:
            logger.error(f"清理所有缓存时出错: {e}")

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
                "anything": (AlwaysEqualProxy("*"), {
                    "tooltip": "通用输入，用于连接工作流数据"
                }),
                "reserved": ("FLOAT", {
                    "default": DEFAULT_RESERVED_GB,
                    "min": MIN_RESERVED_GB,
                    "max": 32.0,
                    "step": 0.1,
                    "display": "slider",
                    "tooltip": "预留显存大小(GB)\n• 手动模式: 固定预留\n• 自动模式: 额外缓冲\n• 智能模式: 动态优化"
                }),
                "mode": (["smart", "auto", "manual"], {
                    "default": "smart",
                    "tooltip": (
                        "模式选择:\n"
                        "• smart(推荐): 根据显存状态智能调整\n"
                        "• auto: 当前使用量 + 预留缓冲\n"
                        "• manual: 固定预留值"
                    )
                }),
                "gpu_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 7,
                    "step": 1,
                    "tooltip": "GPU设备索引 (0-7)"
                }),
                "min_safe_reserve": ("FLOAT", {
                    "default": MIN_SAFE_RESERVE_GB,
                    "min": 0.5,
                    "max": 8.0,
                    "step": 0.5,
                    "display": "slider",
                    "tooltip": "最小安全保留显存(GB)，确保系统稳定"
                }),
                "clear_memory": ("BOOLEAN", {
                    "default": False,
                    "label_on": "✓ 清理显存",
                    "label_off": "✗ 不清理",
                    "tooltip": "执行前清理GPU显存缓存"
                }),
                "show_gpu_info": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✓ 显示信息",
                    "label_off": "✗ 隐藏信息",
                    "tooltip": "显示详细的GPU状态信息"
                })
            },
            "hidden": {
                "unique_id": "UNIQUE_ID", 
                "extra_pnginfo": "EXTRA_PNGINFO"
            }
        }

    RETURN_TYPES = (AlwaysEqualProxy("*"),)
    RETURN_NAMES = ("output",)
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
        anything: Any, 
        reserved: float, 
        mode: str = "smart",
        gpu_index: int = 0,
        min_safe_reserve: float = MIN_SAFE_RESERVE_GB,
        clear_memory: bool = False,
        show_gpu_info: bool = True,
        unique_id: Optional[str] = None, 
        extra_pnginfo: Optional[Any] = None
    ) -> Tuple[Any]:
        """设置预留显存
        
        Args:
            anything: 通用输入数据
            reserved: 预留显存大小(GB)
            mode: 模式选择 (smart/auto/manual)
            gpu_index: GPU设备索引
            min_safe_reserve: 最小安全保留显存
            clear_memory: 是否清理显存
            show_gpu_info: 是否显示GPU信息
            unique_id: 节点唯一ID
            extra_pnginfo: 额外PNG信息
            
        Returns:
            输入数据的元组
        """
        try:
            # 验证GPU索引
            if not self.gpu_manager.validate_gpu_index(gpu_index):
                logger.error(f"GPU索引 {gpu_index} 无效，使用GPU 0")
                gpu_index = 0
            
            # 显示GPU信息
            if show_gpu_info:
                self._show_gpu_info(gpu_index)
            
            # 清理显存（如果需要）
            if clear_memory:
                clean_result = self.memory_cleaner.clear_gpu_memory(gpu_index)
                if clean_result["success"] and clean_result["freed_memory_gb"] > 0:
                    logger.info(
                        f"✓ 显存清理成功: 释放 {clean_result['freed_memory_gb']:.2f}GB "
                        f"({clean_result['freed_memory_mb']:.0f}MB)"
                    )
            
            # 计算预留显存
            reserved_bytes, detail = self.calculator.calculate_reserved_memory(
                reserved, mode, gpu_index, min_safe_reserve, self.gpu_manager
            )
            
            # 设置预留显存
            model_management.EXTRA_RESERVED_MEMORY = reserved_bytes
            
            # 输出设置信息
            reserved_gb = reserved_bytes / GB_TO_BYTES
            logger.info(f"✓ {detail}")
            logger.info(f"已设置预留显存: {reserved_gb:.2f}GB ({reserved_bytes / MB_TO_BYTES:.0f}MB)")
            
        except Exception as e:
            # 出错时使用安全的默认值
            safe_default = max(DEFAULT_RESERVED_GB, min_safe_reserve)
            model_management.EXTRA_RESERVED_MEMORY = int(safe_default * GB_TO_BYTES)
            logger.error(f"设置预留显存时出错: {e}，使用安全默认值 {safe_default:.2f}GB")

        return (anything,)
    
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
# 显存监控节点 (额外功能)
# ============================================================================

class GPUMemoryMonitor:
    """GPU显存监控节点 - 仅用于查看信息，不影响工作流"""
    
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "gpu_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 7,
                    "step": 1,
                    "tooltip": "要监控的GPU索引"
                }),
                "refresh": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✓ 刷新",
                    "label_off": "✗ 暂停",
                    "tooltip": "是否实时刷新GPU信息"
                })
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("gpu_info",)
    OUTPUT_NODE = True
    FUNCTION = "monitor"
    CATEGORY = "ARES/显存管理"
    DESCRIPTION = "实时监控GPU显存和状态信息"
    
    def __init__(self):
        self.gpu_manager = GPUManager()
    
    def monitor(self, gpu_index: int = 0, refresh: bool = True) -> Tuple[str]:
        """监控GPU状态"""
        if not refresh:
            return ("监控已暂停",)
        
        info = self.gpu_manager.get_detailed_info(gpu_index)
        
        if not info["available"]:
            return (f"GPU {gpu_index} 不可用",)
        
        # 构建详细信息
        lines = [
            f"=== GPU {gpu_index} 状态 ===",
            f"型号: {info['name'] or '未知'}",
        ]
        
        if info["memory"]:
            total_gb, used_gb, free_gb = info["memory"]
            usage_percent = (used_gb / total_gb) * 100
            lines.extend([
                f"总显存: {total_gb:.2f} GB",
                f"已使用: {used_gb:.2f} GB ({usage_percent:.1f}%)",
                f"可用: {free_gb:.2f} GB",
            ])
        
        if info["temperature"] is not None:
            lines.append(f"温度: {info['temperature']}°C")
        
        if info["utilization"] is not None:
            lines.append(f"GPU利用率: {info['utilization']}%")
        
        info_text = "\n".join(lines)
        logger.info(f"\n{info_text}")
        
        return (info_text,)

# ============================================================================
# 批量清理节点
# ============================================================================

class BatchMemoryCleaner:
    """批量显存清理节点"""
    
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "anything": (AlwaysEqualProxy("*"), {
                    "tooltip": "通用输入，用于连接工作流"
                }),
                "clear_all_gpus": ("BOOLEAN", {
                    "default": False,
                    "label_on": "✓ 清理所有GPU",
                    "label_off": "✗ 仅当前GPU",
                    "tooltip": "是否清理所有GPU的显存"
                }),
                "aggressive": ("BOOLEAN", {
                    "default": False,
                    "label_on": "✓ 深度清理",
                    "label_off": "✗ 常规清理",
                    "tooltip": "深度清理模式会额外清理ComfyUI模型缓存"
                })
            }
        }
    
    RETURN_TYPES = (AlwaysEqualProxy("*"), "STRING")
    RETURN_NAMES = ("output", "清理报告")
    OUTPUT_NODE = True
    FUNCTION = "clean"
    CATEGORY = "ARES/显存管理"
    DESCRIPTION = "批量清理GPU显存缓存"
    
    def __init__(self):
        self.memory_cleaner = MemoryCleaner()
    
    def clean(
        self,
        anything: Any,
        clear_all_gpus: bool = False,
        aggressive: bool = False
    ) -> Tuple[Any, str]:
        """执行清理操作"""
        report_lines = ["=== 显存清理报告 ==="]
        
        try:
            if clear_all_gpus:
                # 清理所有GPU
                gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
                total_freed = 0.0
                
                for i in range(gpu_count):
                    result = self.memory_cleaner.clear_gpu_memory(i)
                    if result["success"]:
                        freed = result["freed_memory_gb"]
                        total_freed += freed
                        report_lines.append(f"GPU {i}: 释放 {freed:.2f}GB")
                
                report_lines.append(f"总计释放: {total_freed:.2f}GB")
            else:
                # 仅清理当前GPU
                result = self.memory_cleaner.clear_gpu_memory(0)
                if result["success"]:
                    freed = result["freed_memory_gb"]
                    report_lines.append(f"释放显存: {freed:.2f}GB")
            
            # 深度清理
            if aggressive:
                self.memory_cleaner.clear_all_caches()
                report_lines.append("已执行深度清理")
            
            report_lines.append("✓ 清理完成")
            logger.info("\n".join(report_lines))
            
        except Exception as e:
            error_msg = f"清理失败: {e}"
            report_lines.append(f"✗ {error_msg}")
            logger.error(error_msg)
        
        report = "\n".join(report_lines)
        return (anything, report)

# ============================================================================
# 节点注册
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "ReservedMemorySetter": ReservedMemorySetter,
    "GPUMemoryMonitor": GPUMemoryMonitor,
    "BatchMemoryCleaner": BatchMemoryCleaner
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ReservedMemorySetter": "🎛️ 智能显存预留",
    "GPUMemoryMonitor": "📊 GPU显存监控",
    "BatchMemoryCleaner": "🧹 批量显存清理"
}

# ============================================================================
# 清理函数
# ============================================================================

def cleanup():
    """程序退出时清理资源"""
    try:
        gpu_manager = GPUManager()
        gpu_manager.cleanup()
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")

# 注册退出清理函数
atexit.register(cleanup)

# ============================================================================
# 模块信息
# ============================================================================

__version__ = "2.0.0"
__author__ = "ARES"
__description__ = "ComfyUI GPU显存智能管理节点集"
