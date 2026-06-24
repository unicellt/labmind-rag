from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path

import requests

class MinerUParser:
    """MinerU ?????????

    ???MinerU extract/task ???????????? PDF URL?
    ?? docx ?????? PDF ??????????? URL ?? parse_pdf_url?
    """

    def __init__(self, api_key: str | None = None, api_base: str = "https://mineru.net/api/v4"):
        self.api_key = api_key or os.getenv("MINERU_API_KEY")
        self.api_base = api_base.rstrip("/")

    def parse_pdf_url(self, pdf_url: str, output_dir: Path, is_ocr: bool = True) -> Path:
        if not self.api_key:
            raise RuntimeError("??? MINERU_API_KEY??? .env ??? MinerU API Key?")

        task_id = self._create_task(pdf_url, is_ocr=is_ocr)
        zip_path = self._wait_and_download(task_id, output_dir)
        return self._unzip(zip_path, output_dir / task_id)

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _create_task(self, pdf_url: str, is_ocr: bool) -> str:
        payload = {"url": pdf_url, "is_ocr": is_ocr, "enable_formula": False}
        resp = requests.post(f"{self.api_base}/extract/task", headers=self._headers(), json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()["data"]
        return data["task_id"]

    def _wait_and_download(self, task_id: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        while True:
            resp = requests.get(f"{self.api_base}/extract/task/{task_id}", headers=self._headers(), timeout=60)
            resp.raise_for_status()
            result = resp.json()["data"]
            state = result.get("state")
            if state in {"pending", "running"}:
                time.sleep(5)
                continue
            if result.get("err_msg"):
                raise RuntimeError(result["err_msg"])
            if state != "done":
                raise RuntimeError(f"MinerU unknown state: {state}")
            full_zip_url = result.get("full_zip_url")
            if not full_zip_url:
                raise RuntimeError("MinerU ??? full_zip_url?")
            zip_path = output_dir / f"{task_id}.zip"
            with requests.get(full_zip_url, stream=True, timeout=120) as download:
                download.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in download.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return zip_path

    @staticmethod
    def _unzip(zip_path: Path, extract_dir: Path) -> Path:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        return extract_dir
