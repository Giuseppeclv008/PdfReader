"""main.py — entry point for the file converter application"""

import sys
from pathlib import Path

import converters  # noqa: F401 — registers all built-in formats
from menu.menu import show_menu, get_input_path
from core.core import convert_one, convert_folder
from converters.base import get_format

if __name__ == "__main__":
    choice, extra_kwargs = show_menu()
    fmt = get_format(choice)

    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1]).expanduser()
        if not input_path.exists():
            sys.exit(f"Not found: {input_path}")
    else:
        input_path = get_input_path()

    if len(sys.argv) >= 3:
        out_dir = Path(sys.argv[2]).expanduser()
    else:
        if input_path.is_dir():
            out_dir = input_path.parent / f"{input_path.name}_output"
        else:
            out_dir = input_path.parent / "output"

    if input_path.is_dir():
        convert_folder(input_path, out_dir, choice, **extra_kwargs)
    elif input_path.suffix.lower() == fmt.source_ext:
        convert_one(input_path, out_dir, choice, **extra_kwargs)
    else:
        sys.exit(
            f"Format '{fmt.name}' expects {fmt.source_ext} files, "
            f"got: {input_path.suffix or '(no extension)'}"
        )
