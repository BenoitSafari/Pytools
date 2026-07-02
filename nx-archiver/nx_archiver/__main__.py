"""Subcommand dispatcher: ``python -m nx_archiver <command> [options]``.

Entry point used by the ``nx-archiver.sh`` / ``nx-archiver.ps1`` launchers.
Each subcommand delegates to the ``main(argv)`` of the matching CLI module.
The same commands remain available as console scripts (see pyproject.toml)
and via ``python -m nx_archiver.cli.<module>``.
"""

from __future__ import annotations

import importlib
import sys

# Subcommand (kebab-case) -> module providing a ``main(argv)`` function.
COMMANDS = {
    "make-xci": "nx_archiver.cli.make_xci",
    "nsp-to-xci": "nx_archiver.cli.nsp_to_xci",
    "xci-extract": "nx_archiver.cli.xci_extract",
    "xci-modify": "nx_archiver.cli.xci_modify",
    "xci-update": "nx_archiver.cli.xci_update",
    "xci-trim": "nx_archiver.cli.xci_trim",
}


def _print_usage() -> None:
    print("Usage: python -m nx_archiver <command> [options]\n")
    print("Available commands:")
    print("  make-xci      Builds one XCI per game from a folder of NSP/NSZ files")
    print("  nsp-to-xci    Converts one or more NSP/NSZ files into a single XCI")
    print("  xci-extract   Extracts the NCAs from an XCI (option: rebuild as NSP)")
    print("  xci-modify    Adds/removes NCAs in an XCI")
    print("  xci-update    Replaces the update NCAs of an XCI with a new update")
    print("  xci-trim      Removes the 0xFF padding from an XCI (lossless trim)")
    print("\nHelp for a command: python -m nx_archiver <command> --help")


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
