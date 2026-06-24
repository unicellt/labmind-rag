from __future__ import annotations

import cgi
import json
import os
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from src.config import load_config
from src.pipeline import LabRAGPipeline
from src.utils import read_jsonl

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
PIPELINE = LabRAGPipeline(load_config(ROOT / "config.yaml"))
UPLOAD_LOCK = threading.Lock()
UPLOAD_ENABLED = os.getenv("LABMIND_ENABLE_UPLOAD", "true").strip().lower() in {"1", "true", "yes", "on"}


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
    upload_dir = pipeline.config.paths.examples_dir or (ROOT / "data" / "examples")
    with UPLOAD_LOCK:
        target = unique_upload_path(upload_dir, safe_name)
        target.write_bytes(content)
        try:
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
    rerank = bool(payload.get("rerank", True))
    answer_type = str(payload.get("answer_type", "综合"))
    if path == "/api/search":
        return {"sources": pipeline.search(question, top_k=top_k, doc_name=doc_name, rerank=rerank)}, 200
    if path == "/api/answer":
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
            result, status = process_upload_file(field.filename, field.file.read(), PIPELINE)
            return self._json(result, status=status)
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
