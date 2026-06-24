import unittest
from pathlib import Path


class SiteContractTests(unittest.TestCase):
    def test_launcher_html_points_to_local_app(self):
        launcher = Path(__file__).resolve().parents[2] / "打开实验室知识库.html"
        html = launcher.read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8765/index.html", html)
        self.assertIn("python server.py", html)
        self.assertIn("启动并打开实验室知识库.bat", html)

    def test_windows_launcher_starts_server_and_browser(self):
        launcher = Path(__file__).resolve().parents[2] / "启动并打开实验室知识库.bat"
        script = launcher.read_text(encoding="utf-8")
        self.assertIn("python server.py", script)
        self.assertIn("http://127.0.0.1:8765/index.html", script)

    def test_knowledge_base_build_spec_is_indexed(self):
        root = Path(__file__).resolve().parents[2]
        spec = (root / "spec" / "knowledge-base-build-spec.md").read_text(encoding="utf-8")
        index = (root / "spec" / "README.md").read_text(encoding="utf-8")
        self.assertIn("实验室 SOP 知识库构建 Spec", spec)
        self.assertIn("Qwen/Qwen3-8B", spec)
        self.assertIn("knowledge-base-build-spec.md", index)

    def test_search_results_are_ranked_and_limited_to_top_five(self):
        html = (Path(__file__).resolve().parents[2] / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function topFiveByScore(sources)", html)
        self.assertIn(".sort((left, right) => Number(right.score || 0) - Number(left.score || 0))", html)
        self.assertIn(".slice(0, 5)", html)
        self.assertIn("if (!withAnswer) payload.top_k = 5;", html)
        self.assertIn("相关性 ${Number(chunk.score || 0).toFixed(3)}", html)

    def test_visible_copy_has_no_corrupted_question_mark_placeholders(self):
        html = (Path(__file__).resolve().parents[2] / "site" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("???", html)
        self.assertIn("全部文档", html)
        self.assertIn("知识库回答", html)
        self.assertIn("查询失败", html)
        self.assertIn("filter(doc => !/\\?{2,}/.test(String(doc)))", html)

    def test_upload_ui_calls_upload_api(self):
        html = (Path(__file__).resolve().parents[2] / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="uploadInput"', html)
        self.assertIn('id="uploadBtn"', html)
        self.assertIn('id="uploadStatus"', html)
        self.assertIn("上传并整合", html)
        self.assertIn("/api/upload", html)
        self.assertIn("MinerU 解析成功", html)
        self.assertIn("data.ingest_report", html)
        self.assertIn('formData.append("file", file)', html)


if __name__ == "__main__":
    unittest.main()
