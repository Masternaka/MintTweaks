"""Allow ``python3 -m minttweaks``."""

import sys

try:
    import gi  # noqa: F401  (only used to check that the GTK bindings exist)
except ImportError:
    sys.stderr.write(
        "MintTweaks needs the GTK 3 Python bindings.\n"
        "Install them with: sudo apt install python3-gi gir1.2-gtk-3.0\n"
    )
    sys.exit(1)

from .app import main  # noqa: E402  (imported after the GTK check)

if __name__ == "__main__":
    sys.exit(main())
