#!/usr/bin/env python3
"""
Simple HTTP server to serve the valve control UI.
This is for development/testing purposes only.
"""
import http.server
import socketserver
import os
import sys
import json

PORT = 8000
DIRECTORY = "ui"

# Ensure the UI directory exists
if not os.path.exists(DIRECTORY):
    print(f"Error: UI directory '{DIRECTORY}' not found")
    sys.exit(1)

# Try to load configuration from root config.json
config = {}
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except Exception as e:
    print(f"Warning: Could not load config.json: {e}")

# Default API URL
api_url = config.get('api_url', 'http://localhost:5000/api')

class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_GET(self):
        # If it's the index.html, inject the API URL
        if self.path == '/' or self.path == '/index.html':
            # Read the index.html file
            filepath = os.path.join(DIRECTORY, 'index.html')
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content = f.read()
              

                api_injection_script = f"""
                <script>
                    if (typeof API_BASE_URL === 'undefined') {{
                        var API_BASE_URL = '{api_url}';
                    }}
                </script>
                """
                # Inject the script before the first script tag
                content = content.replace('<script src="script.js"></script>', f'{api_injection_script}<script src="script.js"></script>')
              
                # Send response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(content.encode())
                return
        # For all other requests, serve normally
        super().do_GET()

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