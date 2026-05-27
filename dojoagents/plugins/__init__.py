from __future__ import annotations

from dojoagents.plugins.registry import DojoPluginRegistry

_global_registry: DojoPluginRegistry | None = None

def get_plugin_registry() -> DojoPluginRegistry:
    """获取并延迟初始化全局插件注册表单例"""
    global _global_registry
    if _global_registry is None:
        _global_registry = DojoPluginRegistry()
        _global_registry.discover_and_load()
    return _global_registry
