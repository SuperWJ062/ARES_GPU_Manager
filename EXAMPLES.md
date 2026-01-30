# 代码对比示例

## 场景：清理GPU显存并获取信息

### 原版实现

```python
# nodes.py (原版)

def clear_gpu_memory() -> dict:
    """清理GPU内存"""
    result = {
        "torch_cuda": False,
        "gc_collected": 0,
        "before_memory": None,
        "after_memory": None
    }
    
    gpu_manager = GPUManager()
    result["before_memory"] = gpu_manager.get_gpu_memory_info(0)
    
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            result["torch_cuda"] = True
        
        collected = gc.collect()
        result["gc_collected"] = collected
        
        result["after_memory"] = gpu_manager.get_gpu_memory_info(0)
        
        if result["before_memory"] and result["after_memory"]:
            total_before, used_before = result["before_memory"]
            total_after, used_after = result["after_memory"]
            freed_memory = used_before - used_after
            print(f"显存清理完成: 释放了 {freed_memory:.2f}GB 显存")
        else:
            print("显存清理完成")
            
    except Exception as e:
        print(f"清理显存时出错: {e}")
    
    return result
```

**输出：**
```
显存清理完成: 释放了 1.25GB 显存
```

---

### 改进版实现

```python
# nodes.py (改进版 v2.0)

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
        with MemoryCleaner._lock:  # 线程安全
            result = {
                "success": False,
                "torch_cuda": False,
                "gc_collected": 0,
                "before_memory": None,
                "after_memory": None,
                "freed_memory_gb": 0.0,
                "freed_memory_mb": 0.0  # 新增MB单位
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
                    logger.info("PyTorch CUDA缓存已清理")  # 使用logger
                
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
```

**输出：**
```
[2025-01-30 10:30:15] [GPUMemoryManager] [INFO] PyTorch CUDA缓存已清理
[2025-01-30 10:30:15] [GPUMemoryManager] [INFO] 垃圾回收完成，回收对象数: 42
[2025-01-30 10:30:16] [GPUMemoryManager] [INFO] 显存清理成功: 释放了 1.25GB (1280MB)
```

---

## 场景：获取GPU信息

### 原版实现

```python
# 只能获取显存信息
def get_gpu_memory_info(self, gpu_index: int = 0) -> Optional[Tuple[float, float]]:
    if not self._initialized:
        return None
        
    try:
        handle = self.pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
        memory_info = self.pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_gb = memory_info.total / GB_TO_BYTES
        used_gb = memory_info.used / GB_TO_BYTES
        return total_gb, used_gb
    except Exception as e:
        print(f"获取GPU信息时出错: {e}")
        return None
```

**使用：**
```python
memory_info = gpu_manager.get_gpu_memory_info(0)
if memory_info:
    total_gb, used_gb = memory_info
    print(f"总{total_gb:.2f}GB, 已用{used_gb:.2f}GB")
```

**输出：**
```
获取GPU信息时出错: ...
```
或
```
总24.00GB, 已用8.50GB
```

---

### 改进版实现

```python
# 可以获取完整的GPU信息
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
    
    if not self.validate_gpu_index(gpu_index):  # 先验证索引
        return info
    
    info["available"] = True
    info["name"] = self.get_gpu_name(gpu_index)
    info["memory"] = self.get_gpu_memory_info(gpu_index)
    info["temperature"] = self.get_gpu_temperature(gpu_index)
    info["utilization"] = self.get_gpu_utilization(gpu_index)
    
    return info

# 还有专门的显示函数
def _show_gpu_info(self, gpu_index: int) -> None:
    """显示GPU详细信息"""
    info = self.gpu_manager.get_detailed_info(gpu_index)
    
    if not info["available"]:
        logger.warning(f"GPU {gpu_index} 不可用")
        return
    
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
```

**使用：**
```python
# 方法1: 获取详细信息
info = gpu_manager.get_detailed_info(0)
print(info)

# 方法2: 直接显示（推荐）
self._show_gpu_info(0)
```

**输出：**
```
[2025-01-30 10:30:15] [GPUMemoryManager] [INFO] GPU 0 | 型号: NVIDIA GeForce RTX 4090 | 显存: 8.50GB/24.00GB (使用率35.4%, 可用15.50GB) | 温度: 65°C | 利用率: 78%
```

---

## 场景：设置预留显存

### 原版实现

```python
def _log_setting(self, reserved: float, mode: str, reserved_bytes: int, 
                gpu_index: int, min_safe_reserve: float) -> None:
    """记录设置信息"""
    reserved_gb = reserved_bytes / GB_TO_BYTES
    
    memory_info = gpu_manager.get_gpu_memory_info(gpu_index)
    if memory_info:
        total_gb, used_gb = memory_info
        print(f"设置预留显存: {reserved_gb:.2f}GB ({mode}模式, GPU{gpu_index}: 总{total_gb:.2f}GB, 已用{used_gb:.2f}GB, 最小保留{min_safe_reserve}GB)")
    else:
        print(f"设置预留显存: {reserved_gb:.2f}GB ({mode}模式, 最小保留{min_safe_reserve}GB)")
```

**输出：**
```
设置预留显存: 2.50GB (smart模式, GPU0: 总24.00GB, 已用8.50GB, 最小保留2.0GB)
```

---

### 改进版实现

```python
def set_memory(self, anything, reserved, mode="smart", gpu_index=0, 
               min_safe_reserve=2.0, clear_memory=False, show_gpu_info=True, ...):
    try:
        # 1. 验证GPU索引
        if not self.gpu_manager.validate_gpu_index(gpu_index):
            logger.error(f"GPU索引 {gpu_index} 无效，使用GPU 0")
            gpu_index = 0
        
        # 2. 显示GPU详细信息（可选）
        if show_gpu_info:
            self._show_gpu_info(gpu_index)
        
        # 3. 清理显存（可选）
        if clear_memory:
            clean_result = self.memory_cleaner.clear_gpu_memory(gpu_index)
            if clean_result["success"] and clean_result["freed_memory_gb"] > 0:
                logger.info(
                    f"✓ 显存清理成功: 释放 {clean_result['freed_memory_gb']:.2f}GB "
                    f"({clean_result['freed_memory_mb']:.0f}MB)"
                )
        
        # 4. 计算预留显存（使用策略计算器）
        reserved_bytes, detail = self.calculator.calculate_reserved_memory(
            reserved, mode, gpu_index, min_safe_reserve, self.gpu_manager
        )
        
        # 5. 设置预留显存
        model_management.EXTRA_RESERVED_MEMORY = reserved_bytes
        
        # 6. 输出详细信息
        reserved_gb = reserved_bytes / GB_TO_BYTES
        logger.info(f"✓ {detail}")
        logger.info(f"已设置预留显存: {reserved_gb:.2f}GB ({reserved_bytes / MB_TO_BYTES:.0f}MB)")
        
    except Exception as e:
        safe_default = max(DEFAULT_RESERVED_GB, min_safe_reserve)
        model_management.EXTRA_RESERVED_MEMORY = int(safe_default * GB_TO_BYTES)
        logger.error(f"设置预留显存时出错: {e}，使用安全默认值 {safe_default:.2f}GB")

    return (anything,)
```

**输出：**
```
[2025-01-30 10:30:15] [GPUMemoryManager] [INFO] GPU 0 | 型号: NVIDIA GeForce RTX 4090 | 显存: 8.50GB/24.00GB (使用率35.4%, 可用15.50GB) | 温度: 65°C | 利用率: 78%
[2025-01-30 10:30:16] [GPUMemoryManager] [INFO] ✓ 智能模式: 2.50GB (状态:充足, 可用15.50GB/24.00GB=64.6%)
[2025-01-30 10:30:16] [GPUMemoryManager] [INFO] 已设置预留显存: 2.50GB (2560MB)
```

---

## 关键改进总结

| 方面 | 原版 | 改进版 |
|------|------|--------|
| **线程安全** | ❌ | ✅ 使用锁 |
| **日志系统** | print | logging模块 |
| **错误提示** | 简单 | 详细+emoji |
| **GPU信息** | 2个字段 | 6个字段 |
| **索引验证** | ❌ | ✅ |
| **清理反馈** | 简单 | 详细报告 |
| **类型安全** | 部分 | 完整 |
| **代码组织** | 紧凑 | 模块化 |

---

## 实际使用体验对比

### 原版使用体验
```
1. 添加节点
2. 设置参数
3. 运行
4. 看到一行日志
5. 不确定是否成功
```

### 改进版使用体验
```
1. 添加节点
2. 设置参数（有详细tooltip）
3. 运行
4. 看到完整的GPU状态
5. 看到详细的执行过程
6. 看到最终结果（GB和MB）
7. 确信设置成功
```

---

**结论：** 改进版在保持兼容性的同时，大幅提升了功能性、可靠性和用户体验！
