---
name: canvas-chart
description: "Canvas chart rendering skill. Teaches the agent to output DOJO_CHART blocks for rendering interactive ECharts visualizations in the Dashboard Canvas panel."
version: 1.0.0
author: DojoAgents
license: MIT
category: visualization
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [chart, visualization, canvas, echarts, kline, dashboard]
    related_skills: []
---

# Canvas Chart Rendering

Use this skill when the user requests a chart, graph, or visualization to be displayed on the Dashboard Canvas panel.

## When to Use

Output a `DOJO_CHART` block whenever the user asks to:
- Draw a K-line / candlestick chart
- Plot a line chart (trend, indicators, time series)
- Show a bar chart (volume, comparisons)
- Display an area chart (cumulative returns, ranges)
- Create any ECharts-supported visualization on the canvas

## DOJO_CHART Protocol

In your text response, output a fenced code block with the language tag `DOJO_CHART`. The block must contain a single JSON object with two fields:

````
```DOJO_CHART
{"data": <chart_data>, "script": "<echarts_render_script>"}
```
````

### Field: `data`

An array of data points for the chart. Each element is an object representing one data point.

**For K-line / OHLCV data**, each element must have:
```json
{"time": <unix_timestamp>, "open": <number>, "high": <number>, "low": <number>, "close": <number>, "volume": <number>}
```

**For line / bar / area charts**, use a simple structure:
```json
{"time": <unix_timestamp>, "value": <number>}
```
Or for multi-series:
```json
{"time": <unix_timestamp>, "value1": <number>, "value2": <number>}
```

### Field: `script`

A JavaScript function body string. The sandbox runtime provides three variables:
- `chart` — an initialized ECharts instance (already called `echarts.init(container)`)
- `data` — the `data` array from above
- `echarts` — the global ECharts library reference

Your script **must** call `chart.setOption({...})` to render. Do **not** call `echarts.init()` — the chart is already initialized.

## Dark Theme

The Dashboard uses a dark theme. Always apply these colors:

```javascript
{
  backgroundColor: 'transparent',
  textStyle: { color: '#e0e0e0' },
  title: { textStyle: { color: '#e0e0e0' } },
  legend: { textStyle: { color: '#aaaaaa' } },
  tooltip: { backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#e0e0e0' } }
}
```

K-line colors:
- **Up (bullish)**: `#ef5350` (red)
- **Down (bearish)**: `#26a69a` (green)

## Chart Templates

### 1. K-Line (Candlestick)

For stock or crypto OHLCV data. Use when the user asks for a "K-line", "candlestick chart", or "price chart".

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'K-Line Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'cross' },
    backgroundColor: '#1a1a2e',
    borderColor: '#333',
    textStyle: { color: '#e0e0e0' }
  },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: {
    type: 'category',
    data: data.map(function(d) {
      return new Date(d.time * 1000).toLocaleDateString();
    }),
    axisLabel: { color: '#aaaaaa' },
    axisLine: { lineStyle: { color: '#444' } }
  },
  yAxis: {
    type: 'value',
    scale: true,
    axisLabel: { color: '#aaaaaa' },
    splitLine: { lineStyle: { color: '#333' } }
  },
  series: [{
    type: 'candlestick',
    data: data.map(function(d) {
      return [d.open, d.close, d.low, d.high];
    }),
    itemStyle: {
      color: '#ef5350',
      color0: '#26a69a',
      borderColor: '#ef5350',
      borderColor0: '#26a69a'
    }
  }]
});
```

### 2. K-Line with Volume (Dual Panel)

For when the user wants price + volume together.

```javascript
var dates = data.map(function(d) { return new Date(d.time * 1000).toLocaleDateString(); });
chart.setOption({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'cross' },
    backgroundColor: '#1a1a2e',
    borderColor: '#333',
    textStyle: { color: '#e0e0e0' }
  },
  grid: [
    { left: '10%', right: '5%', top: '8%', height: '55%' },
    { left: '10%', right: '5%', top: '72%', height: '18%' }
  ],
  xAxis: [
    { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#444' } } },
    { type: 'category', data: dates, gridIndex: 1, axisLabel: { color: '#aaaaaa' }, axisLine: { lineStyle: { color: '#444' } } }
  ],
  yAxis: [
    { type: 'value', scale: true, gridIndex: 0, axisLabel: { color: '#aaaaaa' }, splitLine: { lineStyle: { color: '#333' } } },
    { type: 'value', scale: true, gridIndex: 1, axisLabel: { color: '#aaaaaa' }, splitLine: { lineStyle: { color: '#333' } } }
  ],
  series: [
    {
      type: 'candlestick',
      xAxisIndex: 0, yAxisIndex: 0,
      data: data.map(function(d) { return [d.open, d.close, d.low, d.high]; }),
      itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' }
    },
    {
      type: 'bar',
      xAxisIndex: 1, yAxisIndex: 1,
      data: data.map(function(d) { return d.volume; }),
      itemStyle: {
        color: function(params) {
          var d = data[params.dataIndex];
          return d.close >= d.open ? '#ef5350' : '#26a69a';
        }
      }
    }
  ]
});
```

### 3. Line Chart

For trend analysis, technical indicators, or time series.

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'Trend Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1a1a2e',
    borderColor: '#333',
    textStyle: { color: '#e0e0e0' }
  },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: {
    type: 'category',
    data: data.map(function(d) { return new Date(d.time * 1000).toLocaleDateString(); }),
    axisLabel: { color: '#aaaaaa' },
    axisLine: { lineStyle: { color: '#444' } }
  },
  yAxis: {
    type: 'value',
    scale: true,
    axisLabel: { color: '#aaaaaa' },
    splitLine: { lineStyle: { color: '#333' } }
  },
  series: [{
    type: 'line',
    data: data.map(function(d) { return d.value; }),
    smooth: true,
    lineStyle: { color: '#5470c6', width: 2 },
    itemStyle: { color: '#5470c6' }
  }]
});
```

### 4. Bar Chart

For volume comparisons or categorical data.

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'Bar Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1a1a2e',
    borderColor: '#333',
    textStyle: { color: '#e0e0e0' }
  },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: {
    type: 'category',
    data: data.map(function(d) { return d.label || new Date(d.time * 1000).toLocaleDateString(); }),
    axisLabel: { color: '#aaaaaa', rotate: data.length > 20 ? 45 : 0 },
    axisLine: { lineStyle: { color: '#444' } }
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#aaaaaa' },
    splitLine: { lineStyle: { color: '#333' } }
  },
  series: [{
    type: 'bar',
    data: data.map(function(d) { return d.value; }),
    itemStyle: { color: '#5470c6' }
  }]
});
```

### 5. Area Chart

For cumulative returns or range visualization.

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'Area Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1a1a2e',
    borderColor: '#333',
    textStyle: { color: '#e0e0e0' }
  },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: {
    type: 'category',
    data: data.map(function(d) { return new Date(d.time * 1000).toLocaleDateString(); }),
    axisLabel: { color: '#aaaaaa' },
    axisLine: { lineStyle: { color: '#444' } },
    boundaryGap: false
  },
  yAxis: {
    type: 'value',
    scale: true,
    axisLabel: { color: '#aaaaaa' },
    splitLine: { lineStyle: { color: '#333' } }
  },
  series: [{
    type: 'line',
    data: data.map(function(d) { return d.value; }),
    smooth: true,
    areaStyle: { color: 'rgba(84, 112, 198, 0.3)' },
    lineStyle: { color: '#5470c6', width: 2 },
    itemStyle: { color: '#5470c6' }
  }]
});
```

## Data Formatting Rules

1. **Timestamps**: Keep as Unix epoch seconds (integer). The template converts to locale date string via `new Date(d.time * 1000)`.
2. **Numbers**: Use raw floats. Do not round or format — let ECharts handle axis formatting.
3. **Data limit**: Keep data arrays under 200 points for performance. If the tool returns more, sample or truncate.
4. **Missing values**: Use `null` for missing data points rather than 0 or omitting.

## Workflow

1. User requests a chart (e.g., "draw AAPL K-line on canvas")
2. Call the appropriate data tool (e.g., `dojo.sdk.get_stock_kline(symbol="AAPL")`)
3. Extract the data from the tool result
4. Choose the appropriate chart template above
5. Output your response with a `DOJO_CHART` block containing the data and script
6. The Dashboard frontend will automatically parse the block and render the chart in the Canvas panel

## Example Output

Here is an example of a complete DOJO_CHART output in a response:

````
Here is Apple's recent K-line chart:

```DOJO_CHART
{"data":[{"time":1700000000,"open":189.5,"high":191.2,"low":188.8,"close":190.6,"volume":52000000}],"script":"chart.setOption({backgroundColor:'transparent',title:{text:'AAPL K-Line',textStyle:{color:'#e0e0e0'}},tooltip:{trigger:'axis',backgroundColor:'#1a1a2e',borderColor:'#333',textStyle:{color:'#e0e0e0'}},grid:{left:'10%',right:'5%',bottom:'15%'},xAxis:{type:'category',data:data.map(function(d){return new Date(d.time*1000).toLocaleDateString()}),axisLabel:{color:'#aaaaaa'},axisLine:{lineStyle:{color:'#444'}}},yAxis:{type:'value',scale:true,axisLabel:{color:'#aaaaaa'},splitLine:{lineStyle:{color:'#333'}}},series:[{type:'candlestick',data:data.map(function(d){return [d.open,d.close,d.low,d.high]}),itemStyle:{color:'#ef5350',color0:'#26a69a',borderColor:'#ef5350',borderColor0:'#26a69a'}}]});"}
```

The chart shows Apple stock trending upward.
````
