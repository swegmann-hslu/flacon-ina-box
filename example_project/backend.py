from tip import html_page, route, text


@route("/hello")
def hello():
    return "<h1>Hello from the backend</h1><p>This HTML was created by Python.</p>"


@route("/greet")
def greet(request):
    name = request.query.get("name", "World")
    return html_page(f"<h1>Hello, {name}!</h1><p>Try /greet?name=Ada</p>")


@route("/plain")
def plain_text():
    return text("This is plain text from Python.")
