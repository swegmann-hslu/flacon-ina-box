# TIP Server

TIP Server is a small VS Code extension for running the currently opened folder
as a Python-based teaching web application.

The extension bundles `resources/tip_server.py` and starts it with the selected
Python interpreter from the Microsoft Python extension when available.

## Project Layout

```text
my_project/
  static/
    index.html
    style.css
  backend.py
```

## Backend Example

```python
from tip import route

@route("/hello")
def hello():
    return "<h1>Hello from Python</h1>"

@route("/contact")
def contact(request):
    if request.method == "GET":
        return """
        <form action="/contact" method="post">
          <input name="name">
          <button type="submit">Send</button>
        </form>
        """

    name = request.form.get("name", "friend")
    return f"<h1>Hello, {name}!</h1>"
```

## Development

Install dependencies:

```powershell
npm install
```

Compile:

```powershell
npm run compile
```

Run the extension from VS Code with the `Run Extension` launch configuration.
