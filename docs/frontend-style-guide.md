# AlphaNexus 前端样式规范

本文档沉淀 AlphaNexus 当前版本的金融分析工作台视觉规范，用于在其他项目中复用。规范来源包括当前 `styles.css` token、核心 Vue 组件样式，以及设计稿中的“颜色与排版”系统。

## 设计方向

AlphaNexus 使用深色金融终端风格：低亮度背景、细边框、高信息密度、克制的绿色主色，以及少量风险色辅助判断。界面应像专业分析系统，而不是营销页面。

核心原则：

- 深色背景分层，不使用大面积纯黑。
- 主色只用于当前态、可操作入口和正向指标。
- 风险、警告、链接分别使用独立语义色，避免所有高亮都变成绿色。
- 卡片边界轻，内容密度高，圆角小，阴影弱。
- 字号层级克制，正文以 12px/14px 为主体，标题以 16px 为常规上限。

## 命名体系

当前项目中使用 `c-*` 和 `t-*` 命名，适合 Tailwind 快速开发；跨项目复用时建议使用更语义化的 token 名称。

| 推荐 token | 当前 token | 值 | 用途 |
| --- | --- | --- | --- |
| `color-accent-float` | `c-float` | `#00E0A2` | 高亮浮层、强强调、特殊激活态 |
| `color-accent-primary` | `c-main` | `#02AF7F` | 主操作、当前态、正向指标 |
| `color-accent-pressed` | `c-hit` | `#03835F` | 点击态、按下态、深一级主色 |
| `color-accent-disabled` | `c-off` | `#00513A` | 禁用态、弱化主色背景 |
| `color-status-danger` | `c-danger` | `#BB2934` | 下跌、错误、风险、负向状态 |
| `color-status-warning` | `c-warn` | `#DC9400` | 危险提示、关注信号、估值高位 |
| `color-action-link` | `c-link` | `#226BD0` | 链接、可跳转信息、辅助操作 |
| `color-text-primary` | `t-1` | `#FFFFFF` | 一级文本、关键数值 |
| `color-text-secondary` | `t-2` | `#94A3B8` | 正文、说明、大段文本 |
| `color-text-tertiary` | `t-3` | `#64748B` | 辅助文字、时间、元信息 |
| `color-text-disabled` | `t-4` | `#334155` | 禁用文字、弱占位 |
| `color-surface-page` | `bg` | `#070F15` | 页面背景 |
| `color-surface-card` | `card` | `rgb(7 16 26 / 95%)` | 悬浮卡片、面板底色 |

## 色彩规范

### 背景层级

| token | 值 | 使用场景 |
| --- | --- | --- |
| `color-surface-page` | `#070F15` | App 根背景、主工作区背景 |
| `color-surface-panel` | `rgb(7 16 26 / 95%)` | 面板、抽屉、弹窗、主要卡片 |
| `color-surface-raised` | `#0B1824` | 二级浮层、输入框、工具栏背景 |
| `color-surface-subtle` | `rgb(0 0 0 / 10%)` | 列表项、内嵌信息块 |
| `color-surface-muted` | `rgb(255 255 255 / 4%)` | 轻量 hover、图例、弱底色 |

页面整体可以使用设计稿背景 `#1E2834` 作为展示容器或规范页外壳，但业务应用根背景仍建议使用 `#070F15`，以保证图表和卡片对比度。

### 边框与分割线

| token | 推荐值 | 使用场景 |
| --- | --- | --- |
| `color-border-default` | `rgb(255 255 255 / 10%)` | 卡片、列表项、表格分隔 |
| `color-border-muted` | `color-mix(in srgb, #334155 68%, transparent)` | 弱边界、禁用区域 |
| `color-border-accent` | `color-mix(in srgb, #226BD0 58%, #070F15)` | 蓝色信息边框 |
| `color-border-primary` | `rgb(2 175 127 / 35%)` | 当前态、主色卡片、正向标签 |
| `color-border-warning` | `rgb(220 148 0 / 40%)` | 警告卡片 |
| `color-border-danger` | `rgb(187 41 52 / 40%)` | 风险卡片 |

边框优先使用 `1px solid`。避免厚边框和强阴影，金融终端类页面应依靠颜色、密度和信息层级建立秩序。

### 状态色用法

| 状态 | 前景色 | 背景色 | 边框色 |
| --- | --- | --- | --- |
| 正向 / 可执行 | `#02AF7F` | `rgb(2 175 127 / 10%)` | `rgb(2 175 127 / 35%)` |
| 风险 / 错误 | `#BB2934` | `rgb(187 41 52 / 10%)` | `rgb(187 41 52 / 40%)` |
| 警告 / 关注 | `#DC9400` | `rgb(220 148 0 / 15%)` | `rgb(220 148 0 / 35%)` |
| 链接 / 跳转 | `#226BD0` | `rgb(34 107 208 / 10%)` | `rgb(34 107 208 / 35%)` |
| 中性 | `#94A3B8` | `rgb(0 0 0 / 10%)` | `rgb(255 255 255 / 10%)` |

## 字体与排版

### 字体族

```css
--font-sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-mono: "JetBrains Mono", "SF Mono", Consolas, ui-monospace, monospace;
```

使用建议：

- 中文和界面正文使用 `font-sans`。
- 数字、代码、时间、ticker、百分比使用 `font-mono`。
- 全局开启 `-webkit-font-smoothing: antialiased`。

### 字号层级

| 推荐 token | 当前 token | 字号 / 行高 | 字重 | 使用场景 |
| --- | --- | --- | --- | --- |
| `text-caption` | `fa-aux` | `12px / 20px` | 400 | 辅助文案、次要来源信息 |
| `text-body` | `fa-body` | `14px / 22px` | 400 | 正文、列表描述 |
| `text-label` | `fa-sub` | `14px / 22px` | 500 | 小标题、页签标题 |
| `text-title` | `fa-title` | `16px / 24px` | 600 | 卡片标题、页面导航信息 |

补充规格：

| 用途 | 推荐样式 |
| --- | --- |
| 微标签 | `10px / 16px`, `font-weight: 600`, 可使用大写和 `0.12em` 到 `0.16em` 字距 |
| 关键数字 | `18px` 到 `24px`, `font-mono`, `font-weight: 600` |
| 页面模块标题 | `16px / 24px`, `font-weight: 600` |
| 系统大标题 | `28px` 到 `32px`, `font-weight: 700`，仅在品牌或规范展示页使用 |

## 尺寸系统

### 间距

推荐使用 4px 基准栅格。

| token | 值 | Tailwind 对应 | 使用场景 |
| --- | --- | --- | --- |
| `space-1` | `4px` | `1` | 细小间隔、标签内局部间距 |
| `space-2` | `8px` | `2` | 列表项间距、图例间距 |
| `space-3` | `12px` | `3` | 卡片内小 padding、按钮横向间距 |
| `space-4` | `16px` | `4` | 常规卡片 padding、模块间距 |
| `space-5` | `20px` | `5` | 页面 header padding |
| `space-6` | `24px` | `6` | 空状态、复杂卡片 padding |

### 圆角

金融分析系统应使用小圆角，避免大面积圆润风格。

| token | 值 | Tailwind 对应 | 使用场景 |
| --- | --- | --- | --- |
| `radius-xs` | `2px` | `rounded-xs` | 小标签、状态点、表格内徽标 |
| `radius-sm` | `4px` | `rounded-sm` | 列表项、页签、按钮、输入框 |
| `radius-md` | `6px` | `rounded-md` | 信息块、小卡片 |
| `radius-lg` | `8px` | `rounded-lg` | 主卡片、面板、弹窗 |
| `radius-full` | `999px` | `rounded-full` | 进度条、圆形状态、胶囊按钮 |

卡片圆角默认使用 `8px`，内嵌列表项使用 `4px`。不要在工作台页面中使用超过 `12px` 的圆角。

## 组件样式模式

### 基础卡片

基础卡片用于承载图表、摘要、指标和分析内容。

```css
.surface-card {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 8px;
  background: linear-gradient(
    360deg,
    rgb(255 255 255 / 2%) 0%,
    rgb(255 255 255 / 0.2%) 100%
  );
  padding: 16px;
}
```

对应当前实现：

- `base-card`
- `rounded-lg border border-white/10 p-4`

使用规则：

- 卡片标题使用 `12px` 大写标签，颜色 `color-text-secondary`。
- 卡片内主内容使用 `color-text-primary`。
- 元信息和说明使用 `color-text-secondary` 或 `color-text-tertiary`。
- 同屏卡片较多时，优先降低 padding 到 `12px`，不要缩小正文到不可读。

### 警告卡片

```css
.surface-card--warning {
  border-color: rgb(220 148 0 / 40%);
  background: rgb(220 148 0 / 10%);
}
```

用于估值风险、异常波动、需要关注的 AI 解读。标题或关键数字可使用 `color-status-warning`。

### 列表项卡片

```css
.list-card {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 4px;
  background: rgb(0 0 0 / 10%);
  padding: 8px 12px;
  font-size: 12px;
  line-height: 20px;
}
```

高亮负向项：

```css
.list-card--danger {
  border-color: rgb(187 41 52 / 40%);
  background: rgb(187 41 52 / 10%);
}
```

对应当前实现：`SignalListItem.vue`。

### 状态标签

```css
.status-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 2px;
  background: rgb(0 0 0 / 10%);
  padding: 4px 8px;
  color: #94A3B8;
  font-size: 10px;
  line-height: 1;
}
```

状态变体：

| 变体 | 文本色 | 背景 | 边框 |
| --- | --- | --- | --- |
| `status-chip--positive` | `#02AF7F` | `rgb(2 175 127 / 10%)` | `rgb(2 175 127 / 35%)` |
| `status-chip--negative` | `#FECACA` | `rgb(187 41 52 / 20%)` | `rgb(187 41 52 / 35%)` |
| `status-chip--warning` | `#FEF3C7` | `rgb(220 148 0 / 15%)` | `rgb(220 148 0 / 35%)` |
| `status-chip--risk` | `#BB2934` | `rgb(187 41 52 / 10%)` | `rgb(187 41 52 / 40%)` |

对应当前实现：`ToneChip.vue`。

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
  background: #02AF7F;
}
```

标签行：

- 左侧：指标名，`10px`, `color-text-secondary`。
- 右侧：百分比，`10px`, `font-mono`。
- 进度条颜色按语义选择 `primary / warning / danger / link`。

对应当前实现：`MetricProgress.vue`。

### 分段导航

分段导航用于模块切换，不建议做成大按钮。

```css
.segmented-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  border: 1px solid rgb(2 175 127 / 10%);
  border-radius: 4px;
  padding: 2px;
}

.segmented-nav__item {
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 4px 12px;
  color: #FFFFFF;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.segmented-nav__item--active {
  border-color: #02AF7F;
  background: rgb(2 175 127 / 10%);
  color: #02AF7F;
}
```

对应当前实现：`DojoAppHeader.vue`。

### 主操作按钮

```css
.action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  border: 1px solid rgb(2 175 127 / 60%);
  border-radius: 4px;
  background: rgb(2 175 127 / 10%);
  padding: 0 12px;
  color: #02AF7F;
  font-size: 14px;
  font-weight: 600;
  transition: border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease;
}

.action-button:hover {
  border-color: #02AF7F;
  background: rgb(2 175 127 / 15%);
}

.action-button--active {
  border-color: #02AF7F;
  background: rgb(2 175 127 / 15%);
  box-shadow: 0 0 18px rgb(2 175 127 / 16%);
}
```

### 数据表格

表格适合高密度数据显示，避免大卡片套小卡片。

推荐规则：

- 表格字号：`10px` 到 `12px`。
- 表头：`color-text-secondary`，背景 `rgb(255 255 255 / 4%)`。
- 单元格横向 padding：`8px`。
- 行分割线：`rgb(255 255 255 / 10%)`。
- 数字右对齐，使用 `font-mono`。

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

- 正向线：`#02AF7F`
- 风险线：`#BB2934`
- 警告线：`#DC9400`
- 链接 / 对比线：`#226BD0`
- 紫色辅助线：`#8B5CF6`
- 网格线：`rgb(255 255 255 / 8%)`
- 坐标轴文字：`#64748B`

## 布局规范

### 应用骨架

```css
.app-shell {
  display: flex;
  height: 100dvh;
  min-width: 320px;
  overflow: hidden;
  background: #070F15;
  color: #FFFFFF;
}
```

工作台页面应采用“顶部导航 + 主内容区域”的结构。主内容区域必须设置 `min-height: 0`，避免图表、滚动容器和三栏布局溢出。

### 响应式断点

| 断点 | 用法 |
| --- | --- |
| `1100px` | 三栏或复杂 header 改为纵向堆叠 |
| `900px` | 双栏分析页改为单栏 |
| `720px` | 表单、按钮组、指标卡改为单列 |

移动端不要强行保持桌面三栏结构；优先保证阅读顺序和图表高度。

## Tailwind 主题建议

可迁移项目建议保留当前简短类名，同时在文档或设计系统中使用语义名解释。

```css
@theme {
  --font-sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", "SF Mono", Consolas, ui-monospace, monospace;

  --color-c-float: #00e0a2;
  --color-c-main: #02af7f;
  --color-c-hit: #03835f;
  --color-c-off: #00513a;
  --color-c-danger: #bb2934;
  --color-c-warn: #dc9400;
  --color-c-link: #226bd0;

  --color-t-1: #ffffff;
  --color-t-2: #94a3b8;
  --color-t-3: #64748b;
  --color-t-4: #334155;
  --color-bg: #070f15;
  --color-card: rgb(7 16 26 / 95%);

  --text-fa-aux: 12px;
  --text-fa-aux--line-height: 20px;
  --text-fa-body: 14px;
  --text-fa-body--line-height: 22px;
  --text-fa-sub: 14px;
  --text-fa-sub--line-height: 22px;
  --text-fa-title: 16px;
  --text-fa-title--line-height: 24px;
}
```

## 使用禁忌

- 不要把主色 `#02AF7F` 用作所有强调色；风险、警告、链接必须分开。
- 不要在工作台页面使用大面积渐变背景、装饰光斑或营销式 hero。
- 不要使用大圆角卡片；默认 `8px`，内嵌元素 `2px` 到 `4px`。
- 不要在卡片内再嵌套多层卡片；需要分组时使用边框、分割线或轻底色。
- 不要让正文小于 `12px`；只有微标签、图例、表格密集列可以使用 `10px`。
- 不要在图表容器中使用不可收缩的固定高度堆叠；flex/grid 子项要有 `min-height: 0`。

## 快速落地清单

新项目复用时，按以下顺序接入：

1. 先加入字体、颜色和字号 token。
2. 设置根背景 `#070F15`，正文色 `#FFFFFF`。
3. 实现 `surface-card`、`status-chip`、`metric-meter`、`segmented-nav` 四个基础模式。
4. 图表页统一使用 `min-height: 0` 和 `flex: 1 1 0`。
5. 所有风险、警告、链接状态都通过语义色调用，不直接写散落 hex。
6. 用 `12px / 14px / 16px` 建立主体排版，不额外创造过多字号。
