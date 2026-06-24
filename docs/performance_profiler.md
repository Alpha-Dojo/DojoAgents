# DojoAgents 性能剖析工具 (Performance Profiler) 使用指南

DojoAgents 内置了一个开销极低、基于 `pyinstrument` 的性能剖析工具，它可以帮助开发者快速定位和分析服务端点（例如查询比较慢的接口）的性能瓶颈。

该工具已被集成在系统的 FastAPI Middleware 层中，不会侵入具体的业务逻辑代码。你可以通过以下两种方式灵活地触发 Profiler。

## 1. 单次请求触发（推荐，用于局部调试）

如果你正在调试某个特定的 API 请求，可以直接通过在请求 URL 中附加参数来触发。

### 操作方法
在任意 HTTP 请求 URL 后面加上参数 `?profile=1` 或者 `&profile=1`。

**示例**：
原本比较慢的接口：
```text
http://127.0.0.1:8765/api/v1/dojo-sphere/sectors/constituents?level1_id=1&level2_id=13&level3_id=17&market=us&scope=L3
```
增加 profile 参数：
```text
http://127.0.0.1:8765/api/v1/dojo-sphere/sectors/constituents?level1_id=1&level2_id=13&level3_id=17&market=us&scope=L3&profile=1
```

### 输出效果
- 当带上 `profile=1` 参数时，中间件将**拦截**服务端本来应该返回的 JSON 数据。
- 它会直接在 HTTP Response 中返回一个可交互的 HTML 格式的**调用栈火焰图**。
- 如果你是在浏览器中打开这个 URL，你可以非常直观地点击查看每一个内部函数、协程、甚至具体哪一行的执行消耗时间。

## 2. 全局配置触发（用于系统级压力监控）

如果你需要监控前端面板产生的所有的真实 API 流量或者难以通过 URL 参数复现复杂请求时，可以通过修改全局配置开启 Profiler。

### 操作方法
在你的 `agents.yaml` 或者运行时全局配置中（具体的注入依赖在系统 `dashboard` 中进行读取），加入配置标记：
```yaml
dashboard:
  profiler:
    enabled: true
```

### 输出效果
- 当全局启用后，中间件会针对**所有**到达后端的 API 请求进行统计剖析。
- 为了**不破坏原本的前端业务**，接口将继续正常返回 JSON。
- 生成的 Profiler HTML 报告会被自动写入本地磁盘：
  - 默认保存路径为：`~/.dojo/data/profiles/`（如果设置了 `DOJO_CACHE_DIR` 环境变量，则保存在该目录下的 `profiles/` 文件夹中）。
  - 文件命名格式为：`profile_<endpoint_path>_<timestamp>.html`
- 你可以在后续的任何时间，用浏览器打开这些生成的 `.html` 文件进行复盘分析。

## 环境和依赖要求
使用该功能需要保障你的运行环境中已经安装了 `pyinstrument` 库：
```bash
pip install pyinstrument
```
（该依赖通常已在当前工程中预装，如遇模块缺失请手动补充安装。）
