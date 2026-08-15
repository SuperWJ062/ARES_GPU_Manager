# 快速参考卡片

## 🚀 5分钟上手指南

### 安装（3步）
```bash
1. 复制文件夹到: ComfyUI/custom_nodes/ARES_GPU_Manager/
2. pip install pynvml  (可选)
3. 重启ComfyUI
```

### 使用（最简单）
```
1. 添加 "智能显存预留" 节点
2. 保持默认设置（smart模式）
3. 连接到工作流
4. 运行！
```

---

## 🎛️ 智能显存预留

**用途：** 设置显存预留策略（附带GPU状态查看和显存清理）  
**推荐：** mode=smart, reserved=1.0-2.0GB  
**位置：** 工作流开始处

---

## ⚙️ 三种模式速查

| 模式 | 何时使用 | 配置 |
|------|----------|------|
| **Smart** ⭐ | 99%的情况 | 默认即可 |
| **Auto** | 渐进式任务 | reserved=1.5 |
| **Manual** | 固定需求 | reserved=3.0 |

---

## 🎯 常见配置速查

### 场景1：日常使用
```
mode: smart
reserved: 1.0-1.5 GB
clear_memory: False
```

### 场景2：高分辨率
```
mode: smart
reserved: 2.0-3.0 GB
min_safe_reserve: 3.0 GB
```

### 场景3：批量处理
```
mode: auto
reserved: 1.0 GB
clear_memory: True
```

### 场景4：多模型
```
mode: smart
clear_memory: True
clear_all_gpus: True
```

---

## 🔧 参数含义速记

| 参数 | 含义 | 推荐值 |
|------|------|--------|
| reserved | 预留大小 | 1.0-2.0 |
| mode | 工作模式 | smart |
| gpu_index | GPU编号 | 0 |
| min_safe_reserve | 最小保留 | 2.0 |
| clear_memory | 是否清理 | False |
| show_gpu_info | 显示GPU信息 | True |

---

## ⚠️ 重要提示

### ✅ DO
- 优先使用 Smart 模式
- 安装 pynvml 以获得最佳体验
- 在显存不足前清理
- 查看日志了解运行状态

### ❌ DON'T
- 设置过大的预留值（浪费）
- 设置过小的预留值（OOM）
- 频繁清理显存（影响性能）
- 忽略警告信息

---

## 🐛 故障速查

| 问题 | 原因 | 解决 |
|------|------|------|
| 节点不显示 | 安装错误 | 检查路径 |
| 无GPU信息 | 缺少pynvml | `pip install pynvml` |
| 仍然OOM | 预留太小 | 增加reserved |
| 清理无效 | 模型占用 | 开启 clear_memory |

---

## 📝 日志理解

### 正常运行
```
✓ 智能模式: 2.50GB (状态:充足, ...)
已设置预留显存: 2.50GB
```

### 需要注意
```
⚠ GPU索引无效  → 检查gpu_index
⚠ 手动预留值过高 → 减少reserved
```

### 严重错误
```
✗ 获取GPU信息时出错 → 检查驱动
✗ 设置预留显存时出错 → 查看详细日志
```

---

## 🎨 工作流集成

### 基础工作流
```
加载模型 → 智能显存预留 → 生成图像
```

### 进阶工作流
```
加载模型 → 智能显存预留（开启清理） → 生成 → 切换模型
```

### 批量工作流
```
开始 → 智能显存预留（clear_memory=开） → 循环处理 → 结束
```

---

## 🔢 数值参考

### 显存容量对应推荐值

| 显存 | reserved | min_safe_reserve |
|------|----------|------------------|
| 8GB | 1.0 GB | 1.5 GB |
| 12GB | 1.5 GB | 2.0 GB |
| 16GB | 2.0 GB | 2.5 GB |
| 24GB | 2.5 GB | 3.0 GB |
| 32GB+ | 3.0 GB | 4.0 GB |

### 任务类型对应推荐值

| 任务 | reserved | mode |
|------|----------|------|
| 512×512 | 1.0 GB | smart |
| 1024×1024 | 1.5 GB | smart |
| 2048×2048 | 2.5 GB | smart |
| 批量小图 | 1.0 GB | auto |
| 视频生成 | 3.0 GB | smart |

---

## 💡 Pro Tips

### Tip 1: show_gpu_info 不影响性能
```
可以一直开启，仅用于查看信息
```

### Tip 2: 清理时机
```
✓ 模型切换前
✓ 工作流开始前
✓ 显存占用>80%时
✗ 每次生成都清理（过度）
```

### Tip 3: 模式选择
```
不确定用什么？→ Smart
需要精确控制？→ Manual
显存波动大？→ Auto
```

### Tip 4: 日志查看
```
Windows: 命令行窗口
Linux: 终端
或查看 ComfyUI/comfyui.log
```

### Tip 5: 多GPU配置
```
GPU 0: 主要工作 (reserved=2.0)
GPU 1: 辅助任务 (reserved=1.0)
使用 gpu_index 参数选择
```

---

## 📞 获取帮助

### 检查清单
1. ✓ 查看启动日志
2. ✓ 确认pynvml已安装
3. ✓ 检查nvidia-smi
4. ✓ 尝试Manual模式
5. ✓ 查看完整错误信息

### 信息收集
- OS: Windows/Linux/Mac
- GPU: 型号和显存
- ComfyUI版本
- 错误日志
- 复现步骤

---

## 📚 文档索引

- **安装指南：** INSTALL.md
- **完整文档：** README.md
- **改进详解：** IMPROVEMENTS.md
- **源代码：** nodes.py

---

## 版本信息

```
当前版本: v2.2
作者: ARES
许可证: MIT
```

---

**记住：遇到问题先看日志，99%的问题都能在日志中找到答案！**

**Happy ComfyUI-ing! 🎨**
