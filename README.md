<div align="center">
  <img src="https://github.com/Alpha-Dojo/DojoAgents/blob/main/dojoagents/dashboard/web/public/logo.png" alt="DojoAgents Logo">
</div>

<p align="center">
  <a href="https://discord.gg/CCRvSvdvr"><img src="https://img.shields.io/badge/Discord-DojoAgents-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://weixin.qq.com/YOUR_LINK"><img src="https://img.shields.io/badge/WeChat-DojoAgents-4CB55E?logo=wechat&logoColor=white" alt="WeChat"></a>
  <a href="https://huggingface.co/AlphaDojo"><img src="https://img.shields.io/badge/HuggingFace-DojoAgents-FFD21E?logo=huggingface&logoColor=000000" alt="HuggingFace"></a>
  <a href="https://github.com/Alpha-Dojo/DojoAgents/blob/main/docs/README.md"><img src="https://img.shields.io/badge/Join%20GitHub%20Community-DojoAgents-2ea44f?logo=github&logoColor=white" alt="GitHub Community"></a>
</p>

---

# DojoAgents: Full-Market AI Copilot for Personal Investment

DojoAgents is a full-market AI agent framework designed specifically for personal investment. Built to bridge the gap between individual investors and institutional-grade tools, its true powerhouse is a state-of-the-art Agent Loop engine. Instead of a simple dashboard, DojoAgents deploys an autonomous reasoning agent that lives alongside your portfolio, handling everything from full-market data cognition to dynamic cross-market strategy deduction.

## ✨ Why DojoAgents?

**🧠 Loop-Driven Cognitive Portfolio Agent (Our Core Engine):** Powered by advanced Loop-Engineering, this is not a basic Q&A bot. It is an iterative reasoning engine deeply integrated with your portfolio, capable of executing complex financial workflows across four dimensions:
* **Fundamental Data Cognition:** Instantly fetches, structures, and cross-references raw multi-market data (K-lines, financials, news).
* **Advanced Logic Analysis:** Interprets valuation bands, momentum indicators, and sector taxonomy to uncover hidden market mechanics.
* **Cross-Market Strategy Deduction:** Formulates macro asset allocation and maps market linkages (e.g., autonomously reasoning through *"Why US semiconductor software dropped while A-shares surged"* via multi-step tool execution).
* **Dynamic Portfolio Management:** Continuously diagnoses risk exposure, monitors net-worth curves, and evaluates performance attribution for optimal rebalancing.

**📊 Four-Pillar Dashboard:** An out-of-the-box, institutional-grade React SPA featuring:
- **Portfolio (The Command Center):** Net worth curves, live risk exposure, and smart position tracking.
- **Markets:** Cross-market heatmaps (US/HK/A-shares) and index tracking.
- **Sectors:** Deep-dive L1/L2/L3 taxonomy and momentum curves.
- **Equities:** K-lines, PE bands, financials, and news—all in one unified view.

**🤖 Autonomous Quant Analyst:** Powered by multi-agent collaboration, it autonomously conducts background market research, tracks sector rotations, and monitors your risk exposure while you sleep.

**📱 Omnichannel & Always On:** Get personalized daily briefings or real-time alert pushes directly to your Slack, Telegram, Discord, Feishu, or WeChat.

## 🚀 Quick Start

Deploying your DojoAgents environment is designed to be frictionless. We strongly recommend using uv for lightning-fast dependency management.

### 1. Requirements

- **Python** >= 3.11
- **Node.js**: >= 18 (for frontend build)
- **npm**: >= 9
- An LLM **API Key** (OpenAI, Gemini, Anthropic, etc.)

### 2. Core Installation

Runtime dependencies are listed in both `pyproject.toml` and `requirements.txt`.

```bash
# 1. Create and activate a virtual environment
uv venv && source .venv/bin/activate

# 2. OPTION - For Developers & Contributors:
# Install in "editable mode" with dev tools. Any source code changes will take 
# effect immediately—perfect for building custom tools or debugging the Agent Loop.
uv pip install -e ".[dev]"

# 3. Install the core dependencies.
uv pip install -r requirements.txt
```

### 3. Dashboard Build

The DojoAgents Dashboard is a high-performance React SPA powered by Vite, communicating with a FastAPI backend via an OpenAI-compatible chat API and SSE streaming for dynamic Canvas chart rendering.

If you are building from source, you will need Node.js (>= 18) and npm (>= 9).
```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

### 4. Launching the Server

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/ in your browser to access your personal financial command center.

### 5. Configure Your LLM Engine (In-App)

Once the dashboard is live, click on the Settings icon. DojoAgents features a comprehensive graphical interface to securely configure your preferred Large Language Models.

- **Supported Providers**: Out-of-the-box presets for OpenAI, Anthropic, Google Gemini, Zhipu GLM, and DeepSeek.
- **Local & Custom Endpoints**: Easily override Base URLs to connect to local instances like Ollama, llama.cpp, or vLLM.
- **Secure Storage**: All API keys and endpoint settings entered in the UI are securely written to your local ~/.dojo/agents.yaml file.


## 🧠 Core Architecture

DojoAgents is engineered for scale, deep contextual reasoning, and absolute privacy.

- **Agent Loop Engine:** The core reasoning runtime. Handles multi-turn tool orchestration, context window compression, and strict guardrails to prevent financial hallucinations.
- **Execution Sandbox:** A secure, isolated environment for on-the-fly Python code execution, technical indicator calculations, and local web data extraction.
- **Memory & SKILLS:** Automatically distills successful, multi-step market analysis workflows into reusable, programmatic SKILLS for future execution.
- **Cron & Gateway:** Decoupled delivery pipelines that push scheduled, automated insights directly to your preferred chat applications, without blocking the main Agent reasoning loop.


## 📚 Documentation & Deep Dives

Ready to build custom quantitative skills, integrate proprietary data, or deploy a multi-agent swarm? Dive into our comprehensive developer guides:

- System Architecture & Design Philosophy
- Writing Custom Plugins & Claude Skills
- Chat Gateways & Omnichannel Setup
- Dashboard UI Customization Guide

## 🤝 Contributing

We are building the ultimate open-source financial AI, and we'd love your help! Check out our Contribution Guidelines to see how you can add new tools, refine the agent prompts, or expand market coverage.

**License:** DojoAgents is open-source under the Apache License 2.0.
