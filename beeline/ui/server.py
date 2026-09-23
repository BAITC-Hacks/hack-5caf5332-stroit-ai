"""Loopback-only API and UI. No outgoing network calls, no production campaigns."""
import argparse
import json
import mimetypes
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "engine"
OUTPUT = ROOT / "outputs"
LOCK = threading.Lock()
STATE = {"status": "idle", "message": "Подбор ещё не запускался"}
DATA = None
ARTIFACTS = {}


def command(*args):
    process = subprocess.run([sys.executable, "run_case.py", *args], cwd=ENGINE,
                             capture_output=True, text=True, timeout=300)
    if process.returncode:
        raise RuntimeError((process.stderr or process.stdout)[-1500:])
    return process.stdout


def worker():
    try:
        command("--out", str(OUTPUT))
        result = json.loads((OUTPUT / "run.json").read_text(encoding="utf-8"))
        artifacts = {"run.json": (OUTPUT / "run.json").read_bytes(), "submission.csv": (OUTPUT / "submission.csv").read_bytes()}
        with LOCK:
            ARTIFACTS.update(artifacts)
            STATE.update(status="complete", message="Подбор завершён", run_id=result["run_id"])
    except Exception as exc:
        with LOCK:
            STATE.update(status="error", message="Подбор не завершён. Проверьте локальные данные и зависимости, затем повторите запуск.", detail=str(exc))


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, content_type="application/json; charset=utf-8", download=None):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if isinstance(payload, (dict, list)) else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def allowed_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {"error": "Host not allowed"})
        url = urlsplit(self.path)
        if url.path == "/api/data":
            return self.reply(200, DATA)
        if url.path == "/api/status":
            with LOCK:
                status = dict(STATE)
            return self.reply(200, status)
        if url.path in {"/api/result", "/api/export.csv", "/api/audit.json"}:
            with LOCK:
                status = dict(STATE)
                artifacts = dict(ARTIFACTS)
            if status["status"] != "complete":
                return self.reply(409, {"error": "Завершённый прогон пока недоступен"})
            wanted = parse_qs(url.query).get("run_id", [None])[0]
            if wanted and wanted != status["run_id"]:
                return self.reply(409, {"error": "Результат обновился. Перезагрузите страницу."})
            # Only fixed public artifacts, never arbitrary user-supplied paths.
            name = "submission.csv" if url.path.endswith(".csv") else "run.json"
            body = artifacts[name]
            return self.reply(200, body, "text/csv; charset=utf-8" if name.endswith(".csv") else "application/json; charset=utf-8",
                              name if url.path != "/api/result" else None)
        if url.path == "/api/benchmark":
            path = OUTPUT / "benchmark.json"
            return self.reply(200, json.loads(path.read_text()) if path.exists() else {"runs": []})
        path = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/src/app.js": "src/app.js", "/src/workspace.js": "src/workspace.js"}.get(url.path)
        if not path:
            return self.reply(404, {"error": "Not found"})
        return self.reply(200, (ROOT / path).read_bytes(), mimetypes.guess_type(path)[0] + "; charset=utf-8")

    def do_POST(self):
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if not self.allowed_host() or origin not in allowed:
            return self.reply(403, {"error": "Same-origin browser request required"})
        if self.path != "/api/run":
            return self.reply(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"error": "Invalid content length"})
        if length < 0 or length > 1024:
            return self.reply(413, {"error": "Request too large"})
        self.rfile.read(length)
        with LOCK:
            if STATE["status"] == "running":
                return self.reply(409, {"error": "Подбор уже выполняется"})
            STATE.clear()
            STATE.update(status="running", message="Агент исследует аудиторию и проводит пилоты…")
        threading.Thread(target=worker, daemon=True).start()
        return self.reply(202, {"status": "running"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--engine", default=str(ENGINE), help="папка с agent.py, run_case.py и данными кейса")
    args = parser.parse_args()
    ENGINE = Path(args.engine).resolve()
    DATA = json.loads(command("--describe"))
    if (OUTPUT / "run.json").exists():
        saved = json.loads((OUTPUT / "run.json").read_text(encoding="utf-8"))
        if saved.get("data_hashes") == DATA["data_hashes"] and saved.get("run_id"):
            ARTIFACTS.update({"run.json": (OUTPUT / "run.json").read_bytes(), "submission.csv": (OUTPUT / "submission.csv").read_bytes()})
            STATE.update(status="complete", message="Сохранённый прогон", run_id=saved["run_id"])
    print(f"Beeline agent UI: http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
