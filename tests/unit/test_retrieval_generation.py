import unittest
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.generation import AnswerGenerator, _load_project_env
from src.retrieval import HybridRetriever, KeywordRetriever, SimpleReranker
from src.schemas import DocumentChunk, RetrievedChunk


class RetrievalGenerationTests(unittest.TestCase):
    def test_project_env_overrides_inherited_environment(self):
        with patch("src.generation._python_load_dotenv") as load_dotenv:
            AnswerGenerator("dashscope", "qwen", 0)
        dotenv_path = load_dotenv.call_args.kwargs["dotenv_path"]
        self.assertEqual(".env", dotenv_path.name)
        self.assertTrue(load_dotenv.call_args.kwargs["override"])

    def test_project_env_fallback_loader_overrides_inherited_environment(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DASHSCOPE_API_KEY=new-key\n", encoding="utf-8")
            with patch("src.generation._python_load_dotenv", None), \
                 patch.dict(os.environ, {"DASHSCOPE_API_KEY": "old-key"}):
                _load_project_env(env_path)
                self.assertEqual("new-key", os.environ["DASHSCOPE_API_KEY"])

    def test_keyword_retriever_returns_page_sources(self):
        chunks = [
            DocumentChunk("a-p001-01", "a.pdf", 1, "PCR 退火温度 55 ℃", "PCR"),
            DocumentChunk("b-p001-01", "b.pdf", 1, "蛋白结构预测", "蛋白"),
        ]
        results = KeywordRetriever(chunks).retrieve("PCR 退火温度", top_k=1)
        self.assertEqual(1, len(results))
        self.assertEqual("a.pdf", results[0].doc_name)
        self.assertEqual(1, results[0].page_no)

    def test_doc_name_filter(self):
        chunks = [
            DocumentChunk("a-p001-01", "a.pdf", 1, "PCR 退火温度", "PCR"),
            DocumentChunk("b-p001-01", "b.pdf", 1, "PCR 引物设计", "PCR"),
        ]
        results = KeywordRetriever(chunks).retrieve("PCR", top_k=5, doc_name="b.pdf")
        self.assertEqual(["b.pdf"], [item.doc_name for item in results])

    def test_unrelated_partial_character_match_is_rejected(self):
        chunks = [
            DocumentChunk(f"a-p{index:03d}-01", "a.pdf", index, "样品经过离心处理。", "步骤")
            for index in range(1, 11)
        ]
        results = KeywordRetriever(chunks).retrieve("月球样品如何处理", top_k=5)
        self.assertEqual([], results)

    def test_reranker_boosts_parameter_chunks(self):
        chunks = [
            RetrievedChunk("a-p001-01", "a.pdf", 1, "普通说明", "说明", score=0.2),
            RetrievedChunk("a-p002-01", "a.pdf", 2, "加入10 uL buffer，离心5 min", "步骤", score=0.2),
        ]
        results = SimpleReranker().rerank("buffer 加多少", chunks, top_k=1)
        self.assertEqual("a-p002-01", results[0].chunk_id)

    def test_hybrid_retriever_fuses_keyword_and_vector_results(self):
        chunks = [
            DocumentChunk("keyword", "a.pdf", 1, "CryoSPARC 网页配置", "配置"),
            DocumentChunk("vector", "a.pdf", 2, "默认访问端口为 39000", "安装"),
        ]
        keyword = KeywordRetriever(chunks)

        class FakeVectorIndex:
            def search(self, query, source_chunks, top_k, min_score, doc_name=None):
                return [RetrievedChunk(**source_chunks[1].to_dict(), score=0.9)]

        results = HybridRetriever(keyword, FakeVectorIndex()).retrieve(
            "CryoSPARC 默认网页端口", chunks, top_k=5
        )
        self.assertEqual({"keyword", "vector"}, {item.chunk_id for item in results})

    def test_hybrid_retriever_rejects_weak_vector_only_results(self):
        chunks = [DocumentChunk("vector", "a.pdf", 1, "PCR 样品处理", "PCR")]

        class FakeVectorIndex:
            def search(self, query, source_chunks, top_k, min_score, doc_name=None):
                return [RetrievedChunk(**source_chunks[0].to_dict(), score=0.45)]

        results = HybridRetriever(KeywordRetriever(chunks), FakeVectorIndex()).retrieve(
            "月球岩石如何处理", chunks, top_k=5
        )
        self.assertEqual([], results)

    def test_extractive_answer_contains_sources(self):
        chunks = [
            RetrievedChunk("a-p001-01", "a.pdf", 1, "加入10 uL buffer。", "步骤", score=0.9)
        ]
        answer = AnswerGenerator("local", "local", 0).generate("buffer 加多少？", chunks)
        self.assertIn("抽取式答案", answer)
        self.assertIn("a.pdf", answer)
        self.assertIn("第 1 页", answer)

    def test_no_chunks_returns_conservative_answer(self):
        answer = AnswerGenerator("local", "local", 0).generate("不存在的问题", [])
        self.assertIn("未找到足够依据", answer)

    def test_dashscope_failure_falls_back_to_extractive_answer(self):
        chunks = [
            RetrievedChunk("a-p001-01", "a.pdf", 1, "加入10 uL buffer。", "步骤", score=0.9)
        ]
        generator = AnswerGenerator("dashscope", "qwen", 0)
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": "test"}), \
             patch("importlib.util.find_spec", return_value=object()), \
             patch.object(generator, "_dashscope_chat", side_effect=RuntimeError("offline")):
            answer = generator.generate("buffer 加多少？", chunks)
        self.assertIn("抽取式答案", answer)

    def test_openai_compatible_provider_returns_model_answer(self):
        chunks = [
            RetrievedChunk("a-p001-01", "a.pdf", 1, "加入10 uL buffer。", "步骤", score=0.9)
        ]
        generator = AnswerGenerator(
            "openai_compatible",
            "Qwen/Qwen2.5-7B-Instruct",
            0,
            base_url="https://api.example.test/v1",
            api_key_env="TEST_MODEL_KEY",
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "模型答案：加入 10 uL buffer。"}}]}
                ).encode("utf-8")

        with patch.dict(os.environ, {"TEST_MODEL_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            answer = generator.generate("buffer 加多少？", chunks)
        self.assertEqual("模型答案：加入 10 uL buffer。", answer)
        self.assertEqual("llm", generator.last_mode)
        request = urlopen.call_args.args[0]
        self.assertEqual("https://api.example.test/v1/chat/completions", request.full_url)
        self.assertIn("Bearer test-key", request.headers["Authorization"])

    def test_openai_compatible_failure_falls_back_to_extractive_answer(self):
        chunks = [
            RetrievedChunk("a-p001-01", "a.pdf", 1, "加入10 uL buffer。", "步骤", score=0.9)
        ]
        generator = AnswerGenerator(
            "openai_compatible",
            "free-model",
            0,
            base_url="https://api.example.test/v1",
            api_key_env="TEST_MODEL_KEY",
        )
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "test-key"}), \
             patch("urllib.request.urlopen", side_effect=OSError("offline")):
            answer = generator.generate("buffer 加多少？", chunks)
        self.assertIn("抽取式答案", answer)
        self.assertEqual("extractive", generator.last_mode)
        self.assertIn("OSError", generator.last_error)

    def test_extractive_answer_selects_relevant_sentence(self):
        chunks = [
            RetrievedChunk(
                "a-p001-01",
                "a.pdf",
                1,
                "前置说明很长。其他无关内容。ARTP诱变仪电源功率120W，照射距离1mm。",
                "ARTP",
                score=0.9,
            )
        ]
        answer = AnswerGenerator("local", "local", 0).generate("ARTP诱变仪参数是什么？", chunks)
        self.assertIn("120W", answer)


if __name__ == "__main__":
    unittest.main()
