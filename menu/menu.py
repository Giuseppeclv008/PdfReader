"""menu/menu.py — interactive CLI menu, driven entirely by the converter registry"""

from pathlib import Path

from converters.base import all_formats


def show_menu() -> tuple[str, str, dict]:
    formats = all_formats()
    keys = list(formats.keys())

    print("\n" + "=" * 55)
    print("            PDF CONVERTER — Choose format")
    print("=" * 55)
    for key, fmt in formats.items():
        print(f"  {key}. {fmt.name}")
        print(f"     └─ {fmt.description}")
    print("=" * 55)

    while True:
        choice = input(f"Choice [{keys[0]}-{keys[-1]}]: ").strip()
        if choice in formats:
            fmt = formats[choice]
            print(f"\n→ Format: {fmt.name}\n")
            extra_kwargs = fmt.extra_args() if fmt.extra_args else {}
            return choice, fmt.ext, extra_kwargs
        print(f"  Enter one of: {', '.join(keys)}.")


def get_input_path() -> Path:
    while True:
        raw = input("Path to PDF file or folder: ").strip().strip("'\"")
        p = Path(raw).expanduser()
        if p.exists():
            return p
        print(f"  Not found: {p}")
