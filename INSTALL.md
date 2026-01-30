# 安装指南

## 快速安装

### 方法1：手动安装（推荐）

1. **下载文件**
   - 下载 `nodes_improved.py`
   - 下载 `__init___improved.py`（重命名为 `__init__.py`）

2. **放置文件**
   ```bash
   # Windows
   ComfyUI\custom_nodes\ARES_GPU_Manager\
   ├── __init__.py
   └── nodes_improved.py
   
   # Linux/Mac
   ComfyUI/custom_nodes/ARES_GPU_Manager/
   ├── __init__.py
   └── nodes_improved.py
   ```

3. **安装依赖（可选）**
   ```bash
   # 进入ComfyUI目录
   cd ComfyUI
   
   # 激活虚拟环境（如果使用）
   # Windows: venv\Scripts\activate
   # Linux/Mac: source venv/bin/activate
   
   # 安装pynvml（用于GPU监控）
   pip install pynvml
   ```

4. **重启ComfyUI**
   - 完全关闭ComfyUI
   - 重新启动
   - 在节点菜单中查找 "ARES/显存管理" 分类

---

## 验证安装

### 1. 检查启动日志

启动ComfyUI后，应该看到类似输出：
```
[ARES GPU Memory Manager] v2.0.0 已加载
[ARES GPU Memory Manager] 节点数: 3
[ARES GPU Memory Manager] 节点列表: 🎛️ 智能显存预留, 📊 GPU显存监控, 🧹 批量显存清理
[GPUMemoryManager] GPU监控已初始化 (pynvml)
```

### 2. 在节点菜单中查找

右键 → Add Node → ARES → 显存管理
- 🎛️ 智能显存预留
- 📊 GPU显存监控
- 🧹 批量显存清理

### 3. 测试节点

1. 添加 "智能显存预留" 节点
2. 设置参数后执行
3. 查看控制台输出，应该看到：
   ```
   [GPUMemoryManager] GPU 0 | 型号: ... | 显存: ...
   [GPUMemoryManager] ✓ 智能模式: 2.00GB (状态:充足, ...)
   [GPUMemoryManager] 已设置预留显存: 2.00GB (2048MB)
   ```

---

## 常见问题

### Q1: 节点没有出现在菜单中

**解决方案：**
1. 检查文件路径是否正确
2. 确认 `__init__.py` 文件名正确（不是 `__init___improved.py`）
3. 查看ComfyUI启动日志是否有错误
4. 尝试清空浏览器缓存（Ctrl+F5）

### Q2: 显示 "未安装pynvml库" 警告

**影响：** GPU监控功能不可用，但基本功能仍然正常

**解决方案：**
```bash
pip install pynvml
```

### Q3: 安装pynvml后仍然不工作

**可能原因：**
- 虚拟环境问题
- NVIDIA驱动未正确安装

**解决方案：**
```bash
# 检查NVIDIA驱动
nvidia-smi

# 在正确的虚拟环境中安装
# 确认是在ComfyUI使用的Python环境中
which python  # Linux/Mac
where python  # Windows

pip install pynvml
```

### Q4: 节点执行时报错

**检查清单：**
1. ComfyUI版本是否最新
2. PyTorch是否正确安装
3. 查看完整错误日志
4. 尝试使用 Manual 模式（最简单）

---

## 卸载

如需卸载节点：

1. 删除整个文件夹：
   ```bash
   rm -rf ComfyUI/custom_nodes/ARES_GPU_Manager
   ```

2. 重启ComfyUI

---

## 更新

替换 `nodes_improved.py` 文件后重启ComfyUI即可。

---

## 技术支持

如果遇到问题：
1. 查看完整的错误日志
2. 确认系统环境（OS、GPU型号、驱动版本）
3. 提供复现步骤

---

## 系统要求

### 最低要求
- ComfyUI（任意版本）
- Python 3.8+
- PyTorch with CUDA

### 推荐配置
- ComfyUI 最新版
- Python 3.10+
- NVIDIA GPU with 8GB+ VRAM
- 最新NVIDIA驱动
- pynvml 已安装

---

**安装完成后，请查看 README.md 了解详细使用方法！**
