"""Serve the press-room static site with live reload.

Serves press_room.html at the root and makes data/ assets available.
Reloads the page in the browser when press_room.html is regenerated.
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
from pathlib import Path

from config import SERVE_PORT


PROJECT_ROOT = Path(__file__).parent
DEFAULT_ROOT = PROJECT_ROOT
INDEX_FILE = "press_room.html"


class PressRoomHandler(http.server.SimpleHTTPRequestHandler):
    """Static file handler that serves press_room.html at /."""

    def __init__(self, *args, directory: str = str(DEFAULT_ROOT), **kwargs) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        # Prevent caching so browsers always fetch the latest generated page.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        # Serve the index file at the root path.
        if self.path == "/":
            self.path = f"/{INDEX_FILE}"
        super().do_GET()

    def log_message(self, format: str, *args) -> None:
        # Simple, quiet logging.
        print(f"[{self.log_date_time_string()}] {args[0]} {args[1]} {args[2]}")


def serve(port: int = SERVE_PORT) -> None:
    """Start the static file server."""
    with socketserver.TCPServer(("", port), PressRoomHandler) as httpd:
        print(f"Serving press-room at http://localhost:{port}/")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.shutdown()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Serve the press-room static site.")
    parser.add_argument(
        "--port",
        type=int,
        default=SERVE_PORT,
        help=f"Port to serve on (default: {SERVE_PORT})",
    )
    args = parser.parse_args()
    serve(port=args.port)


if __name__ == "__main__":
    main()
