# BLine-GUI

**BLine** is an open-source path generation and tracking suite designed for **holonomic drivetrains** (swerve, mecanum, etc.) made by students for students. It's built around simplicity and performance in time-constrained environments where quick iteration and rapid empirical testing prove advantageous.

📚 **[Documentation](https://edanliahovetsky.github.io/BLine-Docs/)** — full guides, tutorials, and reference.

☕ **[BLine-Lib](https://github.com/edanliahovetsky/BLine-Lib)** — the BLine Java library.

💬 **[Chief Delphi Thread](https://www.chiefdelphi.com/t/introducing-bline-a-new-rapid-polyline-autonomous-path-planning-suite/509778)** — discussion, feedback, and announcements.

![BLine GUI Demo](assets/readme/gui_demo.gif)

![Robot Following BLine Path](assets/readme/cone-demo.gif)

## Installation

### Prebuilt Binaries (Recommended)

Download the latest release for your platform from the [**Releases page**](https://github.com/edanliahovetsky/BLine-GUI/releases/latest).

#### Windows

Choose one of the following:

**Installer (Recommended)**
1. Download `BLine-{version}-Setup.exe`
2. Run the installer and follow the wizard
3. Launch BLine from the Start Menu

**Portable (No Installation)**
1. Download `BLine-{version}-Windows-Portable.zip`
2. Extract anywhere
3. Run `BLine.exe`

No Python installation required—everything is bundled!

#### Linux

**AppImage (All Distributions)**
1. Download `BLine-x86_64.AppImage`
2. Make it executable:
   ```bash
   chmod +x BLine-x86_64.AppImage
   ```
3. Run it:
   ```bash
   ./BLine-x86_64.AppImage
   ```

No installation or dependencies required!

#### macOS

macOS builds are not currently available as prebuilt binaries. See [Install from Source](#install-from-source) below.

---

### Install from Source

If you prefer to install via Python package or need the latest development version:

**Quick Install (all platforms):**
```bash
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

Then run `bline` from anywhere. Don't have pipx? See platform-specific instructions below.

<details>
<summary><strong>Windows</strong></summary>

#### Using pipx (Recommended)

```powershell
# Install pipx (one-time setup)
pip install pipx
pipx ensurepath

# Restart your terminal, then install BLine
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

**Troubleshooting:** If you get a PySide6 build error, install Python 3.11 or 3.12 from [python.org](https://www.python.org/downloads/windows/) and specify it:

```powershell
py -3.12 -m pip install --upgrade pip pipx
py -3.12 -m pipx ensurepath
py -3.12 -m pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

#### Using pip

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

</details>

<details>
<summary><strong>macOS</strong></summary>

#### Using Homebrew (Recommended)

```bash
# Install Homebrew if needed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install pipx and BLine
brew install pipx
pipx ensurepath
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

#### Using pip

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

</details>

<details>
<summary><strong>Linux</strong></summary>

#### Using pipx (Recommended)

```bash
# Install pipx
# Debian/Ubuntu:
sudo apt install pipx

# Fedora:
sudo dnf install pipx

# Arch:
sudo pacman -S python-pipx

# Install BLine
pipx ensurepath
pipx install git+https://github.com/edanliahovetsky/BLine-GUI.git
```

**Troubleshooting:** If you get a PySide6 build error, specify Python 3.11 or 3.12:

```bash
pipx install --python python3.12 git+https://github.com/edanliahovetsky/BLine-GUI.git
```

#### Using pip

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

</details>

## Quick Start

**Binary installation:** Launch BLine from your Start Menu (Windows), Applications folder, or run the executable directly.

**Python package installation:** Run `bline` from any terminal. To create a desktop shortcut with the BLine icon, run `bline --create-shortcut`.

For guides on path elements, constraints, the GUI interface, and more, see the **[Documentation](https://edanliahovetsky.github.io/BLine-Docs/)**.

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

### Development Workflow

Common tasks are provided via the `Makefile`:

| Command       | Description                         |
|---------------|-------------------------------------|
| `make install`| Install dependencies into `.venv`   |
| `make run`    | Launch the GUI                      |
| `make fmt`    | Run Black + Ruff formatting         |
| `make lint`   | Run Ruff and MyPy                   |
| `make test`   | Execute the pytest suite            |

### Project Layout

- `main.py` — Application entry point
- `models/` — Path data structures and simulation logic
- `ui/` — Qt widgets (canvas, sidebar, dialogs, main window)
- `utils/` — Project persistence, undo stack, helpers
- `example_project/` — Sample configs and paths for experimentation

### Tests & CI

Unit tests live under `tests/` and focus on the pure-Python logic in `models/` and `utils/`.
GitHub Actions runs `ruff`, `black --check`, `mypy`, and `pytest` on every push and pull request.

## License

BSD 3-Clause License — See [LICENSE](LICENSE) file.
