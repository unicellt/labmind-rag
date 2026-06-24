from pathlib import Path
import tempfile
import unittest

from src.config import load_config
from src.ingestion import DocumentIngestor
from src.schemas import ParsedPage


class ConfigAndIngestionTests(unittest.TestCase):
    def test_default_config_uses_two_pdf_sources(self):
        cfg = load_config("config.yaml")
        self.assertGreaterEqual(len(cfg.paths.source_docs), 2)
        self.assertTrue(any(path.suffix.lower() == ".pdf" for path in cfg.paths.source_docs))
        self.assertTrue(any(path.suffix.lower() == ".md" for path in cfg.paths.source_docs))
        self.assertTrue(any("gao lab protocol.pdf" == path.name for path in cfg.paths.source_docs))
        self.assertTrue(any("江涛组相关实验SOP" in path.name for path in cfg.paths.source_docs))
        self.assertTrue(any("ai_bio_company_china_xtalpi.md" == path.name for path in cfg.paths.source_docs))

    def test_config_paths_resolve_relative_to_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.yaml"
            config.write_text(
                """
paths:
  source_docs:
    - data/examples/a.pdf
    - data/examples/b.pdf
  parsed_docs: data/parsed
  chunks: data/chunks/chunks.jsonl
  index_store: data/index_store
chunking:
  chunk_size: 100
  chunk_overlap: 10
retrieval:
  top_k: 3
llm:
  provider: local
  model: local
  temperature: 0
""".strip(),
                encoding="utf-8",
            )
            cfg = load_config(config)
            self.assertEqual(root / "data" / "chunks" / "chunks.jsonl", cfg.paths.chunks)
            self.assertEqual(root / "data" / "examples" / "a.pdf", cfg.paths.source_docs[0])
            self.assertEqual(root / ".mineru-venv" / "bin" / "mineru", cfg.parser.local_mineru_executable)
            self.assertFalse(cfg.parser.local_mineru_fallback)

    def test_config_discovers_extra_uploaded_pdfs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            examples = root / "data" / "examples"
            examples.mkdir(parents=True)
            (examples / "a.pdf").write_text("pdf", encoding="utf-8")
            (examples / "extra.pdf").write_text("pdf", encoding="utf-8")
            (examples / "skip.docx").write_text("docx", encoding="utf-8")
            (examples / "skip.md").write_text("md", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                """
paths:
  source_docs:
    - data/examples/a.pdf
  parsed_docs: data/parsed
  chunks: data/chunks/chunks.jsonl
  index_store: data/index_store
  examples_dir: data/examples
chunking:
  chunk_size: 100
  chunk_overlap: 10
retrieval:
  top_k: 3
llm:
  provider: local
  model: local
  temperature: 0
""".strip(),
                encoding="utf-8",
            )
            cfg = load_config(config)
            self.assertEqual(["a.pdf", "extra.pdf"], [path.name for path in cfg.paths.source_docs])

    def test_section_title_detection(self):
        title = DocumentIngestor.guess_section_title("1.2 蛋白质相关预测\n后续内容")
        self.assertEqual("1.2 蛋白质相关预测", title)

    def test_clean_text_repairs_wrapped_chinese_word(self):
        self.assertEqual("加入酶解液。", DocumentIngestor._clean_text("加入酶\n解液。"))

    def test_split_pages_preserves_page_no(self):
        ingestor = DocumentIngestor(chunk_size=12, chunk_overlap=2)
        pages = [ParsedPage("demo.pdf", 3, "步骤一：加入试剂并混匀。步骤二：离心。", "步骤")]
        chunks = ingestor.split_documents(pages)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(chunk.page_no == 3 for chunk in chunks))
        self.assertTrue(all(chunk.doc_name == "demo.pdf" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
