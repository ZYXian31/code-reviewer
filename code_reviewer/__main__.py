"""启动入口：python -m code_reviewer"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
