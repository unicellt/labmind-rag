import json
from pathlib import Path
import tempfile
import unittest

from src.local_mineru_parser import LocalMinerUParser


class LocalMinerUParserTests(unittest.TestCase):
    def test_content_list_is_grouped_by_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_list = Path(tmp) / "demo_content_list.json"
            content_list.write_text(json.dumps([
                {"type": "text", "text": "第一章", "text_level": 1, "page_idx": 0},
                {"type": "text", "text": "正文 A", "page_idx": 0},
                {"type": "page_number", "text": "1", "page_idx": 0},
                {"type": "text", "text": "正文 B", "page_idx": 1},
            ], ensure_ascii=False), encoding="utf-8")
            pages = LocalMinerUParser._read_content_list("demo.pdf", content_list)
            self.assertEqual(2, len(pages))
            self.assertEqual(1, pages[0].page_no)
            self.assertEqual("第一章", pages[0].section_title)
            self.assertEqual("mineru", pages[0].metadata["parser"])
            self.assertNotIn("\n1", pages[0].text)


if __name__ == "__main__":
    unittest.main()
