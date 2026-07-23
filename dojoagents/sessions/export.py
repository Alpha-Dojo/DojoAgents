from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from dojoagents.sessions.atomic import _atomic_write_bytes, _atomic_write_text
from dojoagents.sessions.models import SessionPrincipal
from dojoagents.sessions.service import SessionService


@dataclass(frozen=True)
class SessionExportBundle:
    manifest: dict
    data: dict
    blobs: dict[str, bytes]

    async def write_to(self, output_dir: str | Path) -> Path:
        root = Path(output_dir).expanduser().resolve()

        def write() -> None:
            root.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(root / "manifest.json", json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n")
            _atomic_write_text(root / "session-data.json", json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")
            blob_root = root / "blobs"
            for blob_id, content in self.blobs.items():
                if not blob_id or "/" in blob_id or "\\" in blob_id or blob_id in {".", ".."}:
                    raise ValueError("export contains an invalid blob id")
                _atomic_write_bytes(blob_root / f"{blob_id}.blob", content)

        await asyncio.to_thread(write)
        return root


class SessionExporter:
    def __init__(self, service: SessionService) -> None:
        self.service = service

    async def export(self, principal: SessionPrincipal, session_id: str) -> SessionExportBundle:
        data = await self.service.export_session(principal, session_id)
        blobs: dict[str, bytes] = {}
        for item in data["objects"]:
            blob = item.get("blob_ref")
            if not isinstance(blob, dict) or blob.get("state") != "committed":
                continue
            stream = await self.service.object_writer(principal, session_id).open(str(item["object_id"]))
            blobs[str(blob["blob_id"])] = b"".join([chunk async for chunk in stream])
        manifest = {
            "schema_version": 1,
            "format": "dojoagents.session-export",
            "session_id": session_id,
            "harness_id": data["session"]["harness_id"],
            "counts": {
                "messages": len(data["messages"]),
                "runs": len(data["runs"]),
                "turns": len(data["turns"]),
                "events": len(data["events"]),
                "usage": len(data["usage"]),
                "checkpoints": len(data["checkpoints"]),
                "objects": len(data["objects"]),
                "blobs": len(blobs),
            },
        }
        return SessionExportBundle(manifest=manifest, data=data, blobs=blobs)
