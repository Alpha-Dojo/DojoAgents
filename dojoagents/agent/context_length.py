from __future__ import annotations

import re

_MAX_CONTEXT_RE = re.compile(r"maximum context length is (\d+)", re.IGNORECASE)
_REQUESTED_TOKENS_RE = re.compile(r"requested (\d+) tokens", re.IGNORECASE)


class ContextLengthExceededError(Exception):
    def __init__(
        self,
        message: str,
        *,
        max_context: int | None = None,
        requested_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.max_context = max_context
        self.requested_tokens = requested_tokens


def parse_context_length_error(message: str) -> tuple[int | None, int | None]:
    max_match = _MAX_CONTEXT_RE.search(message)
    req_match = _REQUESTED_TOKENS_RE.search(message)
    max_context = int(max_match.group(1)) if max_match else None
    requested = int(req_match.group(1)) if req_match else None
    return max_context, requested
