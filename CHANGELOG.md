# Changelog

All notable changes to the Flacon in a Box extension will be documented in this file.

## Unreleased

- Restarts the running Flacon server automatically when the workspace root `backend.py` file is saved, created, or deleted.
- Adds `render_template()` for small Jinja-inspired templates with value insertion, loops, conditionals, and includes.
- Adds `methods=[...]` to `@route()` so routes can explicitly accept methods such as `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`, and custom HTTP method names.
- Returns `405 Method Not Allowed` automatically when a request uses a method that is not listed for the matching route.
- Binds the local Flacon server to `localhost` instead of all network interfaces.

## 0.2.0 - 2026-08-19

- Adds a command to create a starter Flacon project structure without overwriting existing files.
- Keeps backend `print()` output visible in the Flacon output channel after the server finishes starting.
- Uses `resources/flacon_server.py` as the single source for the Flacon runtime and generates the Pylance stub from it.
- Searches the project root when `backend.py` imports sibling modules in the project root folder.
- Extends the list of known status code messages for responses.

## 0.1.0

- First publishable Marketplace version of Flacon in a Box.
- Bundles the Python Flacon runtime and Pylance import stub.
- Adds commands to start, stop, toggle, and open the server from VS Code.
- Adds a command to configure Pylance for `from flacon import ...` imports in the current workspace.
- Adds Marketplace metadata, GPLv3 license text, support information, changelog, and extension icon.
