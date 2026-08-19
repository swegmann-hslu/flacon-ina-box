# Changelog

All notable changes to the Flacon in a Box extension will be documented in this file.

## Next release

- Adds a command to create a starter Flacon project structure without overwriting existing files.
- Keeps backend `print()` output visible in the Flacon output channel after the server finishes starting.
- Uses `resources/flacon_server.py` as the single source for the Flacon runtime and generates the Pylance stub from it.
- Searches the project root when `backend.py` imports sibling modules in the project root folder
- Extends the list of known status code messages for responses

## 0.1.0

- First publishable Marketplace version of Flacon in a Box.
- Bundles the Python Flacon runtime and Pylance import stub.
- Adds commands to start, stop, toggle, and open the server from VS Code.
- Adds a command to configure Pylance for `from flacon import ...` imports in the current workspace.
- Adds Marketplace metadata, GPLv3 license text, support information, changelog, and extension icon.
