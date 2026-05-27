import re

_PREFIX_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{10,}",           # OpenAI / Anthropic
    r"ghp_[A-Za-z0-9]{10,}",            # GitHub PAT
    r"AIza[A-Za-z0-9_-]{30,}",          # Google API keys
    r"gsk_[A-Za-z0-9]{10,}",            # Groq Cloud API key
]

_SECRET_ENV_NAMES = r"(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)"
_ENV_ASSIGN_RE = re.compile(
    rf"([A-Z0-9_]{{0,50}}{_SECRET_ENV_NAMES}[A-Z0-9_]{{0,50}})\s*=\s*(['\"]?)(\S+)\2",
    re.IGNORECASE
)

_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(" + "|".join(_PREFIX_PATTERNS) + r")(?![A-Za-z0-9_-])"
)

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----"
)

def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) < 12:
        return "***"
    return f"{value[:6]}...{value[-4:]}"

def redact_sensitive_text(text: str) -> str:
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text

    # 1. 过滤已知 API key 前缀
    text = _PREFIX_RE.sub(lambda m: mask_secret(m.group(1)), text)

    # 2. 过滤环境变量 KEY=value 分配
    def _redact_env(m):
        name, quote, value = m.group(1), m.group(2), m.group(3)
        return f"{name}={quote}{mask_secret(value)}{quote}"
    text = _ENV_ASSIGN_RE.sub(_redact_env, text)

    # 3. 过滤私钥 Block
    text = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", text)

    return text
