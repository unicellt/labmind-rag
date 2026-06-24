from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

@dataclass
class PathConfig:
    source_docs: list[Path]
    parsed_docs: Path
    chunks: Path
    index_store: Path
    examples_dir: Path | None = None
    raw_docs: Path | None = None
    vector_store: Path | None = None

@dataclass
class ParserConfig:
    preferred: str = "local_mineru"
    local_mineru_executable: Path = Path(".mineru-venv/bin/mineru")
    local_mineru_home: Path = Path(".mineru-home")
    local_mineru_output_dir: Path = Path("data/parsed/mineru")
    local_mineru_backend: str = "pipeline"
    local_mineru_fallback: bool = False
    mineru_api_base: str = "https://mineru.net/api/v4"
    mineru_input_dir: Path = Path("data/raw_docs")
    mineru_output_dir: Path = Path("data/parsed/mineru")
    docx_fallback: bool = True

@dataclass
class ChunkingConfig:
    chunk_size: int = 900
    chunk_overlap: int = 150

@dataclass
class RetrievalConfig:
    top_k: int = 5
    mode: str = "keyword"
    candidate_multiplier: int = 4
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    keyword_weight: float = 0.5
    vector_weight: float = 0.5
    keyword_confidence_threshold: float = 0.5
    confident_keyword_weight: float = 0.7
    rrf_k: int = 60
    vector_min_score: float = 0.3
    vector_only_min_score: float = 0.55
    vector_batch_size: int = 32

@dataclass
class LLMConfig:
    provider: str = "openai_compatible"
    model: str = "Qwen/Qwen3-8B"
    temperature: float = 0.0
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key_env: str = "SILICONFLOW_API_KEY"

@dataclass
class AppConfig:
    paths: PathConfig
    parser: ParserConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    llm: LLMConfig

def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(config_path)
    config_root = config_path.resolve().parent
    with open(config_path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    def resolve_path(value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else config_root / path

    path_raw = raw["paths"]
    parser_raw = raw.get("parser", {})
    source_docs = path_raw.get("source_docs")
    if not source_docs:
        source_docs = list(Path(path_raw["raw_docs"]).glob("*"))
    source_doc_paths = [resolve_path(path) for path in source_docs]
    examples_dir = resolve_path(path_raw.get("examples_dir", "data/examples"))
    seen_sources = {path.resolve() for path in source_doc_paths}
    for path in sorted(examples_dir.glob("*.pdf")):
        resolved = path.resolve()
        if resolved not in seen_sources:
            source_doc_paths.append(path)
            seen_sources.add(resolved)

    paths = PathConfig(
        source_docs=source_doc_paths,
        parsed_docs=resolve_path(path_raw["parsed_docs"]),
        chunks=resolve_path(path_raw["chunks"]),
        index_store=resolve_path(path_raw.get("index_store", path_raw.get("vector_store", "data/index_store"))),
        examples_dir=examples_dir,
        raw_docs=resolve_path(path_raw["raw_docs"]) if "raw_docs" in path_raw else None,
        vector_store=resolve_path(path_raw["vector_store"]) if "vector_store" in path_raw else None,
    )
    parser = ParserConfig(
        preferred=parser_raw.get("preferred", "local_mineru"),
        local_mineru_executable=resolve_path(parser_raw.get("local_mineru_executable", ".mineru-venv/bin/mineru")),
        local_mineru_home=resolve_path(parser_raw.get("local_mineru_home", ".mineru-home")),
        local_mineru_output_dir=resolve_path(parser_raw.get("local_mineru_output_dir", "data/parsed/mineru")),
        local_mineru_backend=parser_raw.get("local_mineru_backend", "pipeline"),
        local_mineru_fallback=parser_raw.get("local_mineru_fallback", False),
        mineru_api_base=parser_raw.get("mineru_api_base", "https://mineru.net/api/v4"),
        mineru_input_dir=resolve_path(parser_raw.get("mineru_input_dir", paths.raw_docs or "data/raw_docs")),
        mineru_output_dir=resolve_path(parser_raw.get("mineru_output_dir", paths.parsed_docs / "mineru")),
        docx_fallback=parser_raw.get("docx_fallback", True),
    )
    return AppConfig(
        paths=paths,
        parser=parser,
        chunking=ChunkingConfig(**raw.get("chunking", {})),
        retrieval=RetrievalConfig(**raw.get("retrieval", {})),
        llm=LLMConfig(**raw.get("llm", {})),
    )
