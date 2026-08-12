from typing import Callable


class Request:
    path: str
    query: dict[str, str]
    query_all: dict[str, list[str]]
    method: str
    headers: object
    body: str
    form: dict[str, str]
    form_all: dict[str, list[str]]


class Response:
    body: str | bytes
    status: int
    content_type: str
    headers: dict[str, str] | None

    def __init__(
        self,
        body: str | bytes,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None: ...


def route(path: str) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


def text(body: str, status: int = 200) -> Response: ...


def html_page(body: str, status: int = 200) -> Response: ...


def json(data: str, status: int = 200) -> Response: ...


def redirect(location: str, status: int = 302) -> Response: ...
