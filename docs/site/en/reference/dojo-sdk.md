# DojoSDK

DojoAgents integrates DojoSDK through the `dojosdk` dependency and `dojoagents/tools/dojo_sdk_tool.py`.

The current `uv` source override is:

```toml
[tool.uv.sources]
dojosdk = { path = "../DojoSDK" }
```

Dashboard Dojo data gateway errors are defined in `dojoagents/dashboard/services/dojo_data_gateway.py`.

