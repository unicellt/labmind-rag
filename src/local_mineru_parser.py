from __future__ import annotations

import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path

from src.schemas import ParsedPage


class LocalMinerUParser:
    def __init__(
        self,
        executable: Path,
        home: Path,
        output_dir: Path,
        backend: str = "pipeline",
    ):
        self.executable = executable
        self.home = home
        self.output_dir = output_dir
        self.backend = backend

    def parse_pdf(self, pdf_path: Path) -> list[ParsedPage]:
        self.validate()
        content_list = self._find_content_list(pdf_path)
        if content_list is None:
            self._run_mineru(pdf_path)
            content_list = self._find_content_list(pdf_path)
        if content_list is None:
            raise RuntimeError(f"MinerU did not produce content_list.json for {pdf_path.name}")
        return self._read_content_list(pdf_path.name, content_list)

    def validate(self) -> None:
        if not self.executable.is_file():
            raise RuntimeError(f"MinerU executable not found: {self.executable}")
        config_path = self.home / "mineru.json"
        if not config_path.is_file():
            raise RuntimeError(f"MinerU config not found: {config_path}")

    def _run_mineru(self, pdf_path: Path) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({
            "USERPROFILE": str(self.home),
            "HOME": str(self.home),
            "MINERU_TOOLS_CONFIG_JSON": "mineru.json",
            "MINERU_MODEL_SOURCE": "local",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        })
        command = [
            str(self.executable),
            "-p", str(pdf_path),
            "-o", str(self.output_dir),
            "-b", self.backend,
            "-m", "auto",
            "-l", "ch",
            "-f", "false",
            "-t", "true",
        ]
        subprocess.run(command, check=True, env=env, cwd=self.home)

    def _find_content_list(self, pdf_path: Path) -> Path | None:
        doc_dir = self.output_dir / pdf_path.stem
        matches = sorted(doc_dir.rglob("*_content_list.json")) if doc_dir.exists() else []
        return matches[0] if matches else None

    @staticmethod
    def _read_content_list(doc_name: str, content_list_path: Path) -> list[ParsedPage]:
        rows = json.loads(content_list_path.read_text(encoding="utf-8"))
        page_text: dict[int, list[str]] = defaultdict(list)
        page_section: dict[int, str] = {}
        for row in rows:
            page_idx = int(row.get("page_idx", 0))
            text = str(row.get("text", "")).strip()
            if not text or row.get("type") == "page_number":
                continue
            if row.get("text_level") and page_idx not in page_section:
                page_section[page_idx] = text.splitlines()[0].strip()
            page_text[page_idx].append(text)
        return [
            ParsedPage(
                doc_name=doc_name,
                page_no=page_idx + 1,
                text="\n".join(page_text[page_idx]),
                section_title=page_section.get(page_idx),
                metadata={"source_type": "pdf", "parser": "mineru"},
            )
            for page_idx in sorted(page_text)
        ]
