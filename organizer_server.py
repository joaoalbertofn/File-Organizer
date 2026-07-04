import http.server
import socketserver
import json
import os
import sys
import queue
import threading
import subprocess
import urllib.parse
from organizer.processor import FileOrganizer

PORT = 8080
event_queue = queue.Queue()

class SSEStdout:
    def __init__(self, original):
        self.original = original
        
    def write(self, text):
        self.original.write(text)
        self.original.flush()
        
        # Parse progress bar updates:
        if "\rProgresso:" in text:
            import re
            match = re.search(r"(\d+)/(\d+) \((\d+\.\d+)%\)", text)
            if match:
                curr, tot, pct = match.groups()
                event_queue.put({
                    "type": "progress",
                    "current": int(curr),
                    "total": int(tot),
                    "percent": float(pct)
                })
        elif text.strip():
            # Send normal printed logs
            # Filter out standard progress bar text from normal logs
            if not text.startswith("\rProgresso:") and not text.startswith("Progresso:"):
                event_queue.put({
                    "type": "log",
                    "message": text.strip()
                })
            
    def flush(self):
        self.original.flush()


def select_folder_macos():
    """Opens a native macOS folder selector dialog via AppleScript."""
    cmd = """osascript -e 'POSIX path of (choose folder with prompt "Selecione a Pasta")'"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"Error opening folder picker: {e}")
    return ""


def run_organizer_thread(payload):
    """Orchestrates the FileOrganizer execution in a separate thread."""
    # Redirect stdout to capture logs and progress
    original_stdout = sys.stdout
    sys.stdout = SSEStdout(original_stdout)
    
    try:
        organizer = FileOrganizer(
            src=payload["src"],
            dest=payload["dest"],
            folder_format=payload["folder_format"],
            file_format=payload["file_format"],
            action=payload["action"],
            ai_rename=payload["ai_rename"],
            dry_run=payload["dry_run"],
            limit=payload.get("limit")
        )
        organizer.run()
        event_queue.put({"type": "done"})
    except Exception as e:
        event_queue.put({"type": "error", "message": str(e)})
    finally:
        sys.stdout = original_stdout


class OrganizerHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            # Serve the index.html
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            try:
                with open('index.html', 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            except Exception as e:
                self.wfile.write(f"Error loading index.html: {e}".encode('utf-8'))
                
        elif self.path == '/api/events':
            # Serve SSE Stream
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            # Clear any stale events
            while not event_queue.empty():
                try:
                    event_queue.get_nowait()
                except queue.Empty:
                    break
            
            while True:
                try:
                    event = event_queue.get(timeout=1.5)
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode('utf-8'))
                    self.wfile.flush()
                    if event.get("type") in ("done", "error"):
                        break
                except queue.Empty:
                    # Keepalive comment
                    try:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                    except Exception:
                        break  # Client disconnected
                except Exception:
                    break
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        if self.path == '/api/select-folder':
            path = select_folder_macos()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"path": path}).encode('utf-8'))
            
        elif self.path == '/api/run':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode('utf-8'))
            
            # Validate folders exist
            if not os.path.exists(payload["src"]):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Pasta de origem não existe."}).encode('utf-8'))
                return

            # Start organization thread
            thread = threading.Thread(target=run_organizer_thread, args=(payload,))
            thread.daemon = True
            thread.start()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode('utf-8'))
        else:
            self.send_error(404, "Not found")

    # Suppress default server logs in terminal to keep it clean, unless verbose is needed
    def log_message(self, format, *args):
        pass


def main():
    # Change directory to the app root to ensure index.html can be found
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    server = socketserver.TCPServer(("", PORT), OrganizerHTTPHandler)
    # Allow port reuse instantly
    server.allow_reuse_address = True
    
    print(f"\n=========================================")
    print(f" Servidor da Interface Gráfica Iniciado!")
    print(f" Acesse: http://localhost:{PORT}")
    print(f" Pressione Ctrl+C para encerrar o servidor.")
    print(f"=========================================\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
        server.server_close()

if __name__ == "__main__":
    main()
