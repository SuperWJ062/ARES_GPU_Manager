# ComfyUI GPU显存智能管理 v2.2

## English Overview

A ComfyUI custom node for smart GPU VRAM management. Core features:

1. **Smart VRAM Reservation** - dynamically manages VRAM reservation strategies, with GPU status monitoring and memory cleanup.

Supports **manual / automatic / smart** reservation modes, placeholder VRAM with timed auto-release, GPU info display (model, temperature, utilization), and cache cleanup before execution. It reserves memory through ComfyUI's `model_management.EXTRA_RESERVED_VRAM` to prevent OOM during model switching and heavy loads.

> 中文文档见下方，以下为中文完整说明。

---

## 📦 概述

这是一个功能强大的 ComfyUI 自定义节点，用于智能管理 GPU 显存，核心节点：

1. **🎛️ 智能显存预留** - 动态管理显存预留策略（含 GPU 状态查看与显存清理）

---

## 🚀 主要功能

### 1. **三种预留模式**

| 模式 | 计算方式 | 适用场景 | 优点 | 缺点 |
|------|----------|----------|------|------|
| **手动** | 固定值 | 显存需求稳定 | 简单直接 | 不够灵活 |
| **自动** | 当前使用+缓冲 | 渐进式任务 | 自动适应 | 可能过于保守 |
| **智能** ⭐ | 动态优化 | 通用场景 | 最优平衡 | 略复杂 |

**智能模式策略：**

```
可用显存 < 20%  → 预留80%（紧张状态）
可用显存 20-40% → 基础预留（中等状态）
可用显存 > 40%  → 最小保留（充足状态）
```

### 2. **GPU 状态查看**

执行时输出当前 GPU 信息：

```
[GPUMemoryManager] GPU 0 | 型号: NVIDIA GeForce RTX 4090 | 显存: 8.50GB/24.00GB (使用率35.4%, 可用15.50GB) | 温度: 65°C | 利用率: 78%
```

### 3. **显存清理**

执行前可清理 PyTorch CUDA 缓存与 Python 垃圾回收，并报告实际释放的显存（GB/MB）。

### 4. **占位显存（真正锁住显存）**

启动独立进程真占显存，并支持**延时占用、到时自动释放**，防止 ComfyUI 占满显存卡住：

- `占位延时`：节点运行后等待多少秒再开始占用
- `占位保持`：占用后保持多少秒自动释放，按流的时间线填写

**注意：** 占用期间该部分显存不可用，生成所需显存若超出上限会报 CUDA OOM，请按实际余量设置。

---

## 📖 使用指南

### 安装

1. 将文件夹放入 ComfyUI 的 `custom_nodes` 目录：
```bash
ComfyUI/
└── custom_nodes/
    └── ARES_GPU_Manager/
        ├── __init__.py
        └── nodes.py
```

2. 安装依赖（可选，用于 GPU 状态监控）：
```bash
pip install nvidia-ml-py
```

3. 重启 ComfyUI

### 节点说明

#### 🎛️ 智能显存预留

**参数说明：**

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| 预留大小 | 预留显存大小 | 1.0-2.0 GB |
| 模式 | 工作模式 | 智能 (推荐) |
| GPU索引 | GPU索引 | 0 |
| 最小安全保留 | 最小安全保留 | 2.0 GB |
| 执行前清理 | 是否清理 | False |
| 显示GPU信息 | 显示信息 | True |
| 占位显存 | 独立进程真占显存 | False |
| 占位显存量 | 占用的显存 | 2.0 GB (1-4) |
| 占位延时 | 延时多少秒开始占用 | 0 秒 |
| 占位保持 | 占用后多少秒自动释放 | 30 秒 |

---

## 🎯 使用场景

### 场景1：高分辨率图像生成
```
推荐配置：
- 模式: 智能
- 预留大小: 2.0-3.0 GB
- 最小安全保留: 3.0 GB
```

### 场景2：批量处理
```
推荐配置：
- 模式: 自动
- 预留大小: 1.0-1.5 GB
- 执行前清理: True (每批次前清理)
```

### 场景3：多模型切换
```
推荐配置：
- 模式: 智能
- 执行前清理: True (切换时清理)
```

### 场景4：开发调试
```
推荐配置：
- 模式: 手动
- 显示GPU信息: True
```

---

## 🔧 技术细节

### 显存计算公式

#### 手动模式
```python
reserved_memory = max(user_input, min_safe_reserve)
if reserved_memory > total_memory * 0.9:
    reserved_memory = total_memory * 0.9
```

#### 自动模式
```python
reserved_memory = current_used + buffer
reserved_memory = max(reserved_memory, min_safe_reserve)
reserved_memory = min(reserved_memory, total_memory * 0.85)
```

#### 智能模式
```python
available_ratio = free_memory / total_memory

if available_ratio < 0.2:
    reserved_memory = total_memory * 0.8
elif available_ratio < 0.4:
    reserved_memory = current_used + buffer
else:
    reserved_memory = max(current_used + buffer, min_safe_reserve)

reserved_memory = min(reserved_memory, total_memory * 0.9)
```

### 预留机制

设置值会写入 ComfyUI 的 `model_management.EXTRA_RESERVED_VRAM`，让内存管理器在计算可用显存时扣除这部分空间，避免显存不足（OOM）。对应 ComfyUI 启动参数 `--reserve-vram`。

### 清理机制

```python
清理步骤：
1. torch.cuda.empty_cache()    # 清空PyTorch缓存
2. torch.cuda.synchronize()    # 同步CUDA操作
3. gc.collect()                # Python垃圾回收
```

---

## ⚠️ 注意事项

1. **nvidia-ml-py 依赖**（提供 `pynvml` 模块）
   - 未安装时 GPU 信息查询会降级，但基本功能正常
   - 推荐安装以获得最佳体验

2. **显存预留策略**
   - 过大：浪费显存
   - 过小：可能OOM
   - 推荐使用 智能 模式

3. **清理时机**
   - 模型切换前
   - 显存不足时
   - 工作流开始前

4. **多GPU环境**
   - 注意选择正确的 GPU 索引

---

## 🐛 故障排查

### 问题1：无法获取GPU信息
```
原因: nvidia-ml-py未安装或初始化失败
解决: pip install nvidia-ml-py
```

### 问题2：设置后仍然OOM
```
原因: 预留值设置过小
解决: 增加预留大小或使用智能模式
```

### 问题3：清理效果不明显
```
原因: 显存已被模型占用
解决: 开启执行前清理参数
```

---

## 📝 更新日志

### v2.2 (当前版本)
- ✅ 修复预留显存设置失效问题（`EXTRA_RESERVED_MEMORY` → `EXTRA_RESERVED_VRAM`）
- 🔧 移除冗余节点（GPU显存监控、批量显存清理、VRAM Trigger），功能合并到智能显存预留节点
- ✨ 新增占位显存功能：独立进程真占显存，支持延时占用、到时自动释放

### v2.0
- ✅ 线程安全的单例模式
- ✅ 专业日志系统
- ✅ 完善的类型注解
- ✅ GPU索引验证
- ✅ 详细GPU信息（型号、温度、利用率）
- ✅ 智能策略优化
- ✅ 增强错误处理
- ✅ 自动资源清理

### v1.0
- 基础显存预留功能
- 三种工作模式
- 简单清理功能

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

MIT License

---

## 👤 作者

**ARES**

---

**Happy ComfyUI-ing! 🎨**
