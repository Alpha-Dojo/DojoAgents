"""Dashboard visualization prompt contributor."""

from dojoagents.agent.canvas_protocol import DASHBOARD_VIZ_PROTOCOL
from dojoagents.agent.viz_policy import build_viz_policy_catalog, build_viz_policy_turn_anchor


def visualization_prompt(context) -> str:
    request = context.request
    locale = str(request.metadata.get("locale") or "en")
    blocks = [DASHBOARD_VIZ_PROTOCOL, build_viz_policy_catalog(locale)]
    turn = build_viz_policy_turn_anchor(request, locale)
    if turn:
        blocks.append(turn)
    return "\n\n".join(blocks)


__all__ = ["visualization_prompt"]
