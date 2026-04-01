#!/usr/bin/env python3
"""
Simple HTTP server to serve the valve control UI.
This is for development/testing purposes only.
"""
import http.server
import socketserver
import os
import sys

PORT = 8000
DIRECTORY = "ui"

# Ensure the UI directory exists
if not os.path.exists(DIRECTORY):
    print(f"Error: UI directory '{DIRECTORY}' not found")
    sys.exit(1)

class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def start_server():
    try:
        with socketserver.TCPServer(("", PORT), MyHttpRequestHandler) as httpd:
            print(f"Server running at http://localhost:{PORT}/")
            print(f"Serving files from '{DIRECTORY}' directory")
            print("Press Ctrl+C to stop the server")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_server()