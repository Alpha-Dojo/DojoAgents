# DojoAgents Model CLI Configuration Guide

This guide details how to implement interactive model connection configuration inside the `dojoagents` command-line interface. 

In DojoAgents, all configuration parameters—including LLM provider details, base URLs, and API keys—are centrally stored and managed under a single configuration file: `~/.dojo/agents.yaml`.

---

## 1. Architectural Strategy

To enable users to configure model endpoints interactively:
1.  **Add Subcommand**: Add a `model` subcommand to the main `dojoagents` CLI parser in [dojoagents/cli/main.py](file:///Users/kk1999/Local_Documents/code/alphadojo/DojoAgents/dojoagents/cli/main.py).
2.  **Interactive Configuration Manager**: Implement a new file `dojoagents/cli/model_setup.py` containing the logic for selection menus, credential input, base URL override, and endpoint probing.
3.  **Single-File Config updates**: Update the `llm_provider` block in `~/.dojo/agents.yaml` directly using `ConfigStore`. API keys entered interactively are stored directly under the corresponding provider key as `api_key: <key_value>`, rather than utilizing separate dotenv files.

---

## 2. Step-by-Step Implementation Plan

### Step 1: Update CLI Parser to support `dojoagents model`
We need to register a new `model` subcommand in `dojoagents/cli/main.py`.

```python
# In dojoagents/cli/main.py

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dojoagents")
    sub = parser.add_subparsers(dest="command", required=True)
    
    # ... existing commands (chat, dashboard, gateway, scheduler) ...

    # Add the model config command
    model_parser = sub.add_parser("model", help="Configure default LLM provider and connection parameters")
    model_parser.add_argument("--config", default="~/.dojo/agents.yaml", help="Path to config file")

    return parser
```

Then update `main(argv)` to dispatch the `model` command:

```python
# In dojoagents/cli/main.py (dispatch section)

    if args.command == "model":
        from dojoagents.cli.model_setup import configure_model_connection
        return configure_model_connection(config_path=args.config)
```

---

### Step 2: Implement Interactive Flow in `dojoagents/cli/model_setup.py`
Create a new file `dojoagents/cli/model_setup.py` to handle the configuration menus:

```python
# [NEW] dojoagents/cli/model_setup.py

import getpass
import httpx
from pathlib import Path
from typing import Any
import yaml

from dojoagents.config.loader import ConfigStore

# Supported Preset Providers
PRESET_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o"
    },
    "anthropic": {
        "label": "Anthropic",
        "default_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-latest"
    },
    "gemini": {
        "label": "Google Gemini",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-1.5-pro"
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat"
    }
}

def probe_endpoint_models(base_url: str, api_key: str) -> list[str]:
    """Verify endpoint and probe available models using /models endpoint."""
    url = f"{base_url.rstrip('/')}/models"
    headers = {}
    if api_key:
        # Standard Bearer auth header
        headers["Authorization"] = f"Bearer {api_key}"
        
    try:
        print("Probing endpoint for available models...")
        response = httpx.get(url, headers=headers, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            # Handle standard OpenAI /models response structure
            if isinstance(data, dict) and "data" in data:
                return [m["id"] for m in data["data"] if isinstance(m, dict) and "id" in m]
    except Exception as e:
        print(f"Warning: Endpoint validation probe failed: {e}")
    return []

def configure_model_connection(config_path: str = "~/.dojo/agents.yaml") -> int:
    store = ConfigStore(config_path)
    raw = store.raw()
    llm_section = raw.setdefault("llm_provider", {})
    providers_section = llm_section.setdefault("providers", {})
    
    current_default = llm_section.get("default", "openai")
    print(f"Current default provider: {current_default}")
    print()
    
    # 1. Select Provider
    print("Select LLM Provider:")
    options = list(PRESET_PROVIDERS.keys()) + ["custom"]
    for i, opt in enumerate(options, 1):
        label = PRESET_PROVIDERS[opt]["label"] if opt in PRESET_PROVIDERS else "Custom Endpoint"
        print(f"  {i}. {label}")
    
    try:
        choice = input(f"Choice [1-{len(options)}]: ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(options):
            print("Invalid selection.")
            return 1
        provider_id = options[idx]
    except (ValueError, KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 1

    # Initialize provider info
    if provider_id == "custom":
        name = input("Custom provider name (e.g. ollama): ").strip().lower()
        if not name:
            print("Name required. Cancelled.")
            return 1
        provider_id = name
        default_url = "http://localhost:11434/v1"
        default_model = "llama3"
    else:
        preset = PRESET_PROVIDERS[provider_id]
        default_url = preset["default_url"]
        default_model = preset["default_model"]

    # Retrieve current config for provider
    current_prov_cfg = providers_section.get(provider_id, {})
    current_base = current_prov_cfg.get("base_url") or default_url
    current_key = current_prov_cfg.get("api_key") or ""
    current_model = current_prov_cfg.get("model") or default_model
    
    # 2. Prompt for Base URL
    try:
        base_url = input(f"Base URL [{current_base}]: ").strip() or current_base
        if not base_url.startswith(("http://", "https://")):
            print("Error: URL must start with http:// or https://")
            return 1
            
        # 3. Prompt for API Key
        key_masked = current_key[:8] + "..." if len(current_key) > 8 else "optional"
        api_key = getpass.getpass(f"API Key for {provider_id} [{key_masked}]: ").strip()
        
        effective_key = api_key if api_key else current_key
            
        # 4. Probe Endpoint and Pick Model
        available_models = probe_endpoint_models(base_url, effective_key)
        selected_model = ""
        if available_models:
            print("\nAvailable models on endpoint:")
            for i, m in enumerate(available_models[:15], 1):
                print(f"  {i}. {m}")
            print(f"  {len(available_models) + 1}. Enter custom model name")
            
            pick = input(f"Select model [1-{len(available_models) + 1}]: ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(available_models):
                selected_model = available_models[int(pick) - 1]
            else:
                selected_model = input("Model name: ").strip()
        else:
            selected_model = input(f"Model name [{current_model}]: ").strip() or current_model
            
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 1

    # 5. Save settings to agents.yaml
    prov_cfg = {
        "model": selected_model,
        "base_url": base_url,
    }
    if effective_key:
        prov_cfg["api_key"] = effective_key
    else:
        # Keep api_key_env if present
        if "api_key_env" in current_prov_cfg:
            prov_cfg["api_key_env"] = current_prov_cfg["api_key_env"]
            
    providers_section[provider_id] = prov_cfg
    llm_section["default"] = provider_id
    
    # Update agent default model
    raw.setdefault("agent", {})["model"] = selected_model
    
    store.save_raw(raw)
    print()
    print(f"✓ Configuration successfully saved to {store.path}")
    print(f"  Active Provider: {provider_id}")
    print(f"  Active Model:    {selected_model}")
    print(f"  API Base URL:    {base_url}")
    return 0
```

---

## 3. Benefits of this Design for DojoAgents

*   **Single Source of Truth**: Simplifies the codebase by centralizing all setups (including active secrets and keys) inside a unified `agents.yaml` under `~/.dojo/`, avoiding synchronization issues.
*   **Reduced Configuration Mistakes**: Live endpoint probing via `/models` prevents spelling mistakes and connection errors, immediately verifying connection compatibility.
*   **Flexibility**: Supports standard presets (OpenAI, Anthropic, Gemini, DeepSeek) while seamlessly facilitating local dev runners (Ollama, llama.cpp, LocalAI) through the "custom" provider flow.
