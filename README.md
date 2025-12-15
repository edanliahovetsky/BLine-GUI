# BLine-GUI
Check out 🔧 **[BLine-Lib](https://github.com/edanliahovetsky/BLine-Lib)** for conceptual documentation and general overview.

An editor and simulator for tuning BLine paths, built with PySide6.

## Requirements

- Python 3.11+
- PySide6 (installed automatically via `requirements.txt`)

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Alternatively, run `./scripts/dev_env.sh` to create the virtualenv, install dependencies, and launch the GUI in one step.

## Development Workflow

Common tasks are provided via the `Makefile`:

| Command       | Description                         |
|---------------|-------------------------------------|
| `make install`| Install dependencies into `.venv`   |
| `make run`    | Launch the GUI                      |
| `make fmt`    | Run Black + Ruff formatting         |
| `make lint`   | Run Ruff and MyPy                   |
| `make test`   | Execute the pytest suite            |

## Tests & CI

Unit tests live under `tests/` and focus on the pure-Python logic in `models/` and `utils/`.
GitHub Actions runs `ruff`, `black --check`, `mypy`, and `pytest` on every push and pull request.

## Project Layout

- `ui/` – Qt widgets (canvas, sidebar, dialogs, main window package)
- `models/` – path data structures and simulation logic
- `utils/` – project persistence, undo stack, helpers
- `example_project/` – sample configs and paths for experimentation

