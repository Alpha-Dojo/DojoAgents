# 配置

## 状态

配置系统以 `dojoagents/config/loader.py::ConfigStore` 和 `dojoagents/config/models.py::AgentsConfig` 为准。

## 默认路径

```text
~/.dojo/agents.yaml
```

## 使用原则

- typed reads 使用 `ConfigStore.snapshot()`。
- 用户配置更新使用 `ConfigStore.raw()`、deep merge 和 `ConfigStore.save_raw()`。
- Dashboard/API 暴露配置使用 `ConfigStore.redacted()`。
- 不要创建第二套 YAML parser、环境变量展开或配置 singleton。

## 相关代码

- `dojoagents/config/loader.py`
- `dojoagents/config/models.py`
- `dojoagents/config/watcher.py`

