from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.contracts.portfolio import CreatePortfolioRequest, UpdatePortfolioRequest
from dojoagents.harnesses.built_in.financial.services.portfolio_service import PortfolioService, PortfolioValidationError
from dojoagents.harnesses.built_in.financial.services.portfolio_store import PortfolioStore


class _EmptyStockStore:
    def get(self, *_args):
        return None

    def find_market(self, _ticker):
        return None


class _EmptySectorStore:
    def get(self, *_args):
        return None


class _NoFetchKline:
    async def get_or_fetch_kline(self, *_args, **_kwargs):
        return None


@pytest.fixture
def portfolio_service(tmp_path) -> PortfolioService:
    store = PortfolioStore(tmp_path)
    return PortfolioService(store, _EmptyStockStore(), _EmptySectorStore(), _NoFetchKline())


@pytest.mark.asyncio
async def test_agent_create_sets_kind_agent(portfolio_service: PortfolioService) -> None:
    detail = await portfolio_service.create(CreatePortfolioRequest(name="Agent Folio", kind="agent"))
    assert detail.kind == "agent"


@pytest.mark.asyncio
async def test_manual_create_sets_kind_manual(portfolio_service: PortfolioService) -> None:
    detail = await portfolio_service.create(CreatePortfolioRequest(name="Manual Folio"))
    assert detail.kind == "manual"


@pytest.mark.asyncio
async def test_agent_delete_rejects_manual_portfolio(portfolio_service: PortfolioService) -> None:
    manual = await portfolio_service.create(CreatePortfolioRequest(name="Protected"))
    with pytest.raises(PortfolioValidationError, match="protected"):
        await portfolio_service.delete(manual.id, agent_only=True)


@pytest.mark.asyncio
async def test_agent_delete_allows_agent_portfolio(portfolio_service: PortfolioService) -> None:
    agent = await portfolio_service.create(CreatePortfolioRequest(name="Disposable", kind="agent"))
    assert await portfolio_service.delete(agent.id, agent_only=True) is True


@pytest.mark.asyncio
async def test_user_delete_allows_manual_portfolio(portfolio_service: PortfolioService) -> None:
    manual = await portfolio_service.create(CreatePortfolioRequest(name="User Folio"))
    assert await portfolio_service.delete(manual.id) is True


@pytest.mark.asyncio
async def test_promote_agent_to_manual(portfolio_service: PortfolioService) -> None:
    agent = await portfolio_service.create(CreatePortfolioRequest(name="Promote Me", kind="agent"))
    updated = await portfolio_service.update(agent.id, UpdatePortfolioRequest(kind="manual"))
    assert updated is not None
    assert updated.kind == "manual"


@pytest.mark.asyncio
async def test_cannot_demote_manual_to_agent(portfolio_service: PortfolioService) -> None:
    manual = await portfolio_service.create(CreatePortfolioRequest(name="Stay Manual"))
    with pytest.raises(PortfolioValidationError, match="cannot be converted"):
        await portfolio_service.update(manual.id, UpdatePortfolioRequest(kind="agent"))
