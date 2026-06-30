# Scheduled Jobs

## 适用场景

DojoAgents 使用 cron/scheduler 模块管理后台计划任务，例如维护缓存或触发分析工作流。

## CLI 检查

```bash
dojoagents scheduler
```

该命令会加载默认 runtime 并输出已加载的 scheduled jobs 数量。

## 相关模块

| 模块 | 说明 |
| --- | --- |
| `dojoagents/cron/jobs.py` | Job 模型和存储 |
| `dojoagents/cron/scheduler.py` | Scheduler 集成 |
| `dojoagents/planning/triggers.py` | Plan 触发器 |

## 下一步

金融数据缓存和计划任务应通过具体 dashboard service 的配置与日志确认。
