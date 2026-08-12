"""
A tiny teaching web server for introductory frontend/backend exercises.

Run:
    python tip_server.py path/to/project

Expected project layout:
    project/
      static/
        index.html
        style.css
      backend.py

In backend.py:
    from tip import route

    @route("/hello")
    def hello():
        return "Hello from Python"
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import inspect
import mimetypes
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse


DEFAULT_PORTS = (80, 8000, 8080)
ROUTES: dict[str, Callable[..., object]] = {}


@dataclass
class Request:
    path: str
    query: dict[str, str]
    query_all: dict[str, list[str]]
    method: str
    headers: object


@dataclass
class Response:
    body: str | bytes
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    headers: dict[str, str] | None = None


def route(path: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Register a function as the handler for a URL path."""
    if not path.startswith("/"):
        path = "/" + path

    def register(function: Callable[..., object]) -> Callable[..., object]:
        ROUTES[path] = function
        return function

    return register


def text(body: str, status: int = 200) -> Response:
    return Response(body, status=status, content_type="text/plain; charset=utf-8")


def html_page(body: str, status: int = 200) -> Response:
    return Response(body, status=status, content_type="text/html; charset=utf-8")


def json(data: str, status: int = 200) -> Response:
    return Response(data, status=status, content_type="application/json; charset=utf-8")


def redirect(location: str, status: int = 302) -> Response:
    return Response("", status=status, headers={"Location": location})


def _load_backend(project_dir: Path) -> None:
    backend_file = project_dir / "backend.py"
    if not backend_file.exists():
        return

    # Allows student code to say: from tip import route
    sys.modules["tip"] = sys.modules[__name__]

    spec = importlib.util.spec_from_file_location("student_backend", backend_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {backend_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["student_backend"] = module
    spec.loader.exec_module(module)


def _safe_static_path(static_dir: Path, request_path: str) -> Path | None:
    if request_path == "/":
        request_path = "/index.html"

    relative_path = unquote(request_path).lstrip("/")
    candidate = (static_dir / relative_path).resolve()

    try:
        candidate.relative_to(static_dir.resolve())
    except ValueError:
        return None

    if candidate.is_file():
        return candidate
    return None


def _make_request(handler: BaseHTTPRequestHandler) -> Request:
    parsed = urlparse(handler.path)
    query_all = parse_qs(parsed.query)
    query = {key: values[-1] for key, values in query_all.items() if values}
    return Request(
        path=parsed.path,
        query=query,
        query_all=query_all,
        method=handler.command,
        headers=handler.headers,
    )


def _call_route(handler_function: Callable[..., object], request: Request) -> object:
    signature = inspect.signature(handler_function)
    if len(signature.parameters) == 0:
        return handler_function()
    if len(signature.parameters) == 1:
        return handler_function(request)

    raise TypeError("Route functions must accept either no arguments or one request argument.")


def _status_message(status: int) -> str:
    messages = {
        200: "OK",
        302: "Found",
        400: "Bad Request",
        404: "Not Found",
        500: "Internal Server Error",
    }
    return messages.get(status, "OK")


def _send_response(handler: BaseHTTPRequestHandler, response: object) -> None:
    if isinstance(response, Response):
        body = response.body
        status = response.status
        content_type = response.content_type
        extra_headers = response.headers or {}
    else:
        body = "" if response is None else str(response)
        status = 200
        content_type = "text/html; charset=utf-8"
        extra_headers = {}

    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body

    handler.send_response(status, _status_message(status))
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body_bytes)))
    for name, value in extra_headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body_bytes)


def _send_file(handler: BaseHTTPRequestHandler, file_path: Path) -> None:
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = file_path.read_bytes()

    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_error_page(handler: BaseHTTPRequestHandler, status: int, title: str, detail: str) -> None:
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{status} {html.escape(title)}</title>
</head>
<body>
  <h1>{status} {html.escape(title)}</h1>
  <p>{html.escape(detail)}</p>
</body>
</html>
"""
    _send_response(handler, Response(body, status=status))


def _make_handler(project_dir: Path) -> type[BaseHTTPRequestHandler]:
    static_dir = project_dir / "static"

    class TipRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = _make_request(self)

            static_file = _safe_static_path(static_dir, request.path)
            if static_file is not None:
                _send_file(self, static_file)
                return

            handler_function = ROUTES.get(request.path)
            if handler_function is None:
                _send_error_page(self, 404, "Not Found", f"No static file or route for {request.path}")
                return

            try:
                response = _call_route(handler_function, request)
                _send_response(self, response)
            except Exception as error:
                _send_error_page(self, 500, "Internal Server Error", str(error))

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write(f"{self.address_string()} - {format % args}\n")

    return TipRequestHandler


def _start_server(project_dir: Path, ports: tuple[int, ...]) -> None:
    handler_class = _make_handler(project_dir)
    last_error: OSError | None = None

    for port in ports:
        try:
            server = ThreadingHTTPServer(("", port), handler_class)
        except OSError as error:
            last_error = error
            continue

        print(f"Serving {project_dir} at http://localhost:{port}")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
        finally:
            server.server_close()
        return

    raise RuntimeError(f"Could not start server on any of these ports: {ports}. Last error: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a tiny teaching web server.")
    parser.add_argument("project_dir", help="Folder containing static/ and optional backend.py")
    parser.add_argument(
        "--ports",
        default=",".join(str(port) for port in DEFAULT_PORTS),
        help="Comma-separated ports to try. Default: 80,8000,8080",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"Project folder does not exist: {project_dir}")

    ports = tuple(int(port.strip()) for port in args.ports.split(",") if port.strip())
    if not ports:
        raise SystemExit("Please provide at least one port.")

    _load_backend(project_dir)
    _start_server(project_dir, ports)


if __name__ == "__main__":
    main()
