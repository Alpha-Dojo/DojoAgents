# Dashboard 部署

## 本地部署

先构建前端：

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

再启动后端：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## 网络暴露

默认建议只绑定 `127.0.0.1`。如果要绑定外网地址，需要先确认：

- 模型 API key 不会通过配置接口泄露。
- Dashboard 已部署在可信网络或有额外认证层。
- 工具执行权限符合当前 sandbox policy。
- 日志不会输出 secrets。

## 健康检查

```text
GET /api/health
```

