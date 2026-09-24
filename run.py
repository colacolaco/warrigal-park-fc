"""Entry point for the development and demonstration server.

    python run.py

Configuration is read from environment variables and the optional ``.env``
file; see ``config/env.example``.
"""

from __future__ import annotations

import sys

from app import main

if __name__ == "__main__":
    sys.exit(main())
