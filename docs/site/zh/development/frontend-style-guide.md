# 前端样式规范

Dashboard 是金融分析和 Agent 操作界面，应优先服务高频扫描、对比和重复操作。

## 核心原则

- SaaS/CRM/运营类界面保持安静、清晰、可扫描。
- 工具控件优先使用图标按钮、分段控件、checkbox、slider、菜单、tabs 等熟悉模式。
- 页面 section 使用全宽布局或普通内容区，不做漂浮大卡片。
- 卡片只用于重复项、modal 或真正需要 framed 的工具。
- 文本不能在移动端和桌面端溢出或互相遮挡。
- 固定格式元素使用稳定尺寸，例如 board、toolbar、counter、tile、chart 容器。
- 表格、列表和图表优先保证密度、对齐和可比较性。

## 实现约定

- 复用 `dojoagents/dashboard/web/src/components/` 和 `components/ui/` 中已有组件。
- API 调用放在 `dojoagents/dashboard/web/src/api/`。
- 类型放在 `dojoagents/dashboard/web/src/types/`。
- 页面级视图放在 `dojoagents/dashboard/web/src/views/`。
- 共享计算放在 `dojoagents/dashboard/web/src/utils/`。

## 验证

前端改动至少运行：

```bash
cd dojoagents/dashboard/web
npm run build
```

涉及响应式布局、图表或 canvas 时，应在桌面和移动宽度检查文本不溢出、控件不重叠、数据图层可见。
