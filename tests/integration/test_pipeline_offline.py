from pathlib import Path
import json
import tempfile
import unittest

from src.config import AppConfig, ChunkingConfig, LLMConfig, ParserConfig, PathConfig, RetrievalConfig
from src.pipeline import LabRAGPipeline
from server import get_docs_payload, process_api_request, process_upload_file


class PipelineOfflineTests(unittest.TestCase):
    def make_config(self, tmp: Path) -> AppConfig:
        root = Path(__file__).resolve().parents[2]
        return AppConfig(
            paths=PathConfig(
                source_docs=[
                    root / "data" / "examples" / "gao lab protocol.pdf",
                    next((root / "data" / "examples").glob("江涛组相关实验SOP*.pdf")),
                ],
                parsed_docs=tmp / "parsed",
                chunks=tmp / "chunks" / "chunks.jsonl",
                index_store=tmp / "index_store",
            ),
            parser=ParserConfig(preferred="pypdf2"),
            chunking=ChunkingConfig(chunk_size=900, chunk_overlap=150),
            retrieval=RetrievalConfig(top_k=5),
            llm=LLMConfig(provider="local", model="local", temperature=0),
        )

    def test_ingest_search_and_answer_with_real_pdfs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = LabRAGPipeline(self.make_config(Path(tmpdir)))
            count = pipeline.ingest()
            self.assertGreater(count, 10)
            self.assertTrue(pipeline.config.paths.chunks.exists())
            self.assertTrue((pipeline.config.paths.index_store / "index_manifest.json").exists())

            sources = pipeline.search("UniProt 如何查询蛋白基本信息", top_k=5)
            self.assertGreater(len(sources), 0)
            self.assertTrue(all("page_no" in source for source in sources))
            self.assertTrue(any("江涛组相关实验SOP" in source["doc_name"] for source in sources))

            result = pipeline.answer("ARTP诱变仪的参数设置有哪些？", top_k=5)
            self.assertIn("answer", result)
            self.assertIn("sources", result)
            self.assertGreater(len(result["sources"]), 0)

            self.assert_retrieval_smoke_cases(pipeline, Path(__file__).resolve().parents[1] / "eval_cases" / "retrieval_smoke.jsonl")
            self.assert_qa_smoke_cases(pipeline, Path(__file__).resolve().parents[1] / "eval_cases" / "qa_smoke.jsonl")
            self.assert_api_contracts(pipeline)

    def test_upload_pdf_rebuilds_docs_and_search_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            root = Path(__file__).resolve().parents[2]
            pipeline = LabRAGPipeline(AppConfig(
                paths=PathConfig(
                    source_docs=[],
                    parsed_docs=tmp / "parsed",
                    chunks=tmp / "chunks" / "chunks.jsonl",
                    index_store=tmp / "index_store",
                    examples_dir=tmp / "examples",
                ),
                parser=ParserConfig(preferred="pypdf2"),
                chunking=ChunkingConfig(chunk_size=900, chunk_overlap=150),
                retrieval=RetrievalConfig(top_k=5),
                llm=LLMConfig(provider="local", model="local", temperature=0),
            ))
            pdf_bytes = (root / "data" / "examples" / "gao lab protocol.pdf").read_bytes()
            payload, status = process_upload_file("uploaded protocol.pdf", pdf_bytes, pipeline)
            self.assertEqual(200, status)
            self.assertEqual("uploaded protocol.pdf", payload["uploaded_doc"])
            self.assertGreater(payload["chunk_count"], 10)
            self.assertIn("uploaded protocol.pdf", get_docs_payload(pipeline)["docs"])
            results = pipeline.search("ARTP 120W 照射距离", top_k=5, doc_name="uploaded protocol.pdf")
            self.assertGreater(len(results), 0)
            self.assertTrue(any("120W" in result["text"] for result in results))

    def assert_retrieval_smoke_cases(self, pipeline: LabRAGPipeline, path: Path) -> None:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            case = json.loads(raw)
            results = pipeline.search(case["query"], top_k=max(case["max_rank"], 5))
            if case["notes"] == "document_out_of_scope":
                self.assertEqual([], results, case["id"])
                continue
            top = results[:case["max_rank"]]
            matched = any(
                result["doc_name"] == case["expected_doc"]
                and any(term.lower() in result["text"].lower() for term in case["expected_terms"])
                for result in top
            )
            self.assertTrue(matched, case["id"])

    def assert_qa_smoke_cases(self, pipeline: LabRAGPipeline, path: Path) -> None:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            case = json.loads(raw)
            result = pipeline.answer(case["question"], top_k=5)
            answer = result["answer"].lower()
            source_docs = {source["doc_name"] for source in result["sources"]}
            self.assertTrue(any(point.lower() in answer for point in case["expected_points"]), case["id"])
            self.assertTrue(
                not case["expected_sources"] or any(doc in source_docs for doc in case["expected_sources"]),
                case["id"],
            )
            self.assertTrue(all(term.lower() not in answer for term in case["forbidden"]), case["id"])

    def assert_api_contracts(self, pipeline: LabRAGPipeline) -> None:
        docs = get_docs_payload(pipeline)["docs"]
        self.assertEqual(2, len(docs))

        error, status = process_api_request("/api/search", {"question": ""}, pipeline)
        self.assertEqual(400, status)
        self.assertIn("error", error)

        search, status = process_api_request("/api/search", {"question": "ARTP诱变仪参数", "top_k": 3}, pipeline)
        self.assertEqual(200, status)
        self.assertGreater(len(search["sources"]), 0)
        self.assertIn("page_no", search["sources"][0])

        answer, status = process_api_request("/api/answer", {"question": "月球样品如何处理？"}, pipeline)
        self.assertEqual(200, status)
        self.assertIn("未找到足够依据", answer["answer"])


if __name__ == "__main__":
    unittest.main()
