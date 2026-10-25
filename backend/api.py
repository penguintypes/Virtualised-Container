import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import json
import os
from pathlib import Path
from . import core, engine

GUI = Path(__file__).resolve().parents[1] / "gui"
class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, value=None):
        body = b"" if value is None else json.dumps(value).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8080"); self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS"); self.end_headers(); self.wfile.write(body)
    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
    def fail(self, error, code="bad_request", status=400): self.send_json(status, {"error": str(error), "code": code})
    def do_OPTIONS(self): self.send_json(204)
    def do_HEAD(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
        else: self.send_response(404); self.end_headers()
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"): return self.send_json(200, None) if False else self.static("index.html", "text/html")
            if path.startswith("/static/"): return self.static(path[8:])
            if path == "/health": return self.send_json(200, {"ok": True, "capabilities": engine.capabilities()})
            if path == "/images": return self.send_json(200, engine.images())
            if path == "/containers": return self.send_json(200, engine.containers())
            parts = path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "containers": return self.send_json(200, engine.inspect(core.valid_name(parts[1])))
            if len(parts) == 3 and parts[0] == "containers" and parts[2] == "stats": return self.send_json(200, engine.stats(core.valid_name(parts[1])))
            if len(parts) == 3 and parts[0] == "containers" and parts[2] == "logs": return self.send_json(200, engine.logs(core.valid_name(parts[1])))
            if len(parts) == 3 and parts[0] == "images" and parts[2] == "download":
                import subprocess
                a = engine.export_image(core.valid_name(parts[1]))
                b = a.read_bytes()
                subprocess.run(["sudo", "-n", "rm", "-rf", str(a.parent)])
                self.send_response(200); self.send_header("Content-Type", "application/x-tar"); self.end_headers(); self.wfile.write(b); return
            return self.fail("not found", "not_found", 404)
        except Exception as error: self.fail(error)
    def static(self, name, content_type=None):
        file = (GUI / name).resolve()
        if not str(file).startswith(str(GUI.resolve())): return self.fail("not found", "not_found", 404)
        body = file.read_bytes(); self.send_response(200); self.send_header("Content-Type", content_type or mimetypes.guess_type(name)[0] or "text/plain"); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        path = urlparse(self.path).path; data = self.body()
        try:
            if path == "/containers":
                name = core.valid_name(data.get("name") or data["image"] + "-" + str(os.getpid()))
                port = data.get("port") or ((data.get("ports") or [None])[0])
                return self.send_json(201, engine.run(name, data["image"], data.get("command"), data.get("memory"), data.get("cpus"), data.get("pids"), port))
            if path == "/images/build": return self.send_json(201, engine.build(data["file"], clean=data.get("clean", False), update=data.get("update", False)))
            if len(path.strip("/").split("/")) == 3 and path.strip("/").split("/")[0] == "images" and path.strip("/").split("/")[2] == "upload":
                import tempfile, os
                n = core.valid_name(path.strip("/").split("/")[1])
                d = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with tempfile.NamedTemporaryFile(delete=False) as f: f.write(d); t = f.name
                r = engine.upload_image(n, t)
                os.unlink(t)
                return self.send_json(201, r)
            parts = path.strip("/").split("/"); name = core.valid_name(parts[1])
            if len(parts) == 2:
                o = engine._load().get(name, {})
                return self.send_json(200, engine.run(name, o.get("image", "alpine"), o.get("command"), port=(o.get("ports") or [None])[0]))
            if parts[2] == "stop": engine.stop(name); return self.send_json(200, engine.inspect(name))
            if parts[2] == "exec": return self.send_json(200, engine.execute(name, data["command"]))
            return self.fail("not found", "not_found", 404)
        except Exception as error: self.fail(error)
    def do_DELETE(self):
        try:
            parts = self.path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "containers": engine.remove(core.valid_name(parts[1])); return self.send_json(204)
            if len(parts) == 2 and parts[0] == "images": engine._call("delete", core.valid_name(parts[1])); return self.send_json(204)
            self.fail("not found", "not_found", 404)
        except Exception as error: self.fail(error)

def main():
    ThreadingHTTPServer((os.getenv("VCONTAINER_HOST", "127.0.0.1"), int(os.getenv("VCONTAINER_PORT", "8080"))), Handler).serve_forever()
if __name__ == "__main__": main()
