"""
3D Home Tour — Local Server
Double-click start.bat or run: python server.py
Streams large GLB files from disk via HTTP (no memory duplication).
"""

import http.server
import socketserver
import os
import sys
import json
import webbrowser
import threading
import mimetypes
from urllib.parse import urlparse
from functools import partial

PORT = 8080
glb_file_path = None
server_dir = os.path.dirname(os.path.abspath(__file__))


class TourHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler with range-request support for large GLB streaming."""

    def log_message(self, format, *args):
        msg = format % args
        # Color-code for readability
        if '200' in msg or '206' in msg:
            print(f"  [OK] {msg}")
        elif '404' in msg:
            print(f"  [!!] {msg}")
        else:
            print(f"  [..] {msg}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            self._serve_file(os.path.join(server_dir, 'viewer.html'), 'text/html')

        elif path == '/api/pick-file':
            self._handle_pick_file()

        elif path == '/api/file-info':
            self._handle_file_info()

        elif path == '/model.glb':
            self._stream_glb()

        else:
            # Serve static files from server directory
            safe_path = os.path.normpath(os.path.join(server_dir, path.lstrip('/')))
            if safe_path.startswith(server_dir) and os.path.isfile(safe_path):
                mime = mimetypes.guess_type(safe_path)[0] or 'application/octet-stream'
                self._serve_file(safe_path, mime)
            else:
                self.send_error(404)

    def _serve_file(self, filepath, content_type):
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(data))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404, f'File not found: {filepath}')

    def _handle_pick_file(self):
        """Open native file picker dialog."""
        global glb_file_path
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            # Focus the dialog
            root.focus_force()
            path = filedialog.askopenfilename(
                title='Select GLB/GLTF File',
                filetypes=[
                    ('3D Models', '*.glb *.gltf'),
                    ('GLB files', '*.glb'),
                    ('GLTF files', '*.gltf'),
                    ('All files', '*.*')
                ]
            )
            root.destroy()
        except Exception as e:
            print(f"  [!!] File picker error: {e}")
            path = None

        if path and os.path.exists(path):
            glb_file_path = path
            size = os.path.getsize(path)
            name = os.path.basename(path)
            print(f"\n  >> File selected: {name} ({size / (1024*1024):.0f} MB)")
            result = json.dumps({'name': name, 'size': size, 'ok': True})
        else:
            result = json.dumps({'name': None, 'size': 0, 'ok': False})

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(result.encode())

    def _handle_file_info(self):
        """Return current file info."""
        if glb_file_path and os.path.exists(glb_file_path):
            size = os.path.getsize(glb_file_path)
            name = os.path.basename(glb_file_path)
            result = json.dumps({'name': name, 'size': size, 'ok': True})
        else:
            result = json.dumps({'name': None, 'size': 0, 'ok': False})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(result.encode())

    def _stream_glb(self):
        """Stream GLB from disk with HTTP range-request support (crucial for 1GB+ files)."""
        global glb_file_path
        if not glb_file_path or not os.path.exists(glb_file_path):
            self.send_error(404, 'No GLB file selected')
            return

        file_size = os.path.getsize(glb_file_path)
        range_header = self.headers.get('Range')

        try:
            if range_header:
                # Parse range: "bytes=START-END"
                range_val = range_header.replace('bytes=', '').strip()
                parts = range_val.split('-')
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Content-Length', length)
                self.send_header('Content-Type', 'model/gltf-binary')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()

                with open(glb_file_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))  # 64KB chunks
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            else:
                # Full file — stream in chunks (don't load 1GB into memory)
                self.send_response(200)
                self.send_header('Content-Type', 'model/gltf-binary')
                self.send_header('Content-Length', file_size)
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()

                with open(glb_file_path, 'rb') as f:
                    while True:
                        chunk = f.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        self.wfile.write(chunk)

        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected, that's fine


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def find_free_port(start=8080):
    import socket
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start


def main():
    global glb_file_path

    # Check if a GLB path was passed as argument
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.isfile(arg) and arg.lower().endswith(('.glb', '.gltf')):
            glb_file_path = os.path.abspath(arg)
            print(f"  >> Pre-loaded file: {os.path.basename(glb_file_path)}")

    port = find_free_port(PORT)
    url = f'http://127.0.0.1:{port}'

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║        3D HOME TOUR  — Server        ║")
    print("  ╠══════════════════════════════════════╣")
    print(f"  ║  Open: {url:<29s}║")
    print("  ║  Press Ctrl+C to stop                ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    handler = TourHandler
    httpd = ReusableTCPServer(('127.0.0.1', port), handler)

    # Open browser after short delay
    def open_browser():
        webbrowser.open(url)
    threading.Timer(0.5, open_browser).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        httpd.server_close()


if __name__ == '__main__':
    main()
