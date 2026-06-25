from __future__ import annotations
from dojoagents.logging import LOGGER

import getpass
from pathlib import Path

import httpx

from dojoagents.config.loader import ConfigStore

# Supported Preset Providers
PRESET_PROVIDERS = {
    "openai": {"label": "OpenAI", "default_url": "https://api.openai.com/v1", "default_model": "gpt-4o"},
    "anthropic": {"label": "Anthropic", "default_url": "https://api.anthropic.com/v1", "default_model": "claude-3-5-sonnet-latest"},
    "gemini": {"label": "Google Gemini", "default_url": "https://generativelanguage.googleapis.com/v1beta", "default_model": "gemini-1.5-pro"},
    "deepseek": {"label": "DeepSeek", "default_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"},
    "glm": {"label": "GLM (ZhipuAI)", "default_url": "https://open.bigmodel.cn/api/paas/v4/", "default_model": "glm-4"},
    "minimax": {"label": "MiniMax", "default_url": "https://api.minimax.chat/v1", "default_model": "abab6.5-chat"},
    "kimi": {"label": "Kimi (Moonshot)", "default_url": "https://api.moonshot.cn/v1", "default_model": "moonshot-v1-8k"},
}


def probe_endpoint_models(base_url: str, api_key: str) -> list[str]:
    """Verify endpoint and probe available models using /models endpoint."""
    url = f"{base_url.rstrip('/')}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        LOGGER.info("Probing endpoint for available models...")
        response = httpx.get(url, headers=headers, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                return [m["id"] for m in data["data"] if isinstance(m, dict) and "id" in m]
    except Exception as e:
        LOGGER.info(f"Warning: Endpoint validation probe failed: {e}")
    return []


def configure_model_connection(config_path: str | Path = "~/.dojo/agents.yaml") -> int:
    store = ConfigStore(config_path)
    raw = store.raw()
    llm_section = raw.setdefault("llm_provider", {})
    providers_section = llm_section.setdefault("providers", {})

    current_default = llm_section.get("default", "openai")
    LOGGER.info(f"Current default provider: {current_default}")
    LOGGER.info()

    # 1. Select Provider
    LOGGER.info("Select LLM Provider:")
    options = list(PRESET_PROVIDERS.keys()) + ["custom"]
    for i, opt in enumerate(options, 1):
        label = PRESET_PROVIDERS[opt]["label"] if opt in PRESET_PROVIDERS else "Custom Endpoint"
        LOGGER.info(f"  {i}. {label}")

    try:
        choice = input(f"Choice [1-{len(options)}]: ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(options):
            LOGGER.info("Invalid selection.")
            return 1
        provider_id = options[idx]
    except (ValueError, KeyboardInterrupt, EOFError):
        LOGGER.info("\nCancelled.")
        return 1

    # Initialize provider info
    if provider_id == "custom":
        name = input("Custom provider name (e.g. ollama): ").strip().lower()
        if not name:
            LOGGER.info("Name required. Cancelled.")
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
            LOGGER.info("Error: URL must start with http:// or https://")
            return 1

        # 3. Prompt for API Key
        key_masked = current_key[:8] + "..." if len(current_key) > 8 else "optional"
        api_key = getpass.getpass(f"API Key for {provider_id} [{key_masked}]: ").strip()

        effective_key = api_key if api_key else current_key

        # 4. Probe Endpoint and Pick Model
        available_models = probe_endpoint_models(base_url, effective_key)
        selected_model = ""
        if available_models:
            LOGGER.info("\nAvailable models on endpoint:")
            for i, m in enumerate(available_models[:15], 1):
                LOGGER.info(f"  {i}. {m}")
            LOGGER.info(f"  {len(available_models) + 1}. Enter custom model name")

            pick = input(f"Select model [1-{len(available_models) + 1}]: ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(available_models):
                selected_model = available_models[int(pick) - 1]
            else:
                selected_model = input("Model name: ").strip()
        else:
            selected_model = input(f"Model name [{current_model}]: ").strip() or current_model

    except (KeyboardInterrupt, EOFError):
        LOGGER.info("\nCancelled.")
        return 1

    # 5. Save settings to agents.yaml
    prov_cfg = {
        "model": selected_model,
        "base_url": base_url,
    }
    if effective_key:
        prov_cfg["api_key"] = effective_key
    else:
        if "api_key_env" in current_prov_cfg:
            prov_cfg["api_key_env"] = current_prov_cfg["api_key_env"]

    providers_section[provider_id] = prov_cfg
    llm_section["default"] = provider_id

    # Update agent default model
    raw.setdefault("agent", {})["model"] = selected_model

    store.save_raw(raw)
    LOGGER.info()
    LOGGER.info(f"✓ Configuration successfully saved to {store.path}")
    LOGGER.info(f"  Active Provider: {provider_id}")
    LOGGER.info(f"  Active Model:    {selected_model}")
    LOGGER.info(f"  API Base URL:    {base_url}")
    return 0
