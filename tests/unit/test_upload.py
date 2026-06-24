from pathlib import Path
import tempfile
import unittest

from src.config import AppConfig, ChunkingConfig, LLMConfig, ParserConfig, PathConfig, RetrievalConfig
from src.schemas import DocumentChunk
from src.utils import write_jsonl
from server import process_upload_file, sanitize_uploaded_pdf_name, unique_upload_path


class UploadTests(unittest.TestCase):
    def test_sanitize_uploaded_pdf_name(self):
        self.assertEqual("demo.pdf", sanitize_uploaded_pdf_name(r"C:\fakepath\demo.pdf"))
        self.assertEqual("demo.pdf", sanitize_uploaded_pdf_name("/tmp/demo.pdf"))
        with self.assertRaises(ValueError):
            sanitize_uploaded_pdf_name("../../demo.pdf")
        with self.assertRaises(ValueError):
            sanitize_uploaded_pdf_name("demo.txt")
        with self.assertRaises(ValueError):
            sanitize_uploaded_pdf_name("")

    def test_unique_upload_path_auto_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "protocol.pdf").write_bytes(b"old")
            (root / "protocol (1).pdf").write_bytes(b"old")
            self.assertEqual(root / "protocol (2).pdf", unique_upload_path(root, "protocol.pdf"))

    def test_upload_rejects_non_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = FakePipeline(Path(tmp))
            result, status = process_upload_file("notes.txt", b"text", pipeline)
            self.assertEqual(400, status)
            self.assertIn("error", result)

    def test_upload_saves_and_rebuilds_with_auto_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = FakePipeline(root)
            (pipeline.config.paths.examples_dir / "protocol.pdf").write_bytes(b"old")
            result, status = process_upload_file("protocol.pdf", b"%PDF-1.4", pipeline)
            self.assertEqual(200, status)
            self.assertEqual("protocol (1).pdf", result["uploaded_doc"])
            self.assertEqual(2, result["chunk_count"])
            self.assertTrue((pipeline.config.paths.examples_dir / "protocol (1).pdf").exists())
            self.assertIn("protocol (1).pdf", result["docs"])
            self.assertIn("ingest_report", result)


class FakePipeline:
    def __init__(self, root: Path):
        examples_dir = root / "examples"
        examples_dir.mkdir()
        self.config = AppConfig(
            paths=PathConfig(
                source_docs=[],
                parsed_docs=root / "parsed",
                chunks=root / "chunks" / "chunks.jsonl",
                index_store=root / "index_store",
                examples_dir=examples_dir,
            ),
            parser=ParserConfig(preferred="pypdf2"),
            chunking=ChunkingConfig(chunk_size=100, chunk_overlap=10),
            retrieval=RetrievalConfig(top_k=5),
            llm=LLMConfig(provider="local", model="local", temperature=0),
        )

    def ingest(self) -> int:
        docs = sorted(path.name for path in self.config.paths.examples_dir.glob("*.pdf"))
        chunks = [
            DocumentChunk(f"{Path(doc).stem}-p001-01", doc, 1, "uploaded pdf text", "uploaded").to_dict()
            for doc in docs
        ]
        return write_jsonl(self.config.paths.chunks, chunks)


if __name__ == "__main__":
    unittest.main()
