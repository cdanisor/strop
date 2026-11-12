#!/usr/bin/env python3
"""
Small static server for the Strop UI.

Tuned for the Raspberry Pi 1:
  * index.html is read once and re-read only when it changes on disk;
  * static assets get a long browser cache (index.html references them
    with a ?v= version, bump it when they change) so phones don't re-download;
  * per-request access logs are suppressed to spare the SD card / journal;
  * a threaded server so one slow client does not block the others.
"""
import http.server
import json
import os
import socketserver
import sys

PORT = 8000
# Resolve paths from this file so the server works from any working directory
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(DIRECTORY)
INDEX_PATH = os.path.join(DIRECTORY, 'index.html')

# Only these file types are served (keeps server.py, README etc. private)
STATIC_TYPES = {
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.svg': 'image/svg+xml',
}
STATIC_MAX_AGE = 86400  # 1 day

# Try to load configuration from root config.json
config = {}
try:
    with open(os.path.join(PROJECT_ROOT, 'config.json'), 'r') as f:
        config = json.load(f)
except Exception as e:
    print(f"Warning: Could not load config.json: {e}")

api_url = config.get('api_url', 'http://localhost:5000/api')

_index_cache = {'mtime': None, 'body': b''}


def get_index() -> bytes:
    """index.html with the API URL injected, cached until the file changes."""
    mtime = os.path.getmtime(INDEX_PATH)
    if _index_cache['mtime'] != mtime:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        injection = f"<script>window.API_BASE_URL = {json.dumps(api_url)};</script>\n</head>"
        _index_cache['body'] = content.replace('</head>', injection, 1).encode('utf-8')
        _index_cache['mtime'] = mtime
    return _index_cache['body']


class UIRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        # Silence access logs; errors still go through log_error
        pass

    def log_error(self, format, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send(self, body: bytes, content_type: str, cache: str):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        if path in ('/', '/index.html'):
            try:
                self._send(get_index(), 'text/html; charset=utf-8', 'no-cache')
            except OSError:
                self.send_error(500, 'index.html missing')
            return

        name = path.lstrip('/')
        ext = os.path.splitext(name)[1].lower()
        full = os.path.normpath(os.path.join(DIRECTORY, name))
        if ('/' in name or '\\' in name or ext not in STATIC_TYPES
                or not full.startswith(DIRECTORY) or not os.path.isfile(full)):
            self.send_error(404)
            return
        with open(full, 'rb') as f:
            body = f.read()
        self._send(body, STATIC_TYPES[ext], f'public, max-age={STATIC_MAX_AGE}')


class UIServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    # Allow immediate restarts (otherwise the port stays in TIME_WAIT for ~60 s)
    allow_reuse_address = True
    daemon_threads = True


def start_server():
    try:
        with UIServer(("", PORT), UIRequestHandler) as httpd:
            print(f"Server running at http://localhost:{PORT}/ (API {api_url})")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_server()
