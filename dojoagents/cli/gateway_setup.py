from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Protocol

import httpx

from dojoagents.config.loader import ConfigStore


ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"
QR_TIMEOUT_SECONDS = 35.0


@dataclass(frozen=True)
class SetupField:
    key: str
    prompt: str
    secret: bool = False
    default: str = ""


@dataclass(frozen=True)
class AdapterSetupSpec:
    name: str
    label: str
    fields: tuple[SetupField, ...]


ADAPTER_SETUP_SPECS: tuple[AdapterSetupSpec, ...] = (
    AdapterSetupSpec(
        name="slack",
        label="Slack",
        fields=(
            SetupField("bot_token", "Slack bot token"),
            SetupField("home_channel", "Default Slack channel"),
        ),
    ),
    AdapterSetupSpec(
        name="wechat",
        label="WeChat",
        fields=(),
    ),
    AdapterSetupSpec(
        name="wecom",
        label="WeCom",
        fields=(
            SetupField("webhook_key", "WeCom webhook key"),
            SetupField("home_channel", "Default WeCom room/user"),
        ),
    ),
    AdapterSetupSpec(
        name="feishu",
        label="Feishu",
        fields=(
            SetupField("bot_token", "Feishu tenant access token"),
            SetupField("receive_id_type", "Feishu receive_id_type", default="chat_id"),
            SetupField("home_channel", "Default Feishu receive_id"),
        ),
    ),
    AdapterSetupSpec(
        name="discord",
        label="Discord",
        fields=(
            SetupField("bot_token", "Discord bot token"),
            SetupField("home_channel", "Default Discord channel ID"),
        ),
    ),
    AdapterSetupSpec(
        name="telegram",
        label="Telegram",
        fields=(
            SetupField("bot_token", "Telegram bot token"),
            SetupField("home_channel", "Default Telegram chat ID"),
        ),
    ),
)

_SPECS_BY_NAME = {spec.name: spec for spec in ADAPTER_SETUP_SPECS}


class WeChatQRClient(Protocol):
    async def login(self) -> dict[str, str]:
        """Run the QR login flow and return iLink account credentials."""


class WeChatQRLoginClient:
    """Small synchronous iLink QR login client for CLI setup.

    Hermes keeps the production Weixin transport async and feature-rich. For
    DojoAgents setup we only need the registration handshake: request a QR URL,
    let the user scan it with WeChat, then poll until iLink returns bot
    credentials.
    """

    def __init__(
        self,
        *,
        base_url: str = ILINK_BASE_URL,
        bot_type: str = "3",
        http_client: httpx.AsyncClient | None = None,
        poll_interval_seconds: float = 2.0,
        max_attempts: int = 90,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bot_type = bot_type
        self.http_client = http_client
        self.poll_interval_seconds = poll_interval_seconds
        self.max_attempts = max_attempts

    async def login(self) -> dict[str, str]:
        qr = await self._fetch_qr()
        qrcode = qr.get("qrcode") or qr.get("qr_code") or qr.get("uuid")
        qr_url = (
            qr.get("qrcode_img_content")
            or qr.get("qrcode_url")
            or qr.get("url")
            or qrcode
        )
        if not qrcode or not qr_url:
            raise RuntimeError("iLink did not return a usable WeChat QR code.")

        print("WeChat QR login URL: " + str(qr_url))
        print("Scan the QR code or open the URL above with WeChat, then confirm login.")

        current_base_url = self.base_url
        refresh_count = 0
        for _ in range(self.max_attempts):
            status = await self._fetch_status(str(qrcode), base_url=current_base_url)
            status_name = str(
                status.get("status") or status.get("qrcode_status") or "wait"
            ).lower()
            if status_name in {"confirmed", "confirm", "success"}:
                credentials = self._extract_credentials(status)
                if credentials:
                    return credentials
                raise RuntimeError("WeChat QR login succeeded but credentials were missing.")
            if status_name == "scaned_but_redirect":
                redirect_host = str(status.get("redirect_host") or "").strip()
                if redirect_host:
                    current_base_url = f"https://{redirect_host}"
            elif status_name in {"expired", "timeout", "canceled", "cancelled"}:
                refresh_count += 1
                if refresh_count > 3:
                    raise RuntimeError("WeChat QR login expired before confirmation.")
                print(f"WeChat QR code expired; refreshing ({refresh_count}/3)...")
                qr = await self._fetch_qr()
                qrcode = qr.get("qrcode") or qr.get("qr_code") or qr.get("uuid")
                qr_url = (
                    qr.get("qrcode_img_content")
                    or qr.get("qrcode_url")
                    or qr.get("url")
                    or qrcode
                )
                if not qrcode or not qr_url:
                    raise RuntimeError("iLink did not return a usable WeChat QR code.")
                print("WeChat QR login URL: " + str(qr_url))
            if status_name in {"scaned", "scanned", "scaned_but_redirect"}:
                print("WeChat scan detected; waiting for phone confirmation...")
            await asyncio.sleep(self.poll_interval_seconds)

        raise RuntimeError("Timed out waiting for WeChat QR login confirmation.")

    async def _fetch_qr(self) -> dict[str, Any]:
        return await self._get_json(EP_GET_BOT_QR, {"bot_type": self.bot_type})

    async def _fetch_status(
        self, qrcode: str, *, base_url: str | None = None
    ) -> dict[str, Any]:
        return await self._get_json(
            EP_GET_QR_STATUS,
            {"qrcode": qrcode},
            base_url=base_url,
        )

    async def _get_json(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        *,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        url = f"{(base_url or self.base_url).rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }
        try:
            if self.http_client is not None:
                response = await self.http_client.get(
                    url,
                    params=params,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(timeout=QR_TIMEOUT_SECONDS, trust_env=True) as client:
                    response = await client.get(
                        url,
                        params=params,
                        headers=headers,
                    )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"WeChat iLink request failed: {exc}") from exc

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("WeChat iLink returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("WeChat iLink returned a non-object JSON response.")
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise RuntimeError("WeChat iLink response did not contain an object payload.")
        return data

    def _extract_credentials(self, status: dict[str, Any]) -> dict[str, str]:
        data = status.get("data", status)
        if not isinstance(data, dict):
            return {}
        account_id = data.get("ilink_bot_id") or data.get("account_id")
        token = data.get("bot_token") or data.get("token")
        if not account_id or not token:
            return {}
        return {
            "account_id": str(account_id),
            "token": str(token),
            "base_url": str(data.get("baseurl") or data.get("base_url") or self.base_url),
            "user_id": str(data.get("ilink_user_id") or data.get("user_id") or ""),
        }


def adapter_names() -> list[str]:
    return list(_SPECS_BY_NAME)


def configure_gateway_adapters(
    adapter: str,
    *,
    config_path: str | Path = "~/.dojo/agents.yaml",
    wechat_qr_client: WeChatQRClient | None = None,
) -> int:
    selected = list(ADAPTER_SETUP_SPECS) if adapter == "all" else [_SPECS_BY_NAME.get(adapter)]
    if not selected or selected[0] is None:
        print(f"Unknown adapter: {adapter}")
        print(f"Available adapters: {', '.join(adapter_names())}, all")
        return 2

    store = ConfigStore(config_path)
    raw = store.raw()
    gateway = raw.setdefault("gateway", {})
    gateway["enabled"] = True
    hooks = gateway.setdefault("hooks", {})

    print("DojoAgents Gateway Setup")
    print(f"Config: {store.path}")
    for spec in selected:
        assert spec is not None
        if spec.name == "wechat":
            hooks[spec.name] = _prompt_for_wechat(
                hooks.get(spec.name, {}),
                wechat_qr_client or WeChatQRLoginClient(),
            )
        else:
            hooks[spec.name] = _prompt_for_adapter(spec, hooks.get(spec.name, {}))
            print(f"{spec.label} configured")

    store.save_raw(raw)
    print(f"Saved gateway configuration to {store.path}")
    print("Start the gateway with: dojoagents gateway")
    return 0


def _prompt_for_adapter(
    spec: AdapterSetupSpec,
    existing: dict[str, Any],
) -> dict[str, Any]:
    values: dict[str, Any] = {"enabled": True}
    for field in spec.fields:
        current = str(existing.get(field.key, field.default) or "")
        suffix = f" [{current}]" if current else ""
        answer = input(f"{spec.label} {field.prompt}{suffix}: ").strip()
        values[field.key] = answer or current
    return values


def _prompt_for_wechat(
    existing: dict[str, Any],
    qr_client: WeChatQRClient,
) -> dict[str, Any]:
    print("WeChat QR setup")
    print("1. DojoAgents requests a Tencent iLink QR login URL.")
    print("2. Scan the QR code or open the URL with the WeChat mobile app.")
    print("3. Confirm the login, then DojoAgents saves account_id/token/base_url.")

    start = _prompt_choice("Start WeChat QR login now?", ("y", "n"), "y")
    if start == "n":
        print("WeChat configuration skipped")
        return {**existing, "enabled": bool(existing.get("enabled", False))}

    credentials = _run_async(qr_client.login())
    dm_policy = _prompt_choice(
        "WeChat DM policy",
        ("pairing", "open", "allowlist", "disabled"),
        str(existing.get("dm_policy", "pairing") or "pairing"),
    )
    group_policy = _prompt_choice(
        "WeChat group policy",
        ("disabled", "open", "allowlist"),
        str(existing.get("group_policy", "disabled") or "disabled"),
    )

    values: dict[str, Any] = {
        "enabled": True,
        "account_id": credentials["account_id"],
        "token": credentials["token"],
        "base_url": credentials.get("base_url") or ILINK_BASE_URL,
        "dm_policy": dm_policy,
        "group_policy": group_policy,
    }

    user_id = credentials.get("user_id", "")
    if user_id:
        use_user_id = _prompt_choice(
            f"Use WeChat user ID ({user_id}) as home channel?",
            ("y", "n"),
            "y",
        )
        if use_user_id == "y":
            values["home_channel"] = user_id
        else:
            values["home_channel"] = _prompt_value(
                "WeChat home channel",
                str(existing.get("home_channel", "") or ""),
            )
    else:
        values["home_channel"] = _prompt_value(
            "WeChat home channel",
            str(existing.get("home_channel", "") or ""),
        )

    if dm_policy == "allowlist":
        values["allow_from"] = _prompt_csv(
            "WeChat allowed DM users",
            existing.get("allow_from", []),
        )
    if group_policy == "allowlist":
        values["group_allow_from"] = _prompt_csv(
            "WeChat allowed groups",
            existing.get("group_allow_from", []),
        )

    print("WeChat configured via QR login")
    return values


def _run_async(value: Awaitable[dict[str, str]] | dict[str, str]) -> dict[str, str]:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    raise RuntimeError("Cannot run WeChat QR login from an active event loop.")


def _prompt_choice(prompt: str, choices: tuple[str, ...], default: str) -> str:
    choices_text = "/".join(choices)
    while True:
        answer = input(f"{prompt} [{choices_text}] [{default}]: ").strip().lower()
        value = answer or default
        if value in choices:
            return value
        print(f"Please choose one of: {choices_text}")


def _prompt_value(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{prompt}{suffix}: ").strip() or default


def _prompt_csv(prompt: str, existing: Any) -> list[str]:
    if isinstance(existing, str):
        default_values = [item.strip() for item in existing.split(",") if item.strip()]
    elif isinstance(existing, list):
        default_values = [str(item) for item in existing]
    else:
        default_values = []
    default = ",".join(default_values)
    answer = _prompt_value(prompt, default)
    return [item.strip() for item in answer.split(",") if item.strip()]
