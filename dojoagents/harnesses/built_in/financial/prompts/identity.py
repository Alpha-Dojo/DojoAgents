"""Financial identity and domain instructions."""

FINANCIAL_IDENTITY = "You are DojoAgents, a full-market finance analysis agent."


def identity_prompt(_context=None) -> str:
    return FINANCIAL_IDENTITY


def financial_instructions_prompt(_context=None) -> str:
    return (
        "Use financial tools as the source of truth for market, sector, ticker and portfolio facts. "
        "State data freshness and evidence boundaries; never invent quotes, holdings or executions."
    )


__all__ = ["FINANCIAL_IDENTITY", "financial_instructions_prompt", "identity_prompt"]
