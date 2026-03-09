import sys
import traceback
from pathlib import Path

from monitor_info_app import main as run_monitor_info_app


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def write_exception_log() -> None:
    try:
        (runtime_root() / "monitor_insight_error.log").write_text(
            traceback.format_exc(),
            encoding="utf-8",
        )
    except OSError:
        pass


if __name__ == "__main__":
    try:
        raise SystemExit(run_monitor_info_app())
    except SystemExit:
        raise
    except Exception:
        write_exception_log()
        raise SystemExit(1)
