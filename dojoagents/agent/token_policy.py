from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenCompressionPolicy:
    threshold_ratio: float = 0.8

    def should_compress(
        self,
        last_prompt_tokens: int,
        session_max_tokens: int,
        *,
        enabled: bool,
    ) -> bool:
        if not enabled or session_max_tokens <= 0:
            return False
        return last_prompt_tokens >= int(session_max_tokens * self.threshold_ratio)

    def utilization_ratio(self, last_prompt_tokens: int, session_max_tokens: int) -> float:
        if session_max_tokens <= 0:
            return 0.0
        return last_prompt_tokens / session_max_tokens
