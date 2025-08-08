import datetime
import json
import mimetypes
import multiprocessing
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from pymongo import MongoClient

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = BASE_DIR / "templates"
STATIC = BASE_DIR / "static"


# ---------- HTTP ----------
class AppHandler(BaseHTTPRequestHandler):
    def _send_bytes(self, data: bytes, code=200, content_type="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, path: Path, code=200):
        if not path.exists():
            return self._serve_error()
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype is None:
            ctype = "application/octet-stream"
        self._send_bytes(path.read_bytes(), code=code, content_type=ctype)

    def _serve_error(self, code=404):
        self._send_bytes((TEMPLATES / "error.html").read_bytes(), code=code)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._serve_file(TEMPLATES / "index.html")
        if self.path == "/message.html":
            return self._serve_file(TEMPLATES / "message.html")
        if self.path.startswith("/static/"):
            rel = self.path.removeprefix("/static/")
            return self._serve_file(STATIC / rel)
        return self._serve_error()

    def do_POST(self):
        if self.path != "/submit":
            return self._serve_error()

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        ctype = self.headers.get("Content-Type", "")

        if "application/x-www-form-urlencoded" in ctype:
            params = parse_qs(body)
            username = params.get("username", ["Anonymous"])[0]
            message = params.get("message", [""])[0]
        elif "application/json" in ctype:
            data = json.loads(body or "{}")
            username = data.get("username", "Anonymous")
            message = data.get("message", "")
        else:
            username, message = "Anonymous", body

        payload = json.dumps({"username": username, "message": message}).encode("utf-8")

        # Пересилаємо далі на Socket-сервер (TCP :5000)
        try:
            with socket.create_connection(("127.0.0.1", 5000), timeout=3) as s:
                s.sendall(payload)
        except Exception as e:
            print("Forward error:", e)

        # редіректимо на головну
        self.send_response(302)
        self.send_header("Location", "/")
        self.end_headers()


def run_http_server():
    server = HTTPServer(("0.0.0.0", 3000), AppHandler)
    print("HTTP server listening on :3000")
    server.serve_forever()


# ---------- SOCKET (TCP) ----------
def run_socket_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 5000))
    srv.listen(5)
    print("Socket server listening on :5000")

    client = MongoClient("mongodb://mongo:27017/")
    col = client["chat_db"]["messages"]

    while True:
        conn, addr = srv.accept()
        with conn:
            chunks = []
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                chunks.append(data)

        raw = b"".join(chunks).decode("utf-8", errors="ignore")
        try:
            doc = json.loads(raw)
            doc["date"] = datetime.datetime.now().isoformat(sep=" ")
            col.insert_one(doc)
            print("Saved:", doc)
        except Exception as e:
            print("Bad payload:", raw, e)


if __name__ == "__main__":
    p = multiprocessing.Process(target=run_socket_server, daemon=True)
    p.start()
    run_http_server()