from __future__ import annotations

import argparse
import contextlib
import http.server
import mimetypes
import os
import urllib.parse
import webbrowser
from functools import partial
from typing import Any, Tuple

from .logger import configure_logging, get_logger

log = get_logger(__name__)


def _guess_mime_type(path: str) -> str:
    # Strip query and hash
    parsed = urllib.parse.urlsplit(path)
    p = parsed.path
    if p.endswith(".gz"):
        p = p[:-3]
    ext = os.path.splitext(p)[1].lower()

    # Extend built-in types
    extra = {
        ".json": "application/json",
        ".ndjson": "application/x-ndjson",
        ".atom": "application/atom+xml",
        ".xml": "application/xml",
        ".csv": "text/csv",
        ".txt": "text/plain; charset=utf-8",
        ".html": "text/html; charset=utf-8",
    }
    if ext in extra:
        return extra[ext]
    guess = mimetypes.types_map.get(ext)
    return guess or "application/octet-stream"


class SignalHarvesterHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        directory: str | None = None,
        no_cache: bool = False,
        cors: bool = False,
        **kwargs: Any
    ) -> None:
        self.no_cache = no_cache
        self.cors = cors
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        try:
            log.info("%s - %s", self.address_string(), fmt % args)
        except Exception:
            pass

    def guess_type(self, path: str) -> str:  # type: ignore[override]
        return _guess_mime_type(str(path))

    def end_headers(self) -> None:
        # Add common headers
        try:
            if self.no_cache:
                self.send_header("Cache-Control", "no-store")
            if self.cors:
                self.send_header("Access-Control-Allow-Origin", "*")
            # Add gzip encoding based on URL path
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path.endswith(".gz"):
                # Content-Type already guessed by our guess_type (underlying)
                self.send_header("Content-Encoding", "gzip")
        except Exception:
            pass
        super().end_headers()


def make_server(
    base_dir: str,
    host: str = "127.0.0.1",
    port: int = 0,
    no_cache: bool = True,
    cors: bool = True,
) -> Tuple[http.server.ThreadingHTTPServer, str]:
    Handler = partial(SignalHarvesterHandler, directory=base_dir, no_cache=no_cache, cors=cors)
    httpd = http.server.ThreadingHTTPServer((host, port), Handler, bind_and_activate=True)
    bound_host, bound_port = httpd.server_address[:2]
    url = f"http://{bound_host.decode() if isinstance(bound_host, bytes) else bound_host}:{bound_port}/"
    return httpd, url


def serve_forever(
    base_dir: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
    no_cache: bool = True,
    cors: bool = True,
) -> int:
    httpd, url = make_server(base_dir, host=host, port=port, no_cache=no_cache, cors=cors)
    log.info("Serving %s on %s", base_dir, url)
    if open_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(url)
    try:
        httpd.serve_forever()
        return 0
    except KeyboardInterrupt:
        log.info("Shutting down...")
        return 0
    finally:
        with contextlib.suppress(Exception):
            httpd.shutdown()
            httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest-serve",
        description="Serve a snapshots directory with correct MIME types and gzip encoding."
    )
    parser.add_argument("--dir", dest="base_dir", required=True, help="Directory to serve (snapshots base)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Open browser to the server URL")
    parser.add_argument("--no-cache", dest="no_cache", action="store_true", help="Send Cache-Control: no-store")
    parser.add_argument("--cors", dest="cors", action="store_true", help="Enable Access-Control-Allow-Origin: *")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    return serve_forever(
        base_dir=args.base_dir,
        host=args.host,
        port=args.port,
        open_browser=args.open_browser,
        no_cache=args.no_cache,
        cors=args.cors,
    )


if __name__ == "__main__":
    raise SystemExit(main())
