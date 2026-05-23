from __future__ import annotations

from dojoagents.tools.sandbox import SandboxPolicy


class LocalEnvironment:
    def __init__(self, policy: SandboxPolicy) -> None:
        self.policy = policy
