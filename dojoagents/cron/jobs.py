from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from dojoagents.agent.models import ChatRequest
from dojoagents.quant.context import QuantContext


@dataclass(frozen=True)
class ScheduledJob:
    id: str
    name: str
    schedule: dict[str, Any]
    prompt: str
    enabled: bool = True
    profile: str = "default"
    quant: QuantContext | None = None
    delivery: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    plan: bool = False

    def to_chat_request(self) -> ChatRequest:
        meta = {"job_id": self.id, **self.metadata}
        if self.plan:
            meta["plan"] = True
        return ChatRequest(
            message=self.prompt,
            user_id="scheduler",
            session_id=f"job-{self.id}-{uuid4().hex[:8]}",
            channel="scheduler",
            quant=self.quant,
            metadata=meta,
        )

    def to_record(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ScheduledJob":
        quant = record.get("quant")
        if isinstance(quant, dict):
            quant = QuantContext(**quant)
        return cls(
            id=record["id"],
            name=record.get("name", record["id"]),
            schedule=dict(record.get("schedule", {})),
            prompt=record.get("prompt", ""),
            enabled=bool(record.get("enabled", True)),
            profile=record.get("profile", "default"),
            quant=quant,
            delivery=record.get("delivery"),
            metadata=dict(record.get("metadata", {})),
            plan=bool(record.get("plan", False)),
        )


@dataclass(frozen=True)
class JobRun:
    id: str
    job_id: str
    output: str
    created_at: str
    path: str
    ok: bool = True
    error: str = ""


class JobStore:
    def __init__(
        self,
        path: str | Path = "~/.dojo/agents/jobs.yaml",
        *,
        output_dir: str | Path | None = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.output_dir = (
            Path(output_dir).expanduser()
            if output_dir is not None
            else self.path.parent / "job_runs"
        )
        self._jobs: dict[str, ScheduledJob] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or []
        records = raw.get("jobs", raw) if isinstance(raw, dict) else raw
        self._jobs = {
            record["id"]: ScheduledJob.from_record(record)
            for record in records
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = [job.to_record() for job in self._jobs.values()]
        self.path.write_text(yaml.safe_dump({"jobs": records}, sort_keys=False), encoding="utf-8")

    def add(self, job: ScheduledJob) -> None:
        self._jobs[job.id] = job
        self._save()

    def get(self, job_id: str) -> ScheduledJob:
        return self._jobs[job_id]

    def list_jobs(self) -> list[dict[str, Any]]:
        return [job.to_record() for job in self._jobs.values()]

    def save_output(self, job: ScheduledJob, output: str, *, ok: bool = True, error: str = "") -> JobRun:
        created = datetime.now(timezone.utc).isoformat()
        run_id = uuid4().hex
        run_dir = self.output_dir / job.id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{run_id}.md"
        path.write_text(output, encoding="utf-8")
        return JobRun(
            id=run_id,
            job_id=job.id,
            output=output,
            created_at=created,
            path=str(path),
            ok=ok,
            error=error,
        )
