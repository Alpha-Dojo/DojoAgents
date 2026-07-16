from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dojoagents.agent.models import ChatRequest
from dojoagents.tasks.models import (
    ActiveTask,
    PipelineSpec,
    PipelineState,
    PipelineStep,
    TaskArtifactSpec,
    TaskContract,
    TaskSpec,
)
from dojoagents.tasks.preflight import parse_pipeline_preflight


def _artifact_specs(raw_items: Any) -> list[TaskArtifactSpec]:
    if not isinstance(raw_items, list):
        return []
    specs: list[TaskArtifactSpec] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if not filename:
            continue
        source_task = str(item.get("source_task") or "").strip() or None
        specs.append(
            TaskArtifactSpec(
                filename=filename,
                format=str(item.get("format") or "json"),
                required=bool(item.get("required", True)),
                schema=str(item["schema"]).strip() if item.get("schema") else None,
                source_task=source_task,
            )
        )
    return specs


def _parse_contract(raw: dict[str, Any], task_dir: Path) -> TaskContract:
    return TaskContract(
        id=str(raw.get("id") or task_dir.name),
        version=int(raw.get("version", 1)),
        name=str(raw.get("name") or ""),
        harness_profile=str(raw.get("harness_profile") or "artifact_synthesis"),
        inputs=_artifact_specs(raw.get("inputs")),
        outputs=_artifact_specs(raw.get("outputs")),
        required_tools=[str(t) for t in (raw.get("required_tools") or []) if str(t).strip()],
        triggers=dict(raw.get("triggers") or {}),
        channels=[str(c) for c in (raw.get("channels") or []) if str(c).strip()],
        constraints=dict(raw.get("constraints") or {}),
        downstream=str(raw["downstream"]).strip() if raw.get("downstream") else None,
    )


def _parse_pipeline(raw: dict[str, Any]) -> PipelineSpec:
    steps: list[PipelineStep] = []
    for item in raw.get("steps") or []:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task") or "").strip()
        if not task_id:
            continue
        input_map = item.get("input_map")
        steps.append(
            PipelineStep(
                task=task_id,
                on_success=str(item.get("on_success") or "continue"),
                input_map=dict(input_map) if isinstance(input_map, dict) else {},
            )
        )
    return PipelineSpec(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        steps=steps,
        preflight=parse_pipeline_preflight(raw.get("preflight")),
    )


class TaskPromptManager:
    def __init__(self, *, task_dirs: list[str | Path], pipeline_dirs: list[str | Path] | None = None) -> None:
        self.task_dirs = [Path(path).expanduser() for path in task_dirs]
        self.pipeline_dirs = [Path(path).expanduser() for path in (pipeline_dirs or [])]
        self._tasks: dict[str, TaskSpec] = {}
        self._pipelines: dict[str, PipelineSpec] = {}
        self.reload()

    def reload(self) -> None:
        self._tasks = {}
        self._pipelines = {}
        seen_ids: set[str] = set()
        for root in self.task_dirs:
            if not root.is_dir():
                continue
            for task_dir in sorted(root.iterdir()):
                if not task_dir.is_dir():
                    continue
                spec = self._load_task_dir(task_dir)
                if spec is None or spec.contract.id in seen_ids:
                    continue
                seen_ids.add(spec.contract.id)
                self._tasks[spec.contract.id] = spec
        seen_pipeline_ids: set[str] = set()
        for root in self.pipeline_dirs:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
                pipeline = self._load_pipeline_file(path)
                if pipeline is None or not pipeline.id or pipeline.id in seen_pipeline_ids:
                    continue
                seen_pipeline_ids.add(pipeline.id)
                self._pipelines[pipeline.id] = pipeline

    def _load_task_dir(self, task_dir: Path) -> TaskSpec | None:
        contract_path = task_dir / "contract.yaml"
        task_path = task_dir / "TASK.md"
        if not contract_path.is_file() or not task_path.is_file():
            return None
        raw = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        contract = _parse_contract(raw, task_dir)
        prompt_body = task_path.read_text(encoding="utf-8").strip()
        return TaskSpec(contract=contract, prompt_body=prompt_body, task_dir=task_dir)

    def _load_pipeline_file(self, path: Path) -> PipelineSpec | None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        pipeline = _parse_pipeline(raw)
        return pipeline if pipeline.id else None

    def list_tasks(self) -> list[str]:
        return sorted(self._tasks)

    def list_pipelines(self) -> list[str]:
        return sorted(self._pipelines)

    def get_task(self, task_id: str) -> TaskSpec | None:
        return self._tasks.get(str(task_id or "").strip())

    def get_pipeline(self, pipeline_id: str) -> PipelineSpec | None:
        return self._pipelines.get(str(pipeline_id or "").strip())

    def resolve_schema_path(self, task: TaskSpec, schema_ref: str) -> Path | None:
        candidate = Path(schema_ref)
        if candidate.is_absolute() and candidate.is_file():
            return candidate
        resolved = (task.task_dir / schema_ref).resolve()
        return resolved if resolved.is_file() else None

    def build_injection_block(self, request: ChatRequest) -> str:
        active = ActiveTask.from_metadata(request.metadata.get("active_task"))
        if active is None:
            return ""
        spec = self.get_task(active.task_id)
        if spec is None:
            return ""

        lines = [
            f"## ACTIVE TASK: {spec.contract.name or spec.contract.id}",
            "",
            f"Task ID: `{spec.contract.id}` (harness: `{active.harness_profile or spec.contract.harness_profile}`)",
        ]
        if active.params:
            lines.append("Runtime parameters:")
            for key, value in sorted(active.params.items()):
                lines.append(f"- {key}: {value}")
        if active.inputs:
            lines.append("")
            lines.append("Required input artifacts:")
            for item in active.inputs:
                filename = item.get("filename", "?")
                status = "ready" if filename in active.input_read else "not yet read — call read_session_output first"
                lines.append(f"- {filename} ({status})")
        if active.outputs:
            lines.append("")
            lines.append("Required output artifacts (written under ~/.dojo/tasks/outputs/{task_id}/):")
            for item in active.outputs:
                lines.append(f"- {item.get('filename', '?')} (format={item.get('format', 'json')})")

        pipeline = PipelineState.from_metadata(request.metadata.get("pipeline"))
        if pipeline is not None:
            lines.extend(
                [
                    "",
                    f"Pipeline: `{pipeline.id}` step {pipeline.step}",
                ]
            )
            if pipeline.artifacts:
                lines.append("Pipeline artifacts:")
                for name, path in sorted(pipeline.artifacts.items()):
                    lines.append(f"- {name}: {path}")

        lines.extend(["", "---", "", spec.prompt_body])
        return "\n".join(lines)
