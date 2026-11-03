"""Allow ``python -m accviz`` as an alternative to the ``accviz`` console script."""

import sys

from accviz.cli import main

if __name__ == "__main__":
    sys.exit(main())
