"""
ComfyUI GPU显存智能管理节点集
提供显存预留、监控、清理等功能
"""

from .nodes import (
    NODE_CLASS_MAPPINGS, 
    NODE_DISPLAY_NAME_MAPPINGS,
    __version__,
    __author__,
    __description__
)

__all__ = [
    'NODE_CLASS_MAPPINGS', 
    'NODE_DISPLAY_NAME_MAPPINGS',
    '__version__',
    '__author__',
    '__description__'
]

# 打印加载信息
print(f"[ARES GPU Memory Manager] v{__version__} 已加载")
print(f"[ARES GPU Memory Manager] 节点数: {len(NODE_CLASS_MAPPINGS)}")
print(f"[ARES GPU Memory Manager] 节点列表: {', '.join(NODE_DISPLAY_NAME_MAPPINGS.values())}")
