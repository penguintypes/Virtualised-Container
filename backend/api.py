import json
import os
import mimetypes
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core, engine

# resolve gui folder once, remember it's 2 levels up
GUI_DIR = Path(__file__).resolve().parents[1] / "gui"

class VcApiHandler(BaseHTTPRequestHandler):

    def respond_with_json(self, status_code, payload=None):
        resp_body = b"" if payload is None else json.dumps(payload).encode()
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "http://localhost:8080")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
            self.end_headers()
            self.wfile.write(resp_body)
        except (BrokenPipeError, ConnectionResetError):
            # finally fixed the stupid broken pipe crash here
            pass

    def fail_out(self, err, err_code="bad_request", code=400):
        if isinstance(err, (BrokenPipeError, ConnectionResetError)):
            return
        self.respond_with_json(code, {"error": str(err), "code": err_code})

    def do_OPTIONS(self):
        self.respond_with_json(204)

    def do_DELETE(self):
        try:
            url_chunks = self.path.strip("/").split("/")
            # container deletion
            if len(url_chunks) == 2 and url_chunks[0] == "volumes":
                engine.run_volume("remove", core.valid_name(url_chunks[1]))
                return self.respond_with_json(204)

            if len(url_chunks) == 2 and url_chunks[0] == "volumes":
                engine.run_volume("remove", core.valid_name(url_chunks[1]))
                return self.respond_with_json(204)

            if len(url_chunks) == 2 and url_chunks[0] == "containers":
                engine.remove(core.valid_name(url_chunks[1]))
                return self.respond_with_json(204)

            # image deletion
            if len(url_chunks) == 2 and url_chunks[0] == "images":
                engine._call("delete", core.valid_name(url_chunks[1]))
                return self.respond_with_json(204)

            self.fail_out("not found", "not_found", 404)
        except FileNotFoundError as e:
            self.fail_out(e, "not_found", 404)
        except Exception as e:
            self.fail_out(e)

    def do_POST(self):
        parsed_path = self.path.split('?')[0]

        content_length = 0 if parsed_path.endswith("/upload") else int(self.headers.get('Content-Length', 0))
        try:
            raw_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
            req_data = json.loads(raw_data) if raw_data.strip() else {}
        except Exception:
            req_data = {}

        if parsed_path == "/volumes":
            try:
                vol_name = req_data.get("name") if isinstance(req_data, dict) else None
                if not vol_name:
                    return self.fail_out("volume name required", "bad_request", 400)
                res = engine.run_volume("create", vol_name)
                return self.respond_with_json(201, res)
            except Exception as e:
                return self.fail_out(e)
        parsed = urlparse(self.path)


        try:
            if parsed.path == "/containers":
                # hacky fallback for name using pid
                c_name = core.valid_name(req_data.get("name") or req_data["image"] + "-" + str(os.getpid()))

                # getting port from old array or new string
                c_port = req_data.get("port")
                if not c_port and req_data.get("ports"):
                    c_port = req_data["ports"][0]
                if isinstance(c_port, dict):
                    c_port = "%s:%s" % (c_port["host_port"], c_port["container_port"])

                res = engine.run(
                    c_name, req_data["image"], req_data.get("command"),
                    req_data.get("memory"), req_data.get("cpus"), req_data.get("pids"), c_port,
                    req_data.get("volumes"), req_data.get("environment"), req_data.get("network"), req_data.get("ip")
                )
                return self.respond_with_json(201, res)

            if parsed.path == "/images/build":
                return self.respond_with_json(201, engine.build(req_data["file"], clean=req_data.get("clean", False), update=req_data.get("update", False)))

            if parsed.path == "/images/pull":
                if "name" not in req_data:
                    return self.fail_out("image name required")
                res = engine._call("pull", core.valid_name(req_data["name"]), req_data.get("reference", ""), timeout=300)
                return self.respond_with_json(200, {"message": "pulled", "output": res})

            if parsed.path == "/images/pull":
                if "name" not in req_data:
                    return self.fail_out("image name required")
                res = engine._call("pull", core.valid_name(req_data["name"]), req_data.get("reference", ""), timeout=300)
                return self.respond_with_json(200, {"message": "pulled", "output": res})

            url_chunks = parsed.path.strip("/").split("/")

            # upload handling
            if len(url_chunks) == 3 and url_chunks[0] == "images" and url_chunks[2] == "upload":
                img_name = core.valid_name(url_chunks[1])

                # kinda ugly but it writes the tar to a temp file then loads it
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_file.write(raw_data)
                    tmp_path = tmp_file.name

                upload_res = engine.upload_image(img_name, tmp_path)
                os.unlink(tmp_path)
                return self.respond_with_json(201, upload_res)

            target_name = core.valid_name(url_chunks[1])

            if url_chunks[0] == "containers" and (len(url_chunks) == 2 or url_chunks[2] == "start"):
                # just load and run, preserving original resource limits
                obj = engine._load().get(target_name, {})
                old_port = (obj.get("ports") or [None])[0]
                return self.respond_with_json(200, engine.run(
                    target_name,
                    obj.get("image", "alpine"),
                    obj.get("command"),
                    memory=obj.get("memory"),
                    cpus=obj.get("cpus"),
                    pids=obj.get("pids"),
                    port=old_port,
                    volumes=obj.get("volumes"),
                    env=obj.get("env"),
                    network=obj.get("network"),
                    ip=obj.get("ip")
                ))

            if url_chunks[2] == "stop":
                engine.stop(target_name)
                return self.respond_with_json(200, engine.inspect(target_name))

            if url_chunks[2] == "exec":
                return self.respond_with_json(200, engine.execute(target_name, req_data["command"]))

            return self.fail_out("not found", "not_found", 404)
        except Exception as e:
            self.fail_out(e)

    def do_GET(self):
        parsed_path = urlparse(self.path).path
        try:
            if parsed_path in ("/", "/index.html"):
                # quick shortcut for dashboard
                return self.serve_gui("index.html", "text/html")

            if parsed_path in ("/7.css", "/style.css", "/app.js") or parsed_path.endswith((".css", ".js")):
                return self.serve_gui(parsed_path.lstrip("/"))

            if parsed_path.startswith("/static/"):
                return self.serve_gui(parsed_path[8:])

            if parsed_path == "/health":
                return self.respond_with_json(200, {"ok": True, "capabilities": engine.capabilities()})

            if parsed_path == "/system/disk":
                return self.respond_with_json(200, engine.get_disk_usage())

            if parsed_path == "/volumes":
                return self.respond_with_json(200, {"volumes": engine.run_volume("list")})

            if parsed_path.startswith("/volumes/") and len(parsed_path.strip("/").split("/")) == 2:
                v_name = parsed_path.strip("/").split("/")[1]
                return self.respond_with_json(200, engine.run_volume("inspect", v_name))

            if parsed_path == "/system/disk":
                return self.respond_with_json(200, engine.get_disk_usage())

            if parsed_path == "/volumes":
                return self.respond_with_json(200, {"volumes": engine.run_volume("list")})

            if parsed_path.startswith("/volumes/") and len(parsed_path.strip("/").split("/")) == 2:
                v_name = parsed_path.strip("/").split("/")[1]
                return self.respond_with_json(200, engine.run_volume("inspect", v_name))

            if parsed_path == "/system/live":
                from . import live
                return self.respond_with_json(200, live.snapshot())
            m_chunks = parsed_path.strip("/").split("/")
            if len(m_chunks) == 3 and m_chunks[0] == "containers" and m_chunks[2] == "logs":
                return self.respond_with_json(200, {"output": engine.logs(core.valid_name(m_chunks[1]))["logs"]})
            if len(m_chunks) == 3 and m_chunks[0] == "containers" and m_chunks[2] == "processes":
                from pathlib import Path as _P
                cname = core.valid_name(m_chunks[1])
                try:
                    pids = _P(f"/sys/fs/cgroup/vcontainer/{cname}/cgroup.procs").read_text().split()
                except OSError:
                    pids = []
                procs = []
                for pid in pids:
                    try:
                        cmd = _P(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
                    except OSError:
                        cmd = ""
                    procs.append({"pid": int(pid), "command": cmd})
                return self.respond_with_json(200, {"processes": procs})
            if len(m_chunks) == 3 and m_chunks[0] == "containers" and m_chunks[2] == "metrics":
                d = engine.inspect(core.valid_name(m_chunks[1]))
                n = engine._number
                return self.respond_with_json(200, {
                    "memory_used_bytes": n(d.get("memory_current")) or 0,
                    "memory_limit_bytes": n(d.get("memory_max")) or 0,
                    "process_count": n(d.get("pids_current")) or 0,
                    "process_limit": n(d.get("pids_max")) or 0,
                    "cpu_percent": d.get("cpu_pct", 0.0),
                    "network_rx_bytes": 0,
                    "network_tx_bytes": 0,
                })

            if parsed_path == "/system":
                return self.respond_with_json(200, engine.host_stats())

            if parsed_path == "/images":
                return self.respond_with_json(200, engine.images())

            if parsed_path == "/volumes":
                vol_name = req_data.get("name")
                if not vol_name:
                    return self.fail_out("volume name required")
                return self.respond_with_json(201, engine.run_volume("create", vol_name))

            if parsed_path == "/volumes":
                # Ensure req_data is parsed safely
                vol_name = req_data.get("name") if isinstance(req_data, dict) else None
                if not vol_name:
                    return self.fail_out("volume name required")
                return self.respond_with_json(201, engine.run_volume("create", vol_name))

            if parsed_path == "/containers":
                return self.respond_with_json(200, engine.containers())

            url_chunks = parsed_path.strip("/").split("/")

            if len(url_chunks) == 2 and url_chunks[0] == "volumes":
                engine.run_volume("remove", core.valid_name(url_chunks[1]))
                return self.respond_with_json(204)

            if len(url_chunks) == 2 and url_chunks[0] == "containers":
                return self.respond_with_json(200, engine.inspect(core.valid_name(url_chunks[1])))

            if len(url_chunks) == 2 and url_chunks[0] == "containers":
                return self.respond_with_json(200, engine.stats(core.valid_name(url_chunks[1])))

            if len(url_chunks) == 2 and url_chunks[0] == "containers":
                return self.respond_with_json(200, engine.logs(core.valid_name(url_chunks[1])))

            if len(url_chunks) == 3 and url_chunks[0] == "images" and url_chunks[2] == "download":
                img_tar = engine.export_image(core.valid_name(url_chunks[1]))
                tar_bytes = img_tar.read_bytes()
                subprocess.run(["sudo", "-n", "/usr/local/libexec/vcontainer/build_helper.sh", "rm", "-rf", str(img_tar.parent)])
                self.send_response(200)
                self.send_header("Content-Type", "application/x-tar")
                self.end_headers()
                self.wfile.write(tar_bytes)
                return

            return self.fail_out("not found", "not_found", 404)
        except Exception as e:
            self.fail_out(e)

    def serve_gui(self, filename, mime_type=None):
        # safely serve gui files
        target_file = (GUI_DIR / filename).resolve()
        if not str(target_file).startswith(str(GUI_DIR.resolve())):
            return self.fail_out("not found", "not_found", 404)

        body = target_file.read_bytes()
        self.send_response(200)

        resolved_mime = mime_type or mimetypes.guess_type(filename)[0] or "text/plain"
        self.send_header("Content-Type", resolved_mime)
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def main():
    bind_host = os.getenv("VCONTAINER_HOST", "127.0.0.1")
    bind_port = int(os.getenv("VCONTAINER_PORT", "8080"))
    # finally start the server
    ThreadingHTTPServer((bind_host, bind_port), VcApiHandler).serve_forever()

if __name__ == "__main__":
    main()
