# AlphaDojo Dashboard 前端样式规范

本文档沉淀当前 `dojoagents/dashboard/web` 的金融分析工作台视觉规范，用于后续页面、组件和跨项目复用。规范来源包括 `src/index.css` 全局 token、`src/styles/uiPrimitives.css` 基础样式，以及当前 Header、Tab、Settings、Core、Sphere、Folio、Mesh 视图的实际实现。

## 设计方向

AlphaDojo Dashboard 使用深色金融终端风格：低亮度背景、细边框、高信息密度、克制的绿色主色，以及少量风险色辅助判断。界面应像专业分析系统，而不是营销页面。

核心原则：

- 深色背景分层，不使用大面积纯黑。
- 主色只用于当前态、可操作入口和正向指标。
- 风险、警告、链接分别使用独立语义色，避免所有高亮都变成绿色。
- 卡片边界轻，内容密度高，圆角小，阴影弱。
- 字号层级克制，正文以 `12px / 14px` 为主体，标题以 `16px` 为常规上限。
- 工作台页面优先信息密度和可扫读性，不使用营销式 hero、装饰光斑或大面积渐变。

## Token 命名体系

当前 React web 使用语义化 CSS 变量作为主 token，并保留少量兼容别名，例如 `--bg-panel`、`--text-muted`、`--green`。新增样式应优先调用语义 token，不直接散写 hex。

| 推荐 token | 当前值 | 用途 |
| --- | --- | --- |
| `--color-accent-float` | `#00e0a2` | 高亮浮层、强强调、特殊激活态 |
| `--color-accent-primary` | `#02af7f` | 主操作、当前态、正向指标 |
| `--color-accent-pressed` | `#03835f` | 点击态、按下态、深一级主色 |
| `--color-accent-disabled` | `#00513a` | 禁用态、弱化主色背景 |
| `--color-status-danger` | `#bb2934` | 下跌、错误、风险、负向状态 |
| `--color-status-warning` | `#dc9400` | 危险提示、关注信号、估值高位 |
| `--color-action-link` | `#226bd0` | 链接、可跳转信息、辅助操作 |
| `--color-text-primary` | `#ffffff` | 一级文本、关键数值 |
| `--color-text-secondary` | `#94a3b8` | 正文、说明、大段文本 |
| `--color-text-tertiary` | `#64748b` | 辅助文字、时间、元信息 |
| `--color-text-disabled` | `#334155` | 禁用文字、弱占位 |
| `--color-surface-page` | `#070f15` | App 根背景、主工作区背景 |
| `--color-surface-panel` | `rgb(7 16 26 / 95%)` | 面板、抽屉、弹窗、主要卡片 |
| `--color-surface-raised` | `#0b1824` | 二级浮层、输入框、工具栏背景 |
| `--color-surface-subtle` | `rgb(0 0 0 / 10%)` | 列表项、内嵌信息块 |
| `--color-surface-muted` | `rgb(255 255 255 / 4%)` | 轻量 hover、图例、弱底色 |

常用兼容别名：

| 别名 | 指向 | 使用建议 |
| --- | --- | --- |
| `--bg-deep` | `--color-surface-page` | 页面根背景 |
| `--bg-panel` | `--color-surface-panel` | 卡片、弹层、主面板 |
| `--bg-elevated` | `--color-surface-raised` | 输入框、二级容器 |
| `--border-dim` | `--color-border-default` | 默认弱边框 |
| `--text-primary` | `--color-text-primary` | 一级文本 |
| `--text-muted` | `--color-text-secondary` | 二级文本 |
| `--text-dim` | `--color-text-tertiary` | 三级文本 |
| `--green` | `--color-accent-primary` | 正向市场色兼容别名 |
| `--red` | `--color-status-danger` | 负向市场色兼容别名 |

## 色彩规范

### 背景层级

| token | 值 | 使用场景 |
| --- | --- | --- |
| `--color-surface-page` | `#070f15` | App 根背景、主工作区背景 |
| `--color-surface-panel` | `rgb(7 16 26 / 95%)` | 面板、抽屉、弹窗、主要卡片 |
| `--color-surface-raised` | `#0b1824` | 二级浮层、输入框、工具栏背景 |
| `--color-surface-subtle` | `rgb(0 0 0 / 10%)` | 列表项、内嵌信息块 |
| `--color-surface-muted` | `rgb(255 255 255 / 4%)` | 轻量 hover、图例、弱底色 |

业务应用根背景使用 `#070f15`，以保证图表、表格和卡片的对比度。不要把页面改成纯黑，也不要使用高饱和大面积背景。

### 边框与分割线

| token | 推荐值 | 使用场景 |
| --- | --- | --- |
| `--color-border-default` | `rgb(255 255 255 / 10%)` | 卡片、列表项、表格分隔 |
| `--color-border-muted` | `color-mix(in srgb, #334155 68%, transparent)` | 弱边界、禁用区域 |
| `--color-border-accent` | `color-mix(in srgb, #226BD0 58%, #070F15)` | 蓝色信息边框 |
| `--color-border-primary` | `rgb(2 175 127 / 35%)` | 当前态、主色卡片、正向标签 |
| `--color-border-warning` | `rgb(220 148 0 / 40%)` | 警告卡片 |
| `--color-border-danger` | `rgb(187 41 52 / 40%)` | 风险卡片 |

边框优先使用 `1px solid`。避免厚边框和强阴影，金融终端类页面应依靠颜色、密度和信息层级建立秩序。

### 状态色用法

| 状态 | 前景色 | 背景色 | 边框色 |
| --- | --- | --- | --- |
| 正向 / 可执行 | `#02af7f` | `rgb(2 175 127 / 10%)` | `rgb(2 175 127 / 35%)` |
| 风险 / 错误 | `#bb2934` | `rgb(187 41 52 / 10%)` | `rgb(187 41 52 / 40%)` |
| 警告 / 关注 | `#dc9400` | `rgb(220 148 0 / 15%)` | `rgb(220 148 0 / 35%)` |
| 链接 / 跳转 | `#226bd0` | `rgb(34 107 208 / 10%)` | `rgb(34 107 208 / 35%)` |
| 中性 | `#94a3b8` | `rgb(0 0 0 / 10%)` | `rgb(255 255 255 / 10%)` |

### 市场身份色

市场身份色用于区分 `US / CN / HK`，不承担涨跌语义。涨跌仍然使用 `--green` 和 `--red`。

| 市场 | 线条 | 填充顶部 | 填充底部 | 标签 |
| --- | --- | --- | --- | --- |
| US | `--market-us-line: #6ec0e4` | `rgba(110, 192, 228, 0.72)` | `rgba(110, 192, 228, 0.24)` | `#8ec4de` |
| CN | `--market-cn-line: #96a8bc` | `rgba(150, 168, 188, 0.58)` | `rgba(150, 168, 188, 0.18)` | `#96a8bc` |
| HK | `--market-hk-line: #708498` | `rgba(112, 132, 152, 0.62)` | `rgba(112, 132, 152, 0.2)` | `#788ea2` |

使用规则：

- 市场身份色要低饱和，不与绿色 / 红色涨跌色竞争。
- 同一图表内可以用市场身份色区分序列，用涨跌色表达方向。
- 标签色优先使用对应 `--market-*-label`，线条使用 `--market-*-line`。

### 市场涨跌色

| token | 值 | 用途 |
| --- | --- | --- |
| `--market-up-bg` | `rgb(2 175 127 / 10%)` | 正向弱背景 |
| `--market-down-bg` | `rgb(187 41 52 / 10%)` | 负向弱背景 |
| `--market-up-bg-emphasis` | `rgb(2 175 127 / 12%)` | 正向强调背景 |
| `--market-down-bg-emphasis` | `rgb(187 41 52 / 12%)` | 负向强调背景 |
| `--market-up-fill-soft` | `rgb(2 175 127 / 28%)` | 正向图形弱填充 |
| `--market-down-fill-soft` | `rgb(187 41 52 / 28%)` | 负向图形弱填充 |

## 字体与排版

### 字体族

```css
--font-sans: 'Inter', 'Segoe UI', system-ui, sans-serif;
--font-mono: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;
```

使用建议：

- 中文和界面正文使用 `font-sans`。
- 数字、代码、时间、ticker、百分比使用 `font-mono`。
- 全局开启 `-webkit-font-smoothing: antialiased`。
- 工作台内不要使用负字距；除微标签和 tab 外，默认 `letter-spacing: 0`。

### 字号层级

| 用途 | 推荐样式 | 使用场景 |
| --- | --- | --- |
| 微标签 | `10px / 16px`, `600`, `0.08em` 到 `0.16em` | 表格紧凑列、图例、eyebrow |
| 辅助文本 | `11px / 16px` 到 `12px / 18px` | 空状态、状态行、meta |
| 正文 | `12px / 18px` 到 `14px / 22px` | 列表、说明、表单 |
| 控件文字 | `12px`, `500` 到 `600` | tab、菜单、按钮 |
| 卡片标题 | `12px` 到 `14px`, `600` 到 `700` | 面板标题、section summary |
| 页面模块标题 | `16px / 24px`, `600` 到 `700` | Modal 标题、大模块标题 |
| 关键数字 | `18px` 到 `24px`, `font-mono`, `600` | 价格、涨跌、核心指标 |

图表日期使用独立 token：

| token | 值 | 使用场景 |
| --- | --- | --- |
| `--chart-date-color` | `var(--text-muted)` | 常规日期 |
| `--chart-date-color-active` | `var(--color-accent-primary)` | 当前日期 / 活跃刻度 |
| `--chart-date-size` | `10px` | 标准日期 |
| `--chart-date-size-head` | `11px` | 日期头部 |
| `--chart-date-size-compact` | `9px` | 紧凑图表 |
| `--chart-date-weight` | `500` | 常规日期字重 |
| `--chart-date-weight-active` | `600` | 活跃日期字重 |

## 尺寸系统

### 间距

使用 4px 基准栅格。

| token | 值 | 使用场景 |
| --- | --- | --- |
| `space-1` | `4px` | 细小间隔、标签内局部间距 |
| `space-2` | `8px` | 列表项间距、图例间距 |
| `space-3` | `12px` | 卡片内小 padding、按钮横向间距 |
| `space-4` | `16px` | 常规卡片 padding、模块间距 |
| `space-5` | `20px` | 页面 header padding |
| `space-6` | `24px` | 空状态、复杂卡片 padding |

当前工作台为了高密度展示，经常使用 `6px`、`7px`、`10px` 这类半步间距。新增组件可以使用半步，但必须服务于信息密度，不要制造随意感。

### 圆角

| token | 值 | 使用场景 |
| --- | --- | --- |
| `radius-xs` | `2px` | 小标签、状态点、表格内徽标 |
| `radius-sm` | `4px` | 列表项、页签、按钮、输入框 |
| `radius-md` | `6px` | 工具栏、小浮层 |
| `radius-lg` | `8px` | 主卡片、面板、弹窗 |
| `radius-full` | `999px` | 进度条、圆形状态 |

卡片默认 `8px`，内嵌列表项和按钮默认 `4px`。不要在工作台页面中使用超过 `12px` 的圆角。

## 组件样式模式

### 基础卡片

当前基础卡片由 `uiPrimitives.css` 统一承接，用于 `core-card`、`folio-card`、`sphere-card`、`market-hero`。

```css
.surface-card {
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--border-dim);
  border-radius: 8px;
  background:
    linear-gradient(360deg, rgb(255 255 255 / 2%) 0%, rgb(255 255 255 / 0.2%) 100%),
    var(--bg-panel);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
```

使用规则：

- 卡片自身负责承载边框、背景、圆角和 flex column。
- 卡片内部 padding 可以由业务类控制，例如紧凑表格卡片可降到 `6px` 到 `12px`。
- 卡片标题使用 `12px` 到 `14px`，颜色 `--text-muted` 或 `--text-primary`。
- 同屏卡片较多时，优先降低 padding 和标题高度，不要缩小正文到不可读。

### 顶部导航与工具区

Header 使用三列 grid：左侧品牌，中间 tab，右侧工具区。

```css
.app-header {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  padding: 7px 14px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-dim);
}
```

工具区采用弱边框容器：

```css
.header-util {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  border: 1px solid var(--border-dim);
  border-radius: 6px;
  background: var(--color-surface-subtle);
}
```

使用规则：

- 顶部工具按钮使用 `12px`，高度控制在 `28px` 左右。
- 工具区内用 `1px` separator 分组，不用大面积按钮底色。
- active 态使用 `--color-accent-primary` 和 `rgb(2 175 127 / 10%)`。

### 分段导航

当前实现：`AppTabBar`。

```css
.app-tab-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px;
  border: 1px solid rgb(2 175 127 / 10%);
  border-radius: 4px;
  background: var(--color-surface-subtle);
}

.app-tab-bar__tab {
  border: none;
  border-radius: 4px;
  padding: 6px 14px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.app-tab-bar__tab--active {
  color: var(--color-accent-primary);
  background: rgb(2 175 127 / 10%);
  box-shadow: inset 0 0 0 1px rgb(2 175 127 / 35%);
}
```

分段导航用于模块切换，不建议做成大按钮，也不要使用大圆角胶囊风格。

### 下拉菜单

当前实现：`DropdownMenu` + `.menu-*` primitive，已被模型、语言和时区切换器复用。

```css
.menu-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
}

.menu-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 40;
  padding: 4px;
  border: 1px solid var(--border-dim);
  border-radius: 8px;
  background: var(--bg-panel);
  box-shadow: 0 10px 28px rgb(0 0 0 / 36%);
}

.menu-option {
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  text-align: left;
}
```

使用规则：

- 下拉浮层靠近触发器，默认 `top: calc(100% + 6px)`。
- 菜单 active 态使用主色弱背景。
- 选项 hover 使用 `--color-surface-muted`，避免强高亮。
- 关闭行为统一为点击外部关闭；不要在各组件重复实现相同逻辑。

### 图标按钮

```css
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.icon-button:hover,
.icon-button--active {
  color: var(--text-primary);
  background: var(--color-surface-muted);
}
```

使用规则：

- 仅图标按钮默认 `28px` 到 `30px` 方形。
- 设置、关闭、工具类按钮优先使用图标语义，不新增文字胶囊。
- active 态可以叠加 `color: var(--color-accent-primary)` 和主色弱背景。

### 主操作按钮

当前实现：`.action-button`。

```css
.action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  border: 1px solid var(--color-border-primary);
  border-radius: 4px;
  background: rgb(2 175 127 / 10%);
  padding: 0 12px;
  color: var(--color-accent-primary);
  font-size: 12px;
  font-weight: 600;
}

.action-button:hover:not(:disabled) {
  border-color: var(--color-accent-primary);
  background: rgb(2 175 127 / 15%);
}

.action-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
```

使用规则：

- 用于保存、发送、添加等明确动作。
- 高度默认 `28px`，表单主按钮可提高到 `34px`。
- 不要给常规按钮添加强发光；只在极少数关键当前态中使用 inset 边框。

### 搜索组合框

当前实现：`SearchComboboxShell` + `.search-combobox-*` primitive。用于 ticker search、portfolio search、add holding search。

```css
.search-combobox {
  position: relative;
}

.search-combobox__input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border-dim);
  border-radius: 4px;
  background: rgb(0 0 0 / 22%);
  color: var(--text-primary);
  font: inherit;
  font-size: 11px;
}

.search-combobox__panel {
  position: absolute;
  z-index: 20;
  top: calc(100% + 4px);
  right: 0;
  left: 0;
  overflow: auto;
  border: 1px solid var(--border-dim);
  border-radius: 6px;
  background: rgb(8 14 24 / 98%);
  box-shadow: 0 8px 24px rgb(0 0 0 / 35%);
}

.search-combobox__option:hover,
.search-combobox__option:focus-visible {
  background: rgb(2 175 127 / 8%);
  outline: none;
}
```

使用规则：

- 搜索输入框保留 `type="search"`、`aria-haspopup="listbox"`、`aria-expanded`、`aria-controls`。
- 结果浮层最大高度由业务组件控制，基础浮层只控制位置和视觉。
- 状态行使用 `search-combobox__status`，颜色为 `--text-dim`。
- ticker、组合名称、meta 的排版由业务 option 类补充，不放进通用 primitive。

### 表单与设置弹窗

Settings 使用右侧 drawer 式 modal。

```css
.settings-modal {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  justify-content: flex-end;
}

.settings-modal__scrim {
  position: absolute;
  inset: 0;
  border: 0;
  background: rgba(0, 0, 0, 0.46);
}

.settings-modal__panel {
  width: min(760px, calc(100vw - 24px));
  height: calc(100dvh - 20px);
  margin: 10px;
  border: 1px solid var(--border-dim);
  border-radius: 8px;
  background: var(--bg-panel);
  box-shadow: 0 24px 56px rgb(0 0 0 / 42%);
}
```

表单控件：

```css
.settings-field input,
.settings-field select,
.settings-field textarea {
  border: 1px solid var(--border-dim);
  border-radius: 4px;
  background: var(--color-surface-subtle);
  color: var(--text-primary);
  font: inherit;
  font-size: 13px;
}

.settings-field input:focus,
.settings-field select:focus,
.settings-field textarea:focus {
  border-color: var(--color-border-primary);
  background: rgb(2 175 127 / 8%);
  box-shadow: 0 0 0 2px rgb(2 175 127 / 12%);
}
```

使用规则：

- Modal panel 使用 `8px` 圆角和弱边框，不使用营销式大卡片。
- Form section 使用 `details / summary` 时，summary hover 只加弱底色。
- 输入框高度默认 `34px`，textarea 最小高度约 `76px`。
- Checkbox 使用 `accent-color: var(--color-accent-primary)`。

### 状态标签

```css
.status-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 2px;
  background: rgb(0 0 0 / 10%);
  padding: 4px 8px;
  color: #94a3b8;
  font-size: 10px;
  line-height: 1;
}
```

状态变体：

| 变体 | 文本色 | 背景 | 边框 |
| --- | --- | --- | --- |
| `status-chip--positive` | `#02af7f` | `rgb(2 175 127 / 10%)` | `rgb(2 175 127 / 35%)` |
| `status-chip--negative` | `#fecaca` | `rgb(187 41 52 / 20%)` | `rgb(187 41 52 / 35%)` |
| `status-chip--warning` | `#fef3c7` | `rgb(220 148 0 / 15%)` | `rgb(220 148 0 / 35%)` |
| `status-chip--risk` | `#bb2934` | `rgb(187 41 52 / 10%)` | `rgb(187 41 52 / 40%)` |

### 指标进度条

```css
.metric-meter {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 10%);
}

.metric-meter__bar {
  height: 100%;
  background: var(--color-accent-primary);
}
```

标签行：

- 左侧：指标名，`10px`, `--text-muted`。
- 右侧：百分比，`10px`, `font-mono`。
- 进度条颜色按语义选择 `primary / warning / danger / link`。

### 数据表格

表格适合高密度数据显示，避免大卡片套小卡片。

推荐规则：

- 表格字号：`10px` 到 `12px`。
- 表头：`--text-muted`，背景 `rgb(255 255 255 / 4%)`。
- 单元格横向 padding：`6px` 到 `8px`。
- 行分割线：`rgb(255 255 255 / 10%)`。
- 数字右对齐，使用 `font-mono`。
- 可排序表头保留 button 语义，但视觉上应像表头控件，不像大按钮。

### 图表容器

图表容器必须保证在 flex/grid 中可收缩。

```css
.chart-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
}

.chart-surface {
  min-height: 0;
  flex: 1 1 0;
}
```

推荐高度：

| 场景 | 高度 |
| --- | --- |
| 小型趋势图 | `64px` |
| 标准图表 | `256px` 到 `288px` |
| 主分析图表 | `320px` 到 `360px` |
| 工作台全高图表 | `flex: 1 1 0` |

图表颜色：

- 正向线：`--color-accent-primary`
- 风险线：`--color-status-danger`
- 警告线：`--color-status-warning`
- 链接 / 对比线：`--color-action-link`
- 市场身份线：`--market-us-line`、`--market-cn-line`、`--market-hk-line`
- 网格线：`rgb(255 255 255 / 8%)`
- 坐标轴文字：`--text-dim`

## 布局规范

### 应用骨架

```css
.app-shell {
  display: flex;
  height: 100dvh;
  min-width: 320px;
  overflow: hidden;
  background: var(--color-surface-page);
  color: var(--color-text-primary);
}
```

工作台页面应采用“顶部导航 + 主内容区域”的结构。主内容区域必须设置 `min-height: 0`，避免图表、滚动容器和三栏布局溢出。

### 响应式断点

| 断点 | 用法 |
| --- | --- |
| `1100px` | 三栏或复杂 header 改为纵向堆叠 |
| `900px` | 双栏分析页改为单栏 |
| `720px` | 表单、按钮组、指标卡改为单列 |

移动端不要强行保持桌面三栏结构；优先保证阅读顺序和图表高度。固定格式元素如图表、棋盘、工具条、按钮组应使用稳定尺寸、`minmax(0, 1fr)`、`aspect-ratio` 或容器变量，避免 hover 和动态文本造成布局跳动。

### 滚动条

当前全局滚动条使用低对比轨道和主色 hover。

| token | 值 | 用途 |
| --- | --- | --- |
| `--scrollbar-size` | `10px` | 滚动条宽高 |
| `--scrollbar-track` | `rgb(7 15 21 / 54%)` | 默认轨道 |
| `--scrollbar-track-hover` | `rgb(11 24 36 / 82%)` | hover 轨道 |
| `--scrollbar-thumb` | `rgb(100 116 139 / 52%)` | 默认滑块 |
| `--scrollbar-thumb-hover` | `rgb(2 175 127 / 62%)` | hover 滑块 |
| `--scrollbar-thumb-active` | `rgb(2 175 127 / 82%)` | active 滑块 |
| `--scrollbar-corner` | `rgb(7 15 21 / 72%)` | 角落 |

使用规则：

- 全局滚动条保持一致，不在局部容器里制造不同主题。
- 极窄工具条可隐藏滚动条，但必须保留滚动能力。
- 滚动区域必须有 `min-height: 0` 或明确高度约束。

## CSS 组织与复用

当前建议的样式组织：

1. `index.css`：全局 token、根元素、滚动条、全局骨架。
2. `styles/uiPrimitives.css`：跨组件复用 primitive，例如 card、menu、button、search、status text。
3. 组件 CSS：只保留尺寸、局部布局、具体内容排版和业务变体。
4. View CSS：负责页面网格、模块关系、图表和表格细节。

新增样式优先判断是否属于 primitive：

- 如果多个组件共享同一视觉模型，放入 `uiPrimitives.css`。
- 如果只是某个组件的尺寸或内容排版，保留在组件 / view CSS。
- 不要复制一套 hover、disabled、panel、option 样式到多个组件里。

## Tailwind 主题建议

当前 web 以原生 CSS 变量为主。如果迁移到 Tailwind，可保留语义 token，并在 theme 中映射。

```css
@theme {
  --font-sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", "SF Mono", Consolas, ui-monospace, monospace;

  --color-accent-float: #00e0a2;
  --color-accent-primary: #02af7f;
  --color-accent-pressed: #03835f;
  --color-accent-disabled: #00513a;
  --color-status-danger: #bb2934;
  --color-status-warning: #dc9400;
  --color-action-link: #226bd0;

  --color-text-primary: #ffffff;
  --color-text-secondary: #94a3b8;
  --color-text-tertiary: #64748b;
  --color-text-disabled: #334155;
  --color-surface-page: #070f15;
  --color-surface-panel: rgb(7 16 26 / 95%);
}
```

## 使用禁忌

- 不要把主色 `#02af7f` 用作所有强调色；风险、警告、链接必须分开。
- 不要在工作台页面使用大面积渐变背景、装饰光斑或营销式 hero。
- 不要使用大圆角卡片；默认 `8px`，内嵌元素 `2px` 到 `4px`。
- 不要在卡片内再嵌套多层卡片；需要分组时使用边框、分割线或轻底色。
- 不要让正文小于 `12px`；只有微标签、图例、表格密集列可以使用 `9px` 到 `10px`。
- 不要在图表容器中使用不可收缩的固定高度堆叠；flex/grid 子项要有 `min-height: 0`。
- 不要给常规控件加厚阴影或强 glow；hover 应轻，active 应清晰但克制。
- 不要把市场身份色当作涨跌色使用。

## 快速落地清单

新页面或新项目复用时，按以下顺序接入：

1. 先加入字体、颜色、边框、市场身份色、滚动条和图表日期 token。
2. 设置根背景 `#070f15`，正文色 `#ffffff`，全局 `color-scheme: dark`。
3. 接入 `surface-card`、`menu-*`、`icon-button`、`action-button`、`search-combobox-*`、`status-text`。
4. Header 使用三列 grid，Tab 使用弱底色分段导航。
5. 图表页统一使用 `min-height: 0` 和 `flex: 1 1 0`。
6. 所有风险、警告、链接、市场身份色都通过语义 token 调用，不直接写散落 hex。
7. 用 `12px / 14px / 16px` 建立主体排版，不额外创造过多字号。
