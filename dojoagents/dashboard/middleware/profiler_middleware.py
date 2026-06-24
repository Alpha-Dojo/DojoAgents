import os
from datetime import datetime
from pathlib import Path
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse
from pyinstrument import Profiler
from dojoagents.logging import LOGGER


class PyInstrumentProfilerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Determine if triggered by query param
        profile_param = request.query_params.get("profile", "").lower()
        trigger_request = profile_param in ("1", "true")

        # 2. Determine if triggered globally
        trigger_global = False
        config_store = getattr(request.app.state, "config_store", None)
        if config_store:
            try:
                snapshot = config_store.snapshot()
                if hasattr(snapshot, "dashboard") and hasattr(snapshot.dashboard, "profiler"):
                    trigger_global = getattr(snapshot.dashboard.profiler, "enabled", False)
            except Exception:
                pass

        if not trigger_request and not trigger_global:
            return await call_next(request)

        # 3. Profile the request
        profiler = Profiler(async_mode="enabled")
        profiler.start()

        try:
            response = await call_next(request)
        except Exception as e:
            profiler.stop()
            raise e

        profiler.stop()
        html_output = profiler.output_html()

        # 4. Handle output
        if trigger_request:
            # If triggered by query param, return HTML directly
            return HTMLResponse(content=html_output)

        # If globally triggered, save to disk and return original response
        try:
            local_data_dir = os.environ.get("DOJO_CACHE_DIR", os.path.expanduser("~/.dojo/data"))
            profiles_dir = Path(local_data_dir) / "profiles"
            profiles_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            endpoint_name = request.url.path.strip("/").replace("/", "_") or "root"
            filename = profiles_dir / f"profile_{endpoint_name}_{timestamp}.html"

            filename.write_text(html_output, encoding="utf-8")
            LOGGER.info(f"Performance profile saved to {filename}")
        except Exception as e:
            LOGGER.error(f"Failed to save performance profile: {e}")

        return response
