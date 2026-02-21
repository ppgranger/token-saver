import os

__version__ = "1.3.1"


def data_dir() -> str:
    """Return the token-saver data directory (for DB, config, logs).

    Uses %APPDATA%/token-saver on Windows, ~/.token-saver on Unix.
    """
    if os.name == "nt":
        appdata = os.environ.get(
            "APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        )
        return os.path.join(appdata, "token-saver")
    return os.path.join(os.path.expanduser("~"), ".token-saver")
