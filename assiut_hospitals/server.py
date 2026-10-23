"""A tiny static HTTP server for the emergency dispatch page.

خادم HTTP صغير لصفحة الإرسال؛ لا يشغّل محاكاة ولا يبثّ حالة مباشرة.

Only the standard library is used (``http.server``).  The old live simulation
stream and the old dashboard were removed by owner decision (requirement 9).
"""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .config import Config

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class MapHandler(BaseHTTPRequestHandler):
    """Static files + the dispatch JSON API."""

    server_version = "AssiutDispatch/2.0"
    web_dir: Path = Path(".")
    config: Config = None  # type: ignore[assignment]
    dispatcher: Any = None

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover
        if os.environ.get("ASSIUT_HOSPITALS_VERBOSE"):
            super().log_message(fmt, *args)

    # ------------------------------------------------------------- helpers
    def _send_bytes(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)
            return
        content_type, _ = mimetypes.guess_type(str(path))
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
        ):
            content_type += "; charset=utf-8"
        self._send_bytes(path.read_bytes(), content_type)

    # --------------------------------------------------------------- routes
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/dispatch", "/dispatch.html"):
            self._send_file(self.web_dir / "dispatch.html")
            return
        if path == "/api/dispatch/meta":
            self._dispatch_meta()
            return
        if path == "/api/dispatch":
            self._dispatch_query()
            return
        if path == "/api/hospitals":
            self._send_file(Path(self.config.dataset_file))
            return
        if path == "/api/network":
            self._send_file(Path(self.config.network_js))
            return

        # static assets
        relative = path.lstrip("/")
        candidate = (self.web_dir / relative).resolve()
        try:
            candidate.relative_to(self.web_dir.resolve())
        except ValueError:
            self._send_bytes(b"forbidden", "text/plain; charset=utf-8", 403)
            return
        self._send_file(candidate)

    # -------------------------------------------------------------- dispatch
    def _dispatch_meta(self) -> None:
        """Metadata needed by the dispatch page (specialties, data source).

        بيانات وصفية لصفحة الإرسال: التخصصات ومصدر بيانات الطوارئ وقرارات المالك.
        """
        if self.dispatcher is None:
            self._send_json({"error": "dispatcher not initialised"}, 503)
            return
        dispatcher = self.dispatcher
        self._send_json(
            {
                "specialties": list(dispatcher.dcfg.specialty_catalog),
                "capacity_source": dispatcher.capacity.source,
                "synthetic": dispatcher.capacity.synthetic,
                "vehicle_class": dispatcher.vehicle_class,
                "zone_source": dispatcher.dcfg.zone_source,
                "search_scope": dispatcher.dcfg.search_scope,
                "clinics_as_emergency": dispatcher.dcfg.clinics_as_emergency,
                "excluded_destinations": dict(dispatcher.dcfg.excluded_destinations),
                "cost_model": dispatcher.model.describe(),
                "config_errors": dispatcher.validate(),
            }
        )

    def _dispatch_query(self) -> None:
        """Answer ``/api/dispatch?lat=&lon=&specialty=`` (fastest hospital).

        ينفذ طلب إرسال ويعيد أفضل مستشفى ومساره وزمنه بصيغة JSON.
        """
        if self.dispatcher is None:
            self._send_json({"error": "dispatcher not initialised"}, 503)
            return
        query = parse_qs(urlparse(self.path).query)
        try:
            lat = float(query.get("lat", [""])[0])
            lon = float(query.get("lon", [""])[0])
        except (TypeError, ValueError):
            self._send_json({"error": "lat and lon (decimal degrees) are required"}, 400)
            return
        specialty = (query.get("specialty", ["general"])[0] or "general").strip()

        try:
            result = self.dispatcher.search(lat, lon, specialty, verify=True)
        except Exception as exc:  # DispatchError and unexpected failures
            self._send_json({"error": str(exc)}, 400)
            return

        payload = result.as_dict()
        if result.route is not None and payload.get("optimal"):
            payload["optimal"]["route"]["geometry"] = self.dispatcher.route_geometry(
                result.route
            )
        self._send_json(payload)


def serve(
    config: Config,
    host: Optional[str] = None,
    port: Optional[int] = None,
    open_browser: bool = False,
) -> None:
    """Start the static dispatch map server.

    تشغيل خادم خريطة الإرسال الثابتة.
    """
    host = host or config.server.get("host", "127.0.0.1")
    port = int(port or config.server.get("port", 8770))

    from .dispatch import Dispatcher

    dispatcher = Dispatcher(config=config)

    handler = type(
        "BoundMapHandler",
        (MapHandler,),
        {
            "web_dir": config.web_dir.resolve(),
            "config": config,
            "dispatcher": dispatcher,
        },
    )

    httpd = ThreadingHTTPServer((host, port), handler)
    url = "http://{0}:{1}/".format(host, port)
    print("  map      : {0}".format(url))
    print("  dispatch : {0}".format(url))
    print("  hospitals: {0}".format(config.dataset_file))
    print("  press Ctrl+C to stop")

    if open_browser:
        import webbrowser

        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopping ...")
    finally:
        httpd.server_close()
