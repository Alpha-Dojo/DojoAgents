# DojoAgents

DojoAgents is a quantitative finance agent runtime prototype. It provides an
agent loop, pluggable tools and memory, scheduled jobs, a dashboard API, and a
gateway layer for chat adapters.

## Installation

Runtime dependencies are listed in both `pyproject.toml` and
`requirements.txt`.

```bash
pip install -r requirements.txt
```

For local development with `uv`:

```bash
uv run --extra dev python -m pytest -q
```

## CLI

After installing the package, the console entry point is:

```bash
dojoagents --help
```

Main commands:

```bash
dojoagents chat "Analyze BTC market structure" --market crypto --symbols BTC-USD --timeframe 1d
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents gateway setup all
dojoagents gateway --host 127.0.0.1 --port 8766
dojoagents scheduler
```

## Dashboard

The Dashboard provides a Vue 3 SPA frontend with OpenAI-compatible chat API, SSE streaming, and a Canvas panel for dynamic chart rendering.

### Prerequisites

- **Python**: >= 3.11
- **Node.js**: >= 18 (for frontend build)
- **npm**: >= 9

### Build Frontend

```bash
cd dojoagents/dashboard/frontend
npm install
npm run build
```

This compiles the Vue 3 SPA and outputs to `dojoagents/dashboard/static/`, which is served by the FastAPI backend.

### Start Dashboard Server

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Then open [http://127.0.0.1:8765/](http://127.0.0.1:8765/) in your browser.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Redacted configuration |
| `GET` | `/api/jobs` | Scheduled jobs list |
| `GET` | `/api/extensions` | Registered extensions |
| `POST` | `/api/chat` | Chat completion (OpenAI-compatible) |
| `GET` | `/` | Frontend SPA |

### Frontend Development (HMR)

For frontend development with hot-reload:

```bash
cd dojoagents/dashboard/frontend
npm run dev
```

This starts Vite dev server on `http://localhost:5173` with a proxy to the backend at `http://127.0.0.1:8765/api`.

Make sure the backend is running first:

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

The gateway command starts a FastAPI service that exposes:

```text
GET  /api/health
GET  /api/platforms
POST /api/webhook/{platform}
POST /api/send/{platform}/{target}
```

`/api/webhook/{platform}` normalizes an incoming platform payload into a common
gateway event plus a `ChatRequest` shape. `/api/send/{platform}/{target}` sends a
text message through the selected adapter.

Current adapters:

- `slack`
- `wechat`
- `wecom`
- `feishu`
- `discord`
- `telegram`

## Gateway Interactive Setup

Configure all adapters interactively:

```bash
dojoagents gateway setup all
```

Configure one adapter:

```bash
dojoagents gateway setup telegram
dojoagents gateway setup slack
dojoagents gateway setup discord
dojoagents gateway setup feishu
dojoagents gateway setup wecom
dojoagents gateway setup wechat
```

Use a custom config file:

```bash
dojoagents gateway setup all --config ./agents.yaml
```

The setup command follows the Hermes-style gateway setup flow: select or name a
platform, answer the prompts, save `gateway.hooks.<adapter>` in the agents YAML,
then start or restart the gateway.

### Setup Log For All Adapters

```bash
dojoagents gateway setup all
DojoAgents Gateway Setup
Config: /Users/you/.dojo/agents.yaml
Slack Slack bot token: xoxb-...
Slack Default Slack channel: C123
Slack configured
WeChat QR setup
1. DojoAgents requests a Tencent iLink QR login URL.
2. Scan the QR code or open the URL with the WeChat mobile app.
3. Confirm the login, then DojoAgents saves account_id/token/base_url.
Start WeChat QR login now? [y/n] [y]:
WeChat QR login URL: https://ilinkai.weixin.qq.com/...
Scan the QR code or open the URL above with WeChat, then confirm login.
WeChat DM policy [pairing/open/allowlist/disabled] [pairing]: pairing
WeChat group policy [disabled/open/allowlist] [disabled]: disabled
Use WeChat user ID (wechat-user) as home channel? [y/n] [y]: y
WeChat configured via QR login
WeCom WeCom webhook key: wecom-webhook-key
WeCom Default WeCom room/user: room-1
WeCom configured
Feishu Feishu tenant access token: feishu-tenant-access-token
Feishu Feishu receive_id_type [chat_id]: chat_id
Feishu Default Feishu receive_id: oc_chat_id
Feishu configured
Discord Discord bot token: discord-bot-token
Discord Default Discord channel ID: 1234567890
Discord configured
Telegram Telegram bot token: telegram-bot-token
Telegram Default Telegram chat ID: 123456
Telegram configured
Saved gateway configuration to /Users/you/.dojo/agents.yaml
Start the gateway with: dojoagents gateway
```

The saved YAML looks like:

```yaml
gateway:
  enabled: true
  hooks:
    slack:
      enabled: true
      bot_token: xoxb-...
      home_channel: C123
    wechat:
      enabled: true
      account_id: bot-account-id
      token: bot-token
      base_url: https://ilinkai.weixin.qq.com
      dm_policy: pairing
      group_policy: disabled
      home_channel: wechat-user
    wecom:
      enabled: true
      webhook_key: wecom-webhook-key
      home_channel: room-1
    feishu:
      enabled: true
      bot_token: feishu-tenant-access-token
      receive_id_type: chat_id
      home_channel: oc_chat_id
    discord:
      enabled: true
      bot_token: discord-bot-token
      home_channel: "1234567890"
    telegram:
      enabled: true
      bot_token: telegram-bot-token
      home_channel: "123456"
```

### Single Adapter Logs

```bash
dojoagents gateway setup slack
DojoAgents Gateway Setup
Config: /Users/you/.dojo/agents.yaml
Slack Slack bot token: xoxb-...
Slack Default Slack channel: C123
Slack configured
Saved gateway configuration to /Users/you/.dojo/agents.yaml
Start the gateway with: dojoagents gateway

dojoagents gateway setup telegram
DojoAgents Gateway Setup
Config: /Users/you/.dojo/agents.yaml
Telegram Telegram bot token: telegram-bot-token
Telegram Default Telegram chat ID: 123456
Telegram configured
Saved gateway configuration to /Users/you/.dojo/agents.yaml
```

## Model Interactive Setup

Configure LLM provider and connection parameters interactively:

```bash
dojoagents model
```

Use a custom config file:

```bash
dojoagents model --config ./agents.yaml
```

The command allows you to:
1. Select from preset providers (`openai`, `anthropic`, `gemini`, `deepseek`) or define a `custom` endpoint (e.g. Ollama, llama.cpp, vLLM).
2. Override the Base URL.
3. Enter the API Key securely (using masked input).
4. Probe the endpoint to fetch available models and select from a list.
5. Save the configuration directly inside `~/.dojo/agents.yaml` under the `llm_provider` block.

## Gateway Config Location

The default config file is:

```text
~/.dojo/agents.yaml
```

Gateway settings live under `gateway.hooks`. You can still edit the YAML by
hand, but `dojoagents gateway setup ...` is the recommended path because it
prompts for the fields each adapter needs.

```yaml
gateway:
  enabled: true
  hooks:
    telegram:
      enabled: true
      bot_token: "${TELEGRAM_BOT_TOKEN}"
    slack:
      enabled: true
      bot_token: "${SLACK_BOT_TOKEN}"
```
