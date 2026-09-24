"""Production entry point.

A WSGI-style callable is not needed because the application serves its own HTTP
responses, but deployment platforms and process managers look for a module-level
object, so this file exposes ``application`` as a factory and ``server`` for
scripts that expect a pre-built server.

    APP_ENV=production APP_HOST=0.0.0.0 APP_PORT=8080 python wsgi.py

See ``docs/DEPLOYMENT.md``.
"""

from __future__ import annotations

from app import build_server
from config import get_settings


def application():
    """Factory used by process managers: returns a ready HTTP server."""
    return build_server(get_settings())


def serve_forever() -> int:
    settings = get_settings()
    server = application()
    print(f"Warrigal Park FC listening on http://{settings.host}:{settings.port}/")
    print(settings.describe())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_forever())
