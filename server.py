from __future__ import annotations

import cgi
import json
import os
import re
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.config import load_config
from src.pipeline import LabRAGPipeline
from src.utils import read_jsonl

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
PIPELINE = LabRAGPipeline(load_config(ROOT / "config.yaml"))
UPLOAD_LOCK = threading.Lock()
PIPELINE_LOCK = threading.RLock()
UPLOAD_ENABLED = os.getenv("LABMIND_ENABLE_UPLOAD", "true").strip().lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_BYTES = int(os.getenv("LABMIND_MAX_UPLOAD_MB", "50")) * 1024 * 1024
UPLOAD_TASKS: dict[str, dict] = {}
UPLOAD_TASKS_LOCK = threading.Lock()


def sanitize_uploaded_pdf_name(filename: str | None) -> str:
    raw = str(filename or "").strip().replace("\\", "/")
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("请上传有效的 PDF 文件名。")
    name = parts[-1].strip()
    if not name or name in {".", ".."}:
        raise ValueError("请上传有效的 PDF 文件名。")
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    if Path(safe_name).suffix.lower() != ".pdf":
        raise ValueError("仅支持上传 PDF 文件。")
    return safe_name


def unique_upload_path(upload_dir: Path, filename: str) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    candidate = upload_dir / filename
    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while candidate.exists():
        candidate = upload_dir / f"{stem} ({index}){suffix}"
        index += 1
    return candidate


def process_upload_file(filename: str | None, content: bytes, pipeline: LabRAGPipeline) -> tuple[dict, int]:
    try:
        safe_name = sanitize_uploaded_pdf_name(filename)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    if not content:
        return {"error": "上传文件为空。"}, 400
    if len(content) > MAX_UPLOAD_BYTES:
        return {"error": f"PDF 文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB。"}, 413
    upload_dir = pipeline.config.paths.examples_dir or (ROOT / "data" / "examples")
    with UPLOAD_LOCK:
        target = unique_upload_path(upload_dir, safe_name)
        target.write_bytes(content)
        try:
            with PIPELINE_LOCK:
                if hasattr(pipeline, "ingest_document"):
                    chunk_count = pipeline.ingest_document(target)
                else:
                    chunk_count = pipeline.ingest()
        except Exception:
            target.unlink(missing_ok=True)
            raise
    docs = get_docs_payload(pipeline)["docs"]
    return {
        "uploaded_doc": target.name,
        "chunk_count": chunk_count,
        "docs": docs,
        "ingest_report": getattr(pipeline, "last_ingest_report", {}),
    }, 200

def start_upload_task(filename: str, content: bytes, pipeline: LabRAGPipeline) -> str:
    task_id = uuid.uuid4().hex
    with UPLOAD_TASKS_LOCK:
        if len(UPLOAD_TASKS) >= 100:
            finished = [key for key, value in UPLOAD_TASKS.items() if value.get("status") in {"completed", "failed"}]
            for key in finished[:50]:
                UPLOAD_TASKS.pop(key, None)
        UPLOAD_TASKS[task_id] = {"task_id": task_id, "status": "queued"}

    def worker():
        with UPLOAD_TASKS_LOCK:
            UPLOAD_TASKS[task_id]["status"] = "processing"
        try:
            result, status = process_upload_file(filename, content, pipeline)
            with UPLOAD_TASKS_LOCK:
                if status >= 400:
                    UPLOAD_TASKS[task_id] = {
                        "task_id": task_id,
                        "status": "failed",
                        "error": result.get("error", f"HTTP {status}"),
                    }
                else:
                    UPLOAD_TASKS[task_id] = {
                        "task_id": task_id,
                        "status": "completed",
                        "result": result,
                    }
        except Exception as exc:
            with UPLOAD_TASKS_LOCK:
                UPLOAD_TASKS[task_id] = {
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(exc),
                }

    threading.Thread(target=worker, daemon=True, name=f"labmind-upload-{task_id[:8]}").start()
    return task_id


def get_docs_payload(pipeline: LabRAGPipeline) -> dict:
    rows = read_jsonl(pipeline.config.paths.chunks)
    docs = sorted({row["doc_name"] for row in rows}) if rows else sorted(path.name for path in pipeline.config.paths.source_docs)
    return {"docs": docs}

def process_api_request(path: str, payload: dict, pipeline: LabRAGPipeline) -> tuple[dict, int]:
    question = str(payload.get("question", "")).strip()
    if not question:
        return {"error": "question is required"}, 400
    top_k = int(payload.get("top_k", 5))
    doc_name = payload.get("doc_name")
    if doc_name in {"全部文档", "all", "ALL", ""}:
        doc_name = None
    rerank_value = payload.get("rerank", True)
    rerank = rerank_value if isinstance(rerank_value, bool) else str(rerank_value).lower() not in {"0", "false", "no", "off"}
    answer_type = str(payload.get("answer_type", "综合"))
    if path == "/api/search":
        with PIPELINE_LOCK:
            return {"sources": pipeline.search(question, top_k=top_k, doc_name=doc_name, rerank=rerank)}, 200
    if path == "/api/answer":
        with PIPELINE_LOCK:
            return pipeline.answer(question, top_k=top_k, doc_name=doc_name, rerank=rerank, answer_type=answer_type), 200
    return {"error": "not found"}, 404

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/docs":
            return self._json(get_docs_payload(PIPELINE))
        if parsed.path == "/api/upload-status":
            task_id = parse_qs(parsed.query).get("task_id", [""])[-1]
            with UPLOAD_TASKS_LOCK:
                task = dict(UPLOAD_TASKS.get(task_id, {}))
            if not task:
                return self._json({"error": "upload task not found"}, status=404)
            return self._json(task)
        if parsed.path in {"/api/search", "/api/answer"}:
            payload = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            try:
                result, status = process_api_request(parsed.path, payload, PIPELINE)
                return self._json(result, status=status)
            except Exception as exc:
                return self._json({"error": str(exc)}, status=500)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload":
            if not UPLOAD_ENABLED:
                return self._json({"error": "公开部署已关闭文档上传。"}, status=403)
            return self._handle_upload()
        if parsed.path not in {"/api/search", "/api/answer"}:
            self.send_error(404)
            return
        try:
            payload = self._read_json()
            result, status = process_api_request(parsed.path, payload, PIPELINE)
            return self._json(result, status=status)
        except Exception as exc:
            return self._json({"error": str(exc)}, status=500)

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            return self._json({"error": "请使用 multipart/form-data 上传 PDF。"}, status=400)
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length > MAX_UPLOAD_BYTES + (1024 * 1024):
            return self._json(
                {"error": f"PDF 文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB。"},
                status=413,
            )
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            field = form["file"] if "file" in form else None
            if isinstance(field, list):
                field = field[0] if field else None
            if field is None or not getattr(field, "filename", None):
                return self._json({"error": "请在 file 字段上传 PDF 文件。"}, status=400)
            content = field.file.read()
            try:
                sanitize_uploaded_pdf_name(field.filename)
            except ValueError as exc:
                return self._json({"error": str(exc)}, status=400)
            if not content:
                return self._json({"error": "上传文件为空。"}, status=400)
            if len(content) > MAX_UPLOAD_BYTES:
                return self._json(
                    {"error": f"PDF 文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB。"},
                    status=413,
                )
            task_id = start_upload_task(field.filename, content, PIPELINE)
            return self._json({"task_id": task_id, "status": "queued"}, status=202)
        except ValueError as exc:
            return self._json({"error": str(exc)}, status=400)
        except Exception as exc:
            return self._json({"error": str(exc)}, status=500)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8")
        return json.loads(data or "{}")

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    host = os.getenv("LABMIND_HOST", "127.0.0.1")
    port = int(os.getenv("LABMIND_PORT", "8765"))
    print(f"Lab RAG server running at http://{host}:{port}/index.html")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
