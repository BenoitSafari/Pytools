"""External tool execution (7z, chdman, maxcso/ciso).

Centralizes launching a subprocess, checking the return code, logging the
result and cleaning up the output on failure — a pattern previously duplicated
in `convert.py` and `extract.py`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from psx_archiver.logger import fail, ok


def _remove(path: Path) -> None:
    """Remove *path*, whether it is a file or a directory."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def run_tool(cmd: list[str], name: str, cleanup: Path | str | None = None) -> bool:
    """Run the external tool *cmd* and log the result under *name*.

    Returns ``True`` on success (return code 0), logging ``ok(name)``.
    On failure: logs ``fail`` with the last line of *stderr*, removes *cleanup*
    (partially written file or directory) if provided, and returns ``False``.
    """
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode == 0:
        ok(name)
        return True

    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    detail = f" — {stderr.splitlines()[-1]}" if stderr else ""
    fail(f"{name}{detail}")

    if cleanup is not None:
        _remove(Path(cleanup))
    return False
