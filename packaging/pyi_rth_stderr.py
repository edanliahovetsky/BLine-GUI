# PyInstaller runtime hook to fix sys.stderr issue on Windows
# This ensures sys.stdout and sys.stderr are always available

import sys
import os

# If running as a frozen Windows GUI app without console
if sys.stderr is None or sys.stdout is None:
    # Redirect to AppData to prevent crashes
    try:
        # Use AppData for logs (persistent, user-accessible)
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            log_dir = os.path.join(appdata, "BLine", "logs")
        else:
            # Fallback for other platforms
            log_dir = os.path.expanduser("~/.bline/logs")

        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "bline.log")
        sys.stderr = open(log_file, "w", encoding="utf-8", errors="ignore")
        sys.stdout = sys.stderr
    except Exception:
        # Fallback: use null device
        import io

        sys.stderr = io.StringIO()
        sys.stdout = io.StringIO()
