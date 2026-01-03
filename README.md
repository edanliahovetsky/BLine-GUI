# BLine-GUI
Check out 🔧 **[BLine-Lib](https://github.com/edanliahovetsky/BLine-Lib)** for conceptual documentation and general overview.

An editor and simulator for tuning BLine paths, built with PySide6.

## Installation

### macOS

#### Option A: Using Homebrew (Recommended)

If you don't have Homebrew, install it first:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install BLine:
```bash
# Install pipx (one-time setup)
brew install pipx
pipx ensurepath

# Restart your terminal, then install BLine
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

#### Option B: Using pip (No Homebrew)

```bash
# Create a folder for BLine
mkdir -p ~/Applications/BLine
cd ~/Applications/BLine

# Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/edanliahovetsky/BLine-GUI.git

# Run BLine (from this folder, with venv activated)
bline
```

To run BLine later with this method:
```bash
cd ~/Applications/BLine
source .venv/bin/activate
bline
```

### Windows

#### Option A: Using pipx (Recommended)

```powershell
# Install pipx (one-time setup)
pip install pipx
pipx ensurepath

# Restart your terminal, then install BLine
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

#### Option B: Using pip

```powershell
# Create a folder for BLine
mkdir %USERPROFILE%\BLine
cd %USERPROFILE%\BLine

# Create a virtual environment and install
python -m venv .venv
.venv\Scripts\activate
pip install git+https://github.com/edanliahovetsky/BLine-GUI.git

# Run BLine
bline
```

To run BLine later with this method:
```powershell
cd %USERPROFILE%\BLine
.venv\Scripts\activate
bline
```

### Linux

#### Option A: Using pipx (Recommended)

```bash
# Debian/Ubuntu
sudo apt install pipx

# Fedora
sudo dnf install pipx

# Arch
sudo pacman -S python-pipx
```

Then:
```bash
pipx ensurepath

# Restart your terminal, then install BLine
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

#### Option B: Using pip (No sudo required)

```bash
# Create a folder for BLine
mkdir -p ~/Applications/BLine
cd ~/Applications/BLine

# Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/edanliahovetsky/BLine-GUI.git

# Run BLine
bline
```

To run BLine later with this method:
```bash
cd ~/Applications/BLine
source .venv/bin/activate
bline
```

## Usage

After installation, run BLine from anywhere:

```bash
bline
```

### Create a Desktop Shortcut

To create a desktop shortcut with the BLine icon:

```bash
bline --create-shortcut
```

This opens a dialog where you can choose to add shortcuts to your Desktop and/or Start Menu (Windows) / Applications folder (macOS/Linux).

### Updating

To update to the latest version:

```bash
# If you used pipx:
pipx upgrade bline

# If you used pip (with venv activated):
pip install --upgrade git+https://github.com/edanliahovetsky/BLine-GUI.git
```

### Uninstalling

```bash
# If you used pipx:
pipx uninstall bline

# If you used pip:
# Just delete the BLine folder you created
```

---

## Development

For contributors who want to work on BLine itself:

### Requirements

- Python 3.11+
- PySide6 (installed automatically via `requirements.txt`)

### Setup

```bash
git clone https://github.com/edanliahovetsky/BLine-GUI.git
cd BLine-GUI
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
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

