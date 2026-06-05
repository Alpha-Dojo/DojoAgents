"""Dashboard Canvas Protocol — injected into Agent system prompt when channel='dashboard'.

This module defines the DOJO_CHART rendering protocol that teaches the Agent
how to output chart data for the Dashboard Canvas panel. It is injected
directly into the system prompt by AgentLoop, bypassing the skill system
to guarantee the Agent always knows about it in dashboard context.
"""
from __future__ import annotations

DASHBOARD_CANVAS_PROTOCOL = """
## Dashboard Canvas Chart Rendering Protocol

You have access to a Canvas panel in the Dashboard that can render interactive ECharts visualizations.
When the user asks you to draw a chart, graph, or visualization on the canvas, you MUST output a `DOJO_CHART` code block in your text response.

### DOJO_CHART Protocol

Output a fenced code block with language tag `DOJO_CHART` containing a JSON object:

````
```DOJO_CHART
{"data": <chart_data_array>, "script": "<echarts_render_script>"}
```
````

**`data` field**: An array of data points.
- For K-line/OHLCV: `[{"time": <unix_ts>, "open": <n>, "high": <n>, "low": <n>, "close": <n>, "volume": <n>}, ...]`
- For line/bar/area: `[{"time": <unix_ts>, "value": <n>}, ...]`

**`script` field**: A JavaScript function body string. The sandbox provides three variables:
- `chart` — an initialized ECharts instance (do NOT call `echarts.init()`)
- `data` — the data array from above
- `echarts` — the global ECharts library reference

Your script MUST call `chart.setOption({...})` to render.

### Dark Theme

Always use dark theme colors:
- `backgroundColor: 'transparent'`
- `textStyle: { color: '#e0e0e0' }`
- `axisLabel: { color: '#aaaaaa' }`
- `splitLine: { lineStyle: { color: '#333' } }`
- `tooltip: { backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#e0e0e0' } }`
- K-line colors: bullish `#ef5350`, bearish `#26a69a`

### K-Line (Candlestick) Template

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'K-Line Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#e0e0e0' } },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: { type: 'category', data: data.map(function(d) { return new Date(d.time * 1000).toLocaleDateString(); }), axisLabel: { color: '#aaaaaa' }, axisLine: { lineStyle: { color: '#444' } } },
  yAxis: { type: 'value', scale: true, axisLabel: { color: '#aaaaaa' }, splitLine: { lineStyle: { color: '#333' } } },
  series: [{ type: 'candlestick', data: data.map(function(d) { return [d.open, d.close, d.low, d.high]; }), itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' } }]
});
```

### Line Chart Template

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'Trend Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: { trigger: 'axis', backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#e0e0e0' } },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: { type: 'category', data: data.map(function(d) { return new Date(d.time * 1000).toLocaleDateString(); }), axisLabel: { color: '#aaaaaa' }, axisLine: { lineStyle: { color: '#444' } } },
  yAxis: { type: 'value', scale: true, axisLabel: { color: '#aaaaaa' }, splitLine: { lineStyle: { color: '#333' } } },
  series: [{ type: 'line', data: data.map(function(d) { return d.value; }), smooth: true, lineStyle: { color: '#5470c6', width: 2 }, itemStyle: { color: '#5470c6' } }]
});
```

### Bar Chart Template

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'Bar Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: { trigger: 'axis', backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#e0e0e0' } },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: { type: 'category', data: data.map(function(d) { return d.label || new Date(d.time * 1000).toLocaleDateString(); }), axisLabel: { color: '#aaaaaa' }, axisLine: { lineStyle: { color: '#444' } } },
  yAxis: { type: 'value', axisLabel: { color: '#aaaaaa' }, splitLine: { lineStyle: { color: '#333' } } },
  series: [{ type: 'bar', data: data.map(function(d) { return d.value; }), itemStyle: { color: '#5470c6' } }]
});
```

### Area Chart Template

```javascript
chart.setOption({
  backgroundColor: 'transparent',
  title: { text: 'Area Chart', textStyle: { color: '#e0e0e0' } },
  tooltip: { trigger: 'axis', backgroundColor: '#1a1a2e', borderColor: '#333', textStyle: { color: '#e0e0e0' } },
  grid: { left: '10%', right: '5%', bottom: '15%' },
  xAxis: { type: 'category', data: data.map(function(d) { return new Date(d.time * 1000).toLocaleDateString(); }), axisLabel: { color: '#aaaaaa' }, axisLine: { lineStyle: { color: '#444' } }, boundaryGap: false },
  yAxis: { type: 'value', scale: true, axisLabel: { color: '#aaaaaa' }, splitLine: { lineStyle: { color: '#333' } } },
  series: [{ type: 'line', data: data.map(function(d) { return d.value; }), smooth: true, areaStyle: { color: 'rgba(84, 112, 198, 0.3)' }, lineStyle: { color: '#5470c6', width: 2 }, itemStyle: { color: '#5470c6' } }]
});
```

### Workflow

1. Use data tools (e.g. `dojo_sdk_get_stock_kline`, `dojo_sdk_get_kline`) to fetch data
2. Extract the data array from the tool result
3. Choose the appropriate chart template above
4. Output a `DOJO_CHART` block with the data and script in your text response
5. The Dashboard will automatically render the chart in the Canvas panel

### Example Output

````
Here is Apple's K-line chart:

```DOJO_CHART
{"data":[{"time":1700000000,"open":189.5,"high":191.2,"low":188.8,"close":190.6,"volume":52000000}],"script":"chart.setOption({backgroundColor:'transparent',title:{text:'AAPL K-Line',textStyle:{color:'#e0e0e0'}},tooltip:{trigger:'axis',backgroundColor:'#1a1a2e',borderColor:'#333',textStyle:{color:'#e0e0e0'}},grid:{left:'10%',right:'5%',bottom:'15%'},xAxis:{type:'category',data:data.map(function(d){return new Date(d.time*1000).toLocaleDateString()}),axisLabel:{color:'#aaaaaa'},axisLine:{lineStyle:{color:'#444'}}},yAxis:{type:'value',scale:true,axisLabel:{color:'#aaaaaa'},splitLine:{lineStyle:{color:'#333'}}},series:[{type:'candlestick',data:data.map(function(d){return [d.open,d.close,d.low,d.high]}),itemStyle:{color:'#ef5350',color0:'#26a69a',borderColor:'#ef5350',borderColor0:'#26a69a'}}]});"}
```
````

### Rules

- Keep data arrays under 200 points for performance.
- Use Unix epoch seconds for timestamps.
- Do NOT call `echarts.init()` — the chart is already initialized.
- Do NOT create standalone HTML files — use the DOJO_CHART protocol instead.
""".strip()
