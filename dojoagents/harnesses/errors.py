"""Harness composition and lifecycle errors."""


class HarnessError(RuntimeError):
    """Base error for harness operations."""


class InvalidHarnessError(HarnessError):
    """Raised when an object does not satisfy the harness contract."""


class CapabilityConflictError(HarnessError):
    """Raised when harness capabilities cannot be composed safely."""


class HarnessLifecycleError(HarnessError):
    """Raised when harness startup or shutdown fails."""


class HarnessLoadError(HarnessError):
    """Raised when a configured harness factory cannot be resolved."""


class HarnessConfigError(HarnessError):
    """Raised when harness-specific configuration is invalid."""


class HarnessPolicyError(HarnessError):
    """Raised when a runtime policy or presenter violates its contract."""
