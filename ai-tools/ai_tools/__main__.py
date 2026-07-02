"""Subcommand dispatcher: ``python -m ai_tools <command> [options]``.

This is the entry point used by the ``ai-tools.sh`` / ``ai-tools.ps1`` launchers.
Each subcommand delegates to the ``main(argv)`` of the matching CLI module.
"""

from __future__ import annotations

import importlib
import sys

# Subcommand (kebab-case) -> module providing a ``main(argv)`` function.
COMMANDS = {
    "claude-export": "ai_tools.cli.claude_export",
    "img-resize": "ai_tools.cli.img_resize",
}


def _print_usage() -> None:
    print("Usage: python -m ai_tools <command> [options]\n")
    print("Available commands:")
    print("  claude-export   Export local Claude Code/Desktop data into a ZIP")
    print("  img-resize      Resize and compress images (PNG/JPEG/WebP)")
    print("\nHelp for a command: python -m ai_tools <command> --help")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        _print_usage()
        return 0

    command, *rest = argv
    module_name = COMMANDS.get(command)
    if module_name is None:
        print(f"Unknown command: {command}\n", file=sys.stderr)
        _print_usage()
        return 2

    module = importlib.import_module(module_name)
    return module.main(rest) or 0


if __name__ == "__main__":
    raise SystemExit(main())
