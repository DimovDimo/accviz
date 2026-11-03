"""Streamlit entry point. Run with ``accviz dashboard`` or ``streamlit run src/accviz/dashboard.py``."""

import sys
from pathlib import Path

try:  # normally the package is installed
    from accviz.ui import main
except ImportError:  # pragma: no cover - fall back to the source tree
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from accviz.ui import main

main()
