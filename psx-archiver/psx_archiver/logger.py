"""Logging utilities with timestamped output."""

from datetime import datetime


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{_ts()}] {msg}")


def ok(msg):
    print(f"[OK]   {msg}")


def fail(msg):
    print(f"[FAIL] {msg}")


def skip(msg):
    print(f"[SKIP] {msg}")


def dry_run(action, target):
    """Log a simulated action (--dry-run mode), e.g. "[DRY] Would convert: …"."""
    log(f"[DRY] Would {action}: {target}")
