---
layout: default
title: User Guide
---

{% raw %}

# Flacon in a Box User Guide

Documentation version: **current `main` branch implementation, based on package
version 0.2.0 plus the `Unreleased` changes in `CHANGELOG.md`**

This page describes the user-facing behavior of the Flacon in a Box VS Code
extension and the bundled `flacon` Python package interface.

## What Flacon in a Box Is

Flacon in a Box is a small VS Code extension for introductory web programming
exercises. It runs the currently opened folder as a tiny Flask-inspired Python
web application, without requiring students to install or understand a full web
framework first.

The extension is mainly an educational tool. It is meant for classroom
exercises, demonstrations, and small experiments where the important learning
goals are:

- serving static HTML, CSS, JavaScript, and image files;
- adding a few backend routes in Python;
- reading query parameters and form submissions;
- returning HTML, text, redirects, or simple JSON responses;
- seeing cause and effect quickly inside VS Code.

It is not designed for production applications. It does not provide the security
features, deployment model, scalability, configuration system, or broad HTTP
surface of a real production framework.

## Requirements

- VS Code 1.90.0 or newer.
- The Microsoft Python extension for VS Code.
- A working Python 3.10 through 3.14 interpreter available to VS Code.
- One project folder opened directly in VS Code. Flacon works with one opened
  workspace folder at a time.

The bundled Flacon server uses Python 3.10-compatible syntax and standard
library APIs. No Python 3.11, 3.12, 3.13, or 3.14-specific runtime features are
required. Python 3.15 is expected to work from the current source code, but
should be confirmed with a final Python 3.15 release before it is listed as a
formally supported version.

## Project Layout

A minimal Flacon project has this shape:

```text
my_project/
  static/
    index.html
    style.css
  backend.py
```

The `static/` folder is served as static web content for `GET` and `HEAD`
requests. A browser request for `/` loads `static/index.html`. A request such as
`/style.css` loads `static/style.css`, and `/images/logo.png` loads
`static/images/logo.png`.

The optional `backend.py` file contains Python route functions. If `backend.py`
is missing, Flacon acts as a simple static file server.

## Getting Started

1. Open an empty folder in VS Code.
2. Run `Flacon: Setup Initial Project Structure` from the Command Palette.
3. Run `Flacon: Start`, or click the `Flacon` status bar item.
4. When the server starts, click the status bar URL or run
   `Flacon: Open in Browser`.
5. Open `static/index.html`, change the heading, save, and refresh the browser.
6. Open `backend.py` and add this route:

```python
from flacon import html_page, route


@route("/hello")
def hello():
    return html_page("<h1>Hello from Python</h1>")
```

7. Save `backend.py`. Flacon restarts the server automatically when this file
   changes.
8. Open `/hello` in the browser, for example `http://localhost:8000/hello`.

Flacon listens on `localhost` and tries the ports `80`, `8000`, and
`8080`, using the first available one. The actual URL is shown in the status
bar and in the `Flacon` output channel.

## VS Code Features

The extension contributes these commands:

| Command | What it does |
| --- | --- |
| `Flacon: Setup Initial Project Structure` | Creates `static/`, `static/index.html`, and `backend.py` if they do not already exist. Existing files are not overwritten. |
| `Flacon: Start` | Starts the Flacon server for the currently opened folder. If the server is already running, this opens it in the browser. |
| `Flacon: Stop` | Stops the running Flacon server. |
| `Flacon: Start/Stop` | Starts Flacon when stopped, or stops it when running. |
| `Flacon: Open in Browser` | Opens the running Flacon server URL in the default browser. |
| `Flacon: Fix Pylance warning for 'flacon'` | Adds the bundled Flacon helper path to `python.analysis.extraPaths` for the workspace so Pylance recognizes imports such as `from flacon import route`. |

The status bar shows:

- a play icon and `Flacon` when the server is stopped;
- a spinning indicator while the server is starting;
- the running server URL when startup succeeds;
- a stop button while the server is running.

The `Flacon` output channel shows startup information, the selected Python
interpreter, the server script path, request log lines, backend `print()` output,
and stop or error messages.

While Flacon is running, changes to the workspace root `backend.py` file restart
the server automatically. Imported helper modules are not watched; restart
Flacon manually after changing those files.

## Backend Basics

Import the helpers you need from `flacon` in `backend.py`:

```python
from flacon import html_page, json, redirect, render_template, route, text
```

Route functions can accept no arguments:

```python
@route("/about")
def about():
    return html_page("<h1>About</h1>")
```

Or one argument, usually called `request`:

```python
@route("/greet")
def greet(request):
    name = request.query.get("name", "World")
    return html_page(f"<h1>Hello, {name}</h1>")
```

Route functions with more than one parameter are rejected.

## The `flacon` Package Interface

This section documents the intended outward-facing interface for students and
course exercises. Internal helper functions in `flacon_server.py` are omitted.

### `@route(path, methods=None)`

Registers a function as the handler for a URL path.

```python
@route("/hello")
def hello():
    return "Hello"
```

If `path` does not start with `/`, Flacon adds it automatically. If you do not
pass `methods=...`, the route accepts only `GET`.

The `methods` value must be an iterable of method names, such as
`["GET", "POST"]`. Do not pass a single string such as `"POST"`. Method names
are stripped, converted to uppercase, and duplicate entries are ignored. Empty
method names are rejected.

Important behavior:

- static files are served first for `GET` and `HEAD` requests;
- backend routes handle matching paths after static file lookup;
- pass `methods=[...]` to list the HTTP methods a route accepts, including
  `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`, and custom method
  names;
- a request method that is not listed for a matching route returns
  `405 Method Not Allowed`;
- `405 Method Not Allowed` responses include an `Allow` header when the route
  has allowed methods;
- `HEAD` requests do not send a response body, even when a route returns one;
- a missing route returns `404 Not Found`;
- an exception in a route returns `500 Internal Server Error`.

`HEAD` is not automatically added for a `GET` route. If you want a backend route
to accept `HEAD`, include it explicitly:

```python
@route("/health", methods=["GET", "HEAD"])
def health():
    return text("OK")
```

The same route function may handle more than one method. The route function can
still check `request.method` to decide what to do:

```python
@route("/items", methods=["GET", "POST"])
def items(request):
    if request.method == "GET":
        return html_page("<h1>Items</h1>")
    if request.method == "POST":
        return text("Created", 201)
```

### `Request`

When a route function declares one parameter, Flacon passes a `Request` object.

| Attribute | Type | Meaning |
| --- | --- | --- |
| `path` | `str` | The requested URL path, such as `"/hello"`. |
| `query` | `dict[str, str]` | Query string values from the URL. If a key appears more than once, this contains the last value. |
| `query_all` | `dict[str, list[str]]` | Query string values from the URL, preserving all values for repeated keys. |
| `method` | `str` | The HTTP method, for example `"GET"`, `"POST"`, `"PUT"`, `"DELETE"`, `"PATCH"`, `"OPTIONS"`, or `"HEAD"`. |
| `headers` | object | Request headers sent by the browser. |
| `body` | `str` | The raw request body decoded as UTF-8 text. |
| `form` | `dict[str, str]` | Submitted form values for requests with `application/x-www-form-urlencoded` data. If a key appears more than once, this contains the last value. |
| `form_all` | `dict[str, list[str]]` | Submitted form values, preserving all values for repeated keys. |

Example:

```python
@route("/search")
def search(request):
    term = request.query.get("q", "")
    return html_page(f"<p>You searched for {term}</p>")
```

### `Response`

Represents a complete HTTP response.

```python
Response(
    body="<h1>Created</h1>",
    status=201,
    content_type="text/html; charset=utf-8",
    headers={"X-Example": "yes"},
)
```

Most users should prefer the helper functions below instead of creating
`Response` values directly.

### `html_page(body, status=200)`

Creates an HTML response.

```python
return html_page("<h1>Hello</h1>")
```

Use this when a backend route returns HTML that should be rendered by the
browser.

### `text(body, status=200)`

Creates a plain-text response.

```python
return text("Hello")
```

Use this for simple text output, debugging routes, or exercises where HTML is
not important.

### `json(data, status=200)`

Creates a JSON response.

```python
return json('{"message": "Hello"}')
```

Pass a JSON string. Flacon does not convert Python dictionaries to JSON
automatically.

### `redirect(location, status=302)`

Creates a redirect response.

```python
return redirect("/")
```

Use this after a form submission when the browser should navigate to another
URL.

### `render_template(template_name, **context)`

Renders a template from the project `templates/` folder and returns the rendered
HTML string.

```text
my_project/
  backend.py
  templates/
    hello.html
```

```python
@route("/hello")
def hello():
    return render_template("hello.html", name="Ada")
```

```html
<h1>Hello, {{ name }}</h1>
```

Supported template syntax:

| Syntax | Meaning |
| --- | --- |
| `{{ expression }}` | Inserts the value of a Python expression, HTML-escaped. |
| `{% for item in items %}` ... `{% endfor %}` | Repeats a block for each value in an iterable. |
| `{% if condition %}` ... `{% endif %}` | Renders a block when the condition is true. |
| `{% if condition %}` ... `{% else %}` ... `{% endif %}` | Chooses between two blocks. |
| `{% include 'other.html' %}` | Renders another template file using the same variables. |

Template names must be relative and must stay inside the `templates/` folder.
Include cycles are rejected.

This is intentionally only a small teaching template language, not full Jinja.

## Return Values From Routes

Route functions can return:

| Return value | Result |
| --- | --- |
| `str` | Sent as HTML with status `200`. |
| `bytes` | Sent as raw bytes with status `200` and HTML content type unless wrapped in `Response`. |
| `Response` | Sent using the response status, content type, and headers. |
| `None` | Sends an empty HTML response. |

For `HEAD` requests, Flacon still sends the status code and headers, including
`Content-Length`, but does not send the response body.

## Forms

Flacon can read normal HTML form submissions:

```html
<form action="/contact" method="post">
  <input name="name">
  <button type="submit">Send</button>
</form>
```

```python
@route("/contact", methods=["GET", "POST"])
def contact(request):
    if request.method == "GET":
        return render_template("contact.html")

    name = request.form.get("name", "friend")
    return html_page(f"<h1>Hello, {name}</h1>")
```

Only `application/x-www-form-urlencoded` form data is parsed into
`request.form`. Other request bodies are still available as `request.body`.

## Limits and Intended Use

Flacon deliberately keeps the programming model small. Users should know these
limits:

- routes accept `GET` by default, or the explicit methods listed with
  `@route(..., methods=[...])`;
- `HEAD` is handled by the server, but backend routes must list it explicitly;
- it is intended for local development in VS Code;
- it listens on `localhost` only;
- it serves one opened workspace folder;
- it is not a production web server;
- it does not watch imported Python helper files for automatic restart;
- it does not implement full Flask, Jinja, cookies, sessions, authentication, or
  deployment features.

## Troubleshooting

If the browser does not open:

- check that Flacon is running in the status bar;
- run `Flacon: Open in Browser`;
- check the actual URL in the `Flacon` output channel.

If `from flacon import route` is underlined by Pylance:

- run `Flacon: Fix Pylance warning for 'flacon'`;
- make sure you opened the project folder directly, not a multi-root workspace.

If the server does not start:

- check the selected Python interpreter in VS Code;
- inspect the `Flacon` output channel;
- make sure one of the ports `80`, `8000`, or `8080` is available.

If changes to backend code are not visible:

- save `backend.py`;
- restart Flacon manually if you changed imported helper modules;
- refresh the browser.

If template expressions or template blocks do not work:

- check that template expressions use `{{` and `}}`, for example
  `{{ name }}`;
- check that template tags use `{%` and `%}`, for example
  `{% for item in items %}`;
- make sure there is no space between the curly brace and the percent sign.
  Write `{% ... %}`, not `{ % ... % }`.

## Reporting Problems

Report issues at:

<https://github.com/swegmann-hslu/flacon-ina-box/issues>

Include:

- your VS Code version;
- your operating system;
- the selected Python interpreter;
- the contents of the `Flacon` output channel;
- a small example project or route that reproduces the problem.

{% endraw %}
