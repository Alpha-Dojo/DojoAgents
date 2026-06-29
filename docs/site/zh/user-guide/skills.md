# Skills

## 适用场景

Skills 是给 Agent 使用的过程性知识、工具说明和工作流提示。它们由 `dojoagents/skills/` 的 loader、cache 和 manager 管理，也可以通过插件提供。

## 使用方式

在运行时，skills 会作为 Agent 可用能力的一部分加载。新的内置 skill 应放在 `dojoagents/skills/built_in/`，外部 skill 通常通过插件或用户目录发现。

## 相关模块

| 模块 | 说明 |
| --- | --- |
| `dojoagents/skills/loader.py` | 读取 skill 文件 |
| `dojoagents/skills/cache.py` | 缓存 skill 内容 |
| `dojoagents/skills/manager.py` | 管理 skill 生命周期 |
| `dojoagents/tools/skill_manage.py` | 暴露 skill 管理工具 |

## 下一步

需要扩展工具能力时，阅读 [添加工具](../development/adding-tools.md)。

