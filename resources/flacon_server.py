"""
A tiny teaching web server for introductory frontend/backend exercises.

Run:
    python flacon_server.py path/to/project

Expected project layout:
    project/
      static/
        index.html
        style.css
      backend.py

In backend.py:
    from flacon import route

    @route("/hello")
    def hello():
        return "Hello from Python"
"""

import argparse
import ast
import html
import importlib.util
import inspect
import mimetypes
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, TypeAlias
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_PORTS = (80, 8000, 8080)
PROJECT_DIR: Path | None = None
TEMPLATE_TOKEN_RE = re.compile(r"({{.*?}}|{%.*?%})", re.DOTALL)
FOR_TAG_RE = re.compile(r"^for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+)$", re.DOTALL)


@dataclass
class Route:
    handler: Callable[..., object]
    methods: tuple[str, ...]


ROUTES: dict[str, Route] = {}


@dataclass
class Request:
    path: str
    query: dict[str, str]
    query_all: dict[str, list[str]]
    method: str
    headers: object
    body: str = ""
    form: dict[str, str] = field(default_factory=dict)
    form_all: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Response:
    body: str | bytes
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    headers: dict[str, str] | None = None


def route(path: str, methods: Iterable[str] | None = None) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Register a function as the handler for a URL path."""
    if not path.startswith("/"):
        path = "/" + path
    allowed_methods = _normalize_methods(methods)

    def register(function: Callable[..., object]) -> Callable[..., object]:
        ROUTES[path] = Route(function, allowed_methods)
        return function

    return register


def _normalize_methods(methods: Iterable[str] | None) -> tuple[str, ...]:
    if methods is None:
        return ("GET",)
    if isinstance(methods, str):
        raise TypeError("route methods must be a list of HTTP method names, not a string.")

    normalized_methods: list[str] = []
    seen: set[str] = set()
    for method in methods:
        if not isinstance(method, str):
            raise TypeError("route methods must contain only strings.")
        normalized_method = method.strip().upper()
        if not normalized_method:
            raise ValueError("route methods must not contain empty method names.")
        if normalized_method not in seen:
            normalized_methods.append(normalized_method)
            seen.add(normalized_method)

    return tuple(normalized_methods)


def text(body: str, status: int = 200) -> Response:
    return Response(body, status=status, content_type="text/plain; charset=utf-8")


def html_page(body: str, status: int = 200) -> Response:
    return Response(body, status=status, content_type="text/html; charset=utf-8")


def json(data: str, status: int = 200) -> Response:
    return Response(data, status=status, content_type="application/json; charset=utf-8")


def redirect(location: str, status: int = 302) -> Response:
    return Response("", status=status, headers={"Location": location})


def render_template(template_name: str, **context: object) -> str:
    """Render a template from the project's templates folder."""
    if PROJECT_DIR is None:
        raise RuntimeError("Templates are only available after Flacon has loaded a project.")

    templates_dir = PROJECT_DIR / "templates"
    return _render_template_file(template_name, context, templates_dir, templates_dir, [])


def _load_backend(project_dir: Path) -> None:
    global PROJECT_DIR

    PROJECT_DIR = project_dir
    backend_file = project_dir / "backend.py"
    if not backend_file.exists():
        return

    project_path = str(project_dir)
    if project_path in sys.path:
        sys.path.remove(project_path)
    sys.path.insert(0, project_path)

    # Allows student code to say: from flacon import route.
    sys.modules["flacon"] = sys.modules[__name__]
    # Keep older course projects working while the public name moves to Flacon.
    sys.modules.setdefault("tip", sys.modules[__name__])

    spec = importlib.util.spec_from_file_location("student_backend", backend_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {backend_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["student_backend"] = module
    spec.loader.exec_module(module)


TemplateNode: TypeAlias = (
    tuple[str, str]
    | tuple[str, str, str, list["TemplateNode"]]
    | tuple[str, str, list["TemplateNode"], list["TemplateNode"]]
)


def _render_template_file(
    template_name: str,
    context: dict[str, object],
    templates_dir: Path,
    relative_to: Path,
    stack: list[Path],
) -> str:
    template_path = _resolve_template_path(template_name, templates_dir, relative_to)

    if template_path in stack:
        chain = " -> ".join(path.name for path in [*stack, template_path])
        raise RuntimeError(f"Template include cycle detected: {chain}")

    source = template_path.read_text(encoding="utf-8")
    nodes = _parse_template(source, template_path.name)
    return _render_template_nodes(nodes, dict(context), templates_dir, template_path.parent, [*stack, template_path])


def _resolve_template_path(template_name: str, templates_dir: Path, relative_to: Path) -> Path:
    if not template_name:
        raise RuntimeError("Template name must not be empty.")

    requested_path = Path(template_name)
    if requested_path.is_absolute():
        raise RuntimeError(f"Template paths must be relative: {template_name}")

    base_dir = relative_to if "/" in template_name or "\\" in template_name else templates_dir
    template_path = (base_dir / requested_path).resolve()
    templates_root = templates_dir.resolve()

    try:
        template_path.relative_to(templates_root)
    except ValueError:
        raise RuntimeError(f"Template path must stay inside {templates_dir}: {template_name}") from None

    if not template_path.is_file():
        raise RuntimeError(f"Template not found: {template_name}")

    return template_path


def _parse_template(source: str, template_name: str) -> list[TemplateNode]:
    tokens = TEMPLATE_TOKEN_RE.split(source)
    nodes, position, end_tag = _parse_template_nodes(tokens, 0, set(), template_name)
    if end_tag is not None:
        raise RuntimeError(f"Unexpected template tag {{% {end_tag} %}} in {template_name}.")
    if position != len(tokens):
        raise RuntimeError(f"Could not parse template {template_name}.")
    return nodes


def _parse_template_nodes(
    tokens: list[str],
    position: int,
    stop_tags: set[str],
    template_name: str,
) -> tuple[list[TemplateNode], int, str | None]:
    nodes: list[TemplateNode] = []

    while position < len(tokens):
        token = tokens[position]

        if token.startswith("{{") and token.endswith("}}"):
            nodes.append(("value", token[2:-2].strip()))
            position += 1
            continue

        if token.startswith("{%") and token.endswith("%}"):
            tag = token[2:-2].strip()
            tag_name = tag.split(None, 1)[0] if tag else ""

            if tag_name in stop_tags:
                return nodes, position + 1, tag_name

            if tag_name == "include":
                nodes.append(("include", tag.removeprefix("include").strip()))
                position += 1
                continue

            if tag_name == "for":
                match = FOR_TAG_RE.match(tag)
                if match is None:
                    raise RuntimeError(f"Invalid for tag in {template_name}: {{% {tag} %}}")

                body, position, end_tag = _parse_template_nodes(tokens, position + 1, {"endfor"}, template_name)
                if end_tag != "endfor":
                    raise RuntimeError(f"Missing {{% endfor %}} in {template_name}.")

                nodes.append(("for", match.group(1), match.group(2).strip(), body))
                continue

            if tag_name == "if":
                condition = tag.removeprefix("if").strip()
                if not condition:
                    raise RuntimeError(f"Invalid if tag in {template_name}: {{% {tag} %}}")

                true_body, position, end_tag = _parse_template_nodes(tokens, position + 1, {"else", "endif"}, template_name)
                false_body: list[TemplateNode] = []
                if end_tag == "else":
                    false_body, position, end_tag = _parse_template_nodes(tokens, position, {"endif"}, template_name)
                if end_tag != "endif":
                    raise RuntimeError(f"Missing {{% endif %}} in {template_name}.")

                nodes.append(("if", condition, true_body, false_body))
                continue

            raise RuntimeError(f"Unknown template tag in {template_name}: {{% {tag} %}}")

        if token:
            nodes.append(("text", token))
        position += 1

    return nodes, position, None


def _render_template_nodes(
    nodes: list[TemplateNode],
    context: dict[str, object],
    templates_dir: Path,
    relative_to: Path,
    stack: list[Path],
) -> str:
    rendered: list[str] = []

    for node in nodes:
        node_type = node[0]

        if node_type == "text":
            rendered.append(node[1])
        elif node_type == "value":
            value = _evaluate_template_expression(node[1], context)
            rendered.append("" if value is None else html.escape(str(value)))
        elif node_type == "include":
            included_name = _evaluate_template_name(node[1], context)
            rendered.append(_render_template_file(included_name, context, templates_dir, relative_to, stack))
        elif node_type == "for":
            variable_name = node[1]
            collection = _evaluate_template_expression(node[2], context)
            for value in _template_iterable(collection):
                loop_context = dict(context)
                loop_context[variable_name] = value
                rendered.append(_render_template_nodes(node[3], loop_context, templates_dir, relative_to, stack))
        elif node_type == "if":
            condition = _evaluate_template_expression(node[1], context)
            body = node[2] if condition else node[3]
            rendered.append(_render_template_nodes(body, context, templates_dir, relative_to, stack))

    return "".join(rendered)


def _evaluate_template_expression(expression: str, context: dict[str, object]) -> object:
    if not expression:
        raise RuntimeError("Template expression must not be empty.")

    globals_for_template = {"__builtins__": {}, "False": False, "None": None, "True": True}
    return eval(expression, globals_for_template, context)


def _evaluate_template_name(expression: str, context: dict[str, object]) -> str:
    try:
        value = ast.literal_eval(expression)
    except (SyntaxError, ValueError):
        value = _evaluate_template_expression(expression, context)

    if not isinstance(value, str):
        raise TypeError("Included template name must be a string.")
    return value


def _template_iterable(value: object) -> Iterable[object]:
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return value
    raise RuntimeError(f"Template for loop needs an iterable value, got {type(value).__name__}.")


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


def _make_request(handler: BaseHTTPRequestHandler, body: str = "") -> Request:
    parsed = urlparse(handler.path)
    query_all = parse_qs(parsed.query)
    query = {key: values[-1] for key, values in query_all.items() if values}
    form_all: dict[str, list[str]] = {}

    content_type = handler.headers.get("Content-Type", "")
    if content_type.startswith("application/x-www-form-urlencoded"):
        form_all = parse_qs(body)

    return Request(
        path=parsed.path,
        query=query,
        query_all=query_all,
        method=handler.command,
        headers=handler.headers,
        body=body,
        form={key: values[-1] for key, values in form_all.items() if values},
        form_all=form_all,
    )


def _read_body(handler: BaseHTTPRequestHandler) -> str:
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length == 0:
        return ""

    body_bytes = handler.rfile.read(content_length)
    return body_bytes.decode("utf-8")


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
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
        501: "Not Implemented",
        503: "Service Unavailable",
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
    if handler.command != "HEAD":
        handler.wfile.write(body_bytes)


def _send_file(handler: BaseHTTPRequestHandler, file_path: Path) -> None:
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = file_path.read_bytes()

    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
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


def _send_method_not_allowed(handler: BaseHTTPRequestHandler, allowed_methods: tuple[str, ...]) -> None:
    headers = {"Allow": ", ".join(allowed_methods)} if allowed_methods else None
    _send_response(
        handler,
        Response(
            "Method Not Allowed",
            status=405,
            content_type="text/plain; charset=utf-8",
            headers=headers,
        ),
    )


def _make_handler(project_dir: Path) -> type[BaseHTTPRequestHandler]:
    static_dir = project_dir / "static"

    class FlaconRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_current_request()

        def do_HEAD(self) -> None:
            self._handle_current_request()

        def do_POST(self) -> None:
            self._handle_current_request()

        def do_PUT(self) -> None:
            self._handle_current_request()

        def do_DELETE(self) -> None:
            self._handle_current_request()

        def do_PATCH(self) -> None:
            self._handle_current_request()

        def do_OPTIONS(self) -> None:
            self._handle_current_request()

        def __getattr__(self, name: str) -> object:
            if name.startswith("do_"):
                return self._handle_current_request
            raise AttributeError(name)

        def _handle_current_request(self) -> None:
            body = "" if self.command == "HEAD" else _read_body(self)
            request = _make_request(self, body)
            self._handle_request(request, serve_static=self.command in {"GET", "HEAD"})

        def _handle_request(self, request: Request, serve_static: bool) -> None:
            if serve_static:
                static_file = _safe_static_path(static_dir, request.path)
                if static_file is not None:
                    _send_file(self, static_file)
                    return

            route_info = ROUTES.get(request.path)
            if route_info is None:
                _send_error_page(self, 404, "Not Found", f"No route for {request.method} {request.path}")
                return

            if request.method not in route_info.methods:
                _send_method_not_allowed(self, route_info.methods)
                return

            try:
                response = _call_route(route_info.handler, request)
                _send_response(self, response)
            except Exception as error:
                _send_error_page(self, 500, "Internal Server Error", str(error))

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write(f"{self.address_string()} - {format % args}\n")

    return FlaconRequestHandler


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
