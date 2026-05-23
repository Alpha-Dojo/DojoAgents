from __future__ import annotations

from typing import Any

from dojoagents.agent.models import AgentResponse
from dojoagents.cron.jobs import JobRun, JobStore


class SchedulerService:
    def __init__(
        self,
        *,
        runtime_factory: Any,
        job_store: JobStore,
        gateway: Any | None = None,
    ) -> None:
        self.runtime_factory = runtime_factory
        self.job_store = job_store
        self.gateway = gateway

    def list_jobs(self) -> list[dict]:
        return self.job_store.list_jobs()

    async def run_job(self, job_id: str) -> JobRun:
        job = self.job_store.get(job_id)
        runtime = self.runtime_factory.for_profile(job.profile)
        response: AgentResponse = await runtime.agent.run(job.to_chat_request())
        run = self.job_store.save_output(job, response.content)
        if job.delivery and self.gateway is not None:
            await self.gateway.send(job.delivery, response.content)
        return run
