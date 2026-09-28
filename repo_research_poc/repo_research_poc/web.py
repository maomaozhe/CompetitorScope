"""Loopback-only browser entry point for fixed-snapshot source research."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .runner import run_research
from .snapshot import validate_request


STATIC_DIR = Path(__file__).with_name("static")
RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_REQUEST_BYTES = 16 * 1024


class ResearchWebState:
    def __init__(self, output_dir: Path, model_config: dict[str, Any], runner: Callable):
        self.output_dir = output_dir.resolve()
        self.model_config = model_config
        self.runner = runner
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def submit(self, payload: dict[str, Any]) -> str:
        snapshot_value = payload.get("snapshot")
        sha = payload.get("commit_sha")
        question = payload.get("question")
        if not all(isinstance(value, str) for value in (snapshot_value, sha, question)):
            raise ValueError("snapshot, commit_sha and question must be strings")
        snapshot = Path(snapshot_value)
        validate_request(snapshot, sha, question, self.output_dir)
        with self.lock:
            if any(job["status"] == "running" for job in self.jobs.values()):
                raise RuntimeError("another research job is running")
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"job_id": job_id, "status": "running"}
        thread = threading.Thread(
            target=self._run,
            args=(job_id, snapshot, sha, question),
            daemon=True,
        )
        thread.start()
        return job_id

    def _run(self, job_id: str, snapshot: Path, sha: str, question: str) -> None:
        try:
            result = self.runner(snapshot, sha, question, self.output_dir, self.model_config)
            finished = {"job_id": job_id, "status": "complete", "result": result}
        except Exception as error:
            finished = {"job_id": job_id, "status": "error", "error": str(error)}
        with self.lock:
            self.jobs[job_id] = finished

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if RUN_ID.fullmatch(job_id) is None:
            return None
        with self.lock:
            return self.jobs.get(job_id)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        if RUN_ID.fullmatch(run_id) is None:
            return None
        path = self.output_dir / f"{run_id}.json"
        if not path.is_file() or path.is_symlink():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(record, dict) or record.get("run_id") != run_id:
            return None
        return record

    def list_runs(self) -> list[dict[str, Any]]:
        if not self.output_dir.is_dir():
            return []
        runs = []
        for path in self.output_dir.glob("*.json"):
            record = self.get_run(path.stem)
            if record is None:
                continue
            runs.append(
                {
                    "run_id": record["run_id"],
                    "status": record.get("status", "unknown"),
                    "question": record.get("question", ""),
                    "snapshot_path": record.get("snapshot_path", ""),
                    "started_at": record.get("started_at", ""),
                    "duration_ms": record.get("duration_ms"),
                }
            )
        return sorted(runs, key=lambda run: run["started_at"], reverse=True)[:50]


class ResearchServer(ThreadingHTTPServer):
    web_state: ResearchWebState


def create_server(
    host: str,
    port: int,
    output_dir: Path,
    model_config: dict[str, Any],
    *,
    runner: Callable = run_research,
) -> ResearchServer:
    if host != "127.0.0.1":
        raise ValueError("web server must bind to 127.0.0.1")
    state = ResearchWebState(output_dir, model_config, runner)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, name: str, content_type: str) -> None:
            body = (STATIC_DIR / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                return self._static("index.html", "text/html; charset=utf-8")
            if path == "/app.css":
                return self._static("app.css", "text/css; charset=utf-8")
            if path == "/app.js":
                return self._static("app.js", "text/javascript; charset=utf-8")
            if path == "/api/config":
                return self._json(
                    200,
                    {
                        "model": state.model_config.get("model"),
                        "exposed_tools": ["ls", "glob", "grep", "read_file"],
                    },
                )
            if path == "/api/runs":
                return self._json(200, {"runs": state.list_runs()})
            if path.startswith("/api/runs/"):
                record = state.get_run(path.removeprefix("/api/runs/"))
                return (
                    self._json(200, record)
                    if record
                    else self._json(404, {"error": "run not found"})
                )
            if path.startswith("/api/jobs/"):
                job = state.get_job(path.removeprefix("/api/jobs/"))
                return self._json(200, job) if job else self._json(404, {"error": "job not found"})
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/jobs":
                return self._json(404, {"error": "not found"})
            origin = self.headers.get("Origin")
            if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
                return self._json(403, {"error": "cross-origin request denied"})
            if self.headers.get_content_type() != "application/json":
                return self._json(415, {"error": "Content-Type must be application/json"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise ValueError("request body must be between 1 and 16384 bytes")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                job_id = state.submit(payload)
            except (ValueError, json.JSONDecodeError) as error:
                return self._json(400, {"error": str(error)})
            except RuntimeError as error:
                return self._json(409, {"error": str(error)})
            self._json(202, {"job_id": job_id})

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ResearchServer((host, port), Handler)
    server.web_state = state
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local browser UI for repository research")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--output-dir", type=Path, default=Path.home() / ".competitorscope" / "repo-research-runs"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("REPO_RESEARCH_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or "claude-sonnet-4-6",
    )
    parser.add_argument("--base-url", default=os.getenv("ANTHROPIC_BASE_URL"))
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args(argv)
    model_config: dict[str, Any] = {
        "provider": "anthropic",
        "model": args.model,
        "temperature": 0,
        "max_tokens": args.max_tokens,
    }
    if args.base_url:
        model_config["base_url"] = args.base_url
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        parser.error("set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN before starting")
    if not os.getenv("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_AUTH_TOKEN"]
    server = create_server("127.0.0.1", args.port, args.output_dir, model_config)
    print(f"Repo Research Web: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
