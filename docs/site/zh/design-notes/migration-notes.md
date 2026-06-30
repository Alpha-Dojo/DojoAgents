# 迁移记录

> 状态：migration index  
> 最后核对：2026-06-29

本页汇总 AlphaDojo 和其他迁移相关材料。旧 `docs/hermes/` 参考目录已清理，仍需要保留的迁移背景应迁入 `docs/plans/`。

## AlphaDojo 迁移

- `docs/plans/alphadojo_dashboard_upgrade_design.md`
- `docs/plans/alphadojo_migration_design.md`
- `docs/plans/alphadojo5-agent-upgrade-design.md`
- `docs/plans/alphadojo6-agent-upgrade-design.md`
- `docs/plans/alphadojo6-agent-upgrade-implementation-plan.md`
- `docs/plans/alphadojo6-viz-blocks-upgrade-plan.md`

## MkDocs 本轮落地反思

1. 首页和快速开始必须先覆盖安装、启动、模型配置、首次运行，否则站点只有结构没有入口。
2. 旧文档保留原路径，新页面先提炼主线内容，避免破坏外部链接。
3. `plans/`、`hermes/`、`superpowers/` 不直接进入主导航，只通过设计记录索引访问。
4. Reference 页面以当前代码字段为准，历史协议文档作为深入阅读。
5. 由于引入 MkDocs 是新增第三方依赖，必须同步更新 `pyproject.toml` 和 `uv.lock`。
