import html
from flacon import html_page, route, text



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


@route("/contact")
def contact(request):
    if request.method == "GET":
        return """
        <h1>Contact Form</h1>
        <form action="/contact" method="post">
          <label>
            Name
            <input name="name">
          </label>
          <label>
            Message
            <textarea name="message"></textarea>
          </label>
          <button type="submit">Send</button>
        </form>
        """

    name = html.escape(request.form.get("name", "friend"))
    message = html.escape(request.form.get("message", ""))
    return html_page(f"""
    <h1>Thank you, {name}!</h1>
    <p>Your message was:</p>
    <p>{message}</p>
    """)
