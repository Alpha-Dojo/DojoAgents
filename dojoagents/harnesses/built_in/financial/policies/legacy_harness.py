from __future__ import annotations

from dojoagents.harnesses.components.task_flows import (
    HarnessDecision,
    HarnessLoopState as BaseHarnessLoopState,
    TaskHarness,
)


class FinancialHarnessLoopState(BaseHarnessLoopState):
    def last_eval_submission(self):
        from .legacy.portfolio_eval import parse_eval_submission

        for result in reversed(self.tool_results):
            if result.ok and result.name == "portfolio_eval_submit":
                parsed = parse_eval_submission(result.data)
                if parsed is not None:
                    return parsed
        return None

    def created_portfolio_ids(self) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for result in self.tool_results:
            if not result.ok or result.name != "portfolio_write_create":
                continue
            portfolio_id: str | None = None
            data = result.data
            if isinstance(data, dict):
                raw_id = data.get("id") or data.get("portfolio_id")
                if raw_id:
                    portfolio_id = str(raw_id)
            if portfolio_id is None:
                for change in result.resource_changes:
                    if change.get("resource") == "portfolio" and change.get("action") == "create":
                        raw_id = change.get("portfolio_id")
                        if raw_id:
                            portfolio_id = str(raw_id)
                            break
            if portfolio_id and portfolio_id not in seen:
                seen.add(portfolio_id)
                ids.append(portfolio_id)
        return ids

    def created_portfolio_id(self) -> str | None:
        ids = self.created_portfolio_ids()
        return ids[-1] if ids else None

    def deleted_portfolio_ids(self) -> set[str]:
        deleted: set[str] = set()
        for result in self.tool_results:
            if not result.ok or result.name != "portfolio_write_delete":
                continue
            for change in result.resource_changes:
                if change.get("resource") == "portfolio" and change.get("portfolio_id"):
                    deleted.add(str(change["portfolio_id"]))
            data = result.data
            if isinstance(data, dict) and data.get("portfolio_id"):
                deleted.add(str(data["portfolio_id"]))
        return deleted

    def target_portfolio_id(self) -> str | None:
        created = self.created_portfolio_id()
        if created:
            return created
        deleted = self.deleted_portfolio_ids()
        for result in reversed(self.tool_results):
            if not result.ok or result.name not in {
                "portfolio_write_add_candidate",
                "portfolio_write_add_candidates",
                "portfolio_write_add_holding",
                "portfolio_write_add_holdings",
                "portfolio_write_create_order",
                "portfolio_write_create_orders",
                "portfolio_write_sync_positions",
                "portfolio_write_remove_holding",
                "portfolio_write_remove_candidates",
                "portfolio_write_rename",
                "portfolio_write_auto_allocate",
                "portfolio_read_detail",
            }:
                continue
            for change in reversed(result.resource_changes):
                portfolio_id = change.get("portfolio_id")
                if change.get("resource") == "portfolio" and portfolio_id:
                    portfolio_id = str(portfolio_id)
                    if portfolio_id not in deleted:
                        return portfolio_id
            data = result.data
            if isinstance(data, dict):
                portfolio_id = data.get("portfolio_id") or data.get("id")
                if portfolio_id and str(portfolio_id) not in deleted:
                    return str(portfolio_id)
        return None

    def last_created_portfolio_id(self) -> str | None:
        return self.target_portfolio_id()


HarnessLoopState = FinancialHarnessLoopState

__all__ = [
    "FinancialHarnessLoopState",
    "HarnessDecision",
    "HarnessLoopState",
    "TaskHarness",
]
