from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from src.schemas import DocumentChunk, ParsedPage

class DocumentIngestor:
    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_documents(self, source_docs: list[Path] | Path) -> list[ParsedPage]:
        paths = sorted(source_docs.glob("*")) if isinstance(source_docs, Path) and source_docs.is_dir() else list(source_docs)
        pages: list[ParsedPage] = []
        for path in paths:
            suffix = path.suffix.lower()
            if suffix in {".md", ".txt"}:
                text = self._clean_text(path.read_text(encoding="utf-8", errors="ignore"))
                pages.append(ParsedPage(path.name, 1, text, self.guess_section_title(text), {"source_type": suffix.lstrip(".")}))
            elif suffix == ".docx":
                text = self._clean_text(self._read_docx(path))
                pages.append(ParsedPage(path.name, 1, text, self.guess_section_title(text), {"source_type": "docx"}))
            elif suffix == ".pdf":
                pages.extend(self._read_pdf(path))
        return pages

    def split_documents(self, pages: list[ParsedPage]) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        counters: dict[tuple[str, int], int] = {}
        current_sections: dict[str, str | None] = {}
        for page in pages:
            page_section = page.section_title or current_sections.get(page.doc_name)
            if page.section_title:
                current_sections[page.doc_name] = page.section_title
            for chunk_text in self._split_text(page.text):
                key = (page.doc_name, page.page_no)
                counters[key] = counters.get(key, 0) + 1
                section_title = self.guess_section_title(chunk_text) or page_section
                chunks.append(DocumentChunk(
                    chunk_id=f"{Path(page.doc_name).stem}-p{page.page_no:03d}-{counters[key]:02d}",
                    doc_name=page.doc_name,
                    page_no=page.page_no,
                    text=chunk_text,
                    section_title=section_title,
                    metadata={**page.metadata, "source_type": Path(page.doc_name).suffix.lower().lstrip(".")},
                ))
        return chunks

    def _read_pdf(self, path: Path) -> list[ParsedPage]:
        try:
            from PyPDF2 import PdfReader
        except ImportError as exc:
            raise RuntimeError("读取 PDF 需要 PyPDF2，请先安装依赖。") from exc
        reader = PdfReader(str(path))
        pages: list[ParsedPage] = []
        current_section: str | None = None
        for page_no, page in enumerate(reader.pages, start=1):
            text = self._clean_text(page.extract_text() or "")
            section_title = self.guess_section_title(text)
            if section_title:
                current_section = section_title
            pages.append(ParsedPage(
                doc_name=path.name,
                page_no=page_no,
                text=text,
                section_title=section_title or current_section,
                metadata={"source_type": "pdf"},
            ))
        return pages

    def _read_docx(self, path: Path) -> str:
        """Extract visible paragraph/table text from docx without extra dependencies."""
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        parts = []
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        for paragraph in root.findall(".//w:p", ns):
            texts = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
            line = "".join(texts).strip()
            if line:
                parts.append(line)
        return "\n".join(parts)

    def _split_text(self, text: str) -> list[str]:
        clean = self._clean_text(text)
        if not clean:
            return []
        chunks = []
        start = 0
        while start < len(clean):
            end = start + self.chunk_size
            chunks.append(clean[start:end])
            if end >= len(clean):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    @staticmethod
    def _clean_text(text: str) -> str:
        lines = []
        for line in text.replace("\x00", "").splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                lines.append(clean)
        cleaned = "\n".join(lines)
        return re.sub(r"([\u4e00-\u9fa5])\n([\u4e00-\u9fa5])", r"\1\2", cleaned)

    @staticmethod
    def guess_section_title(text: str) -> str | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title_tokens = [
            "目的",
            "原理",
            "试剂",
            "仪器",
            "步骤",
            "安全",
            "废弃物",
            "注意事项",
            "实验方法",
            "SOP",
            "Protocol",
            "protocol",
        ]
        for line in lines[:6]:
            normalized = line.strip(" ：:.-")
            if len(normalized) <= 100 and any(token.lower() in normalized.lower() for token in title_tokens):
                return normalized
            if re.match(r"^(\d+(\.\d+)*|[一二三四五六七八九十]+)[、.]\s*\S+", normalized) and len(normalized) <= 100:
                return normalized
        return None
