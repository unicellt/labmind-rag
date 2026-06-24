from __future__ import annotations
import json
from src.config import AppConfig
from src.generation import AnswerGenerator
from src.ingestion import DocumentIngestor
from src.local_mineru_parser import LocalMinerUParser
from src.retrieval import FaissVectorIndex, HybridRetriever, KeywordRetriever, SimpleReranker
from src.schemas import DocumentChunk, RetrievedChunk
from src.utils import read_jsonl, write_jsonl

class LabRAGPipeline:
    def __init__(self, config: AppConfig):
        self.config = config
        self.last_ingest_report: dict = {}
        self._faiss_vector_index = None

    def ingest(self) -> int:
        ingestor = DocumentIngestor(self.config.chunking.chunk_size, self.config.chunking.chunk_overlap)
        pages = self._load_pages(ingestor)
        chunks = ingestor.split_documents(pages)
        count = write_jsonl(self.config.paths.chunks, [chunk.to_dict() for chunk in chunks])
        self._build_vector_index(chunks)
        self._write_index_manifest(chunks)
        chunks_by_doc = {}
        for chunk in chunks:
            chunks_by_doc[chunk.doc_name] = chunks_by_doc.get(chunk.doc_name, 0) + 1
        self.last_ingest_report["chunk_count"] = count
        self.last_ingest_report["chunks_by_doc"] = chunks_by_doc
        return count

    def ingest_document(self, path):
        """Parse one uploaded PDF and merge its chunks into the current index."""
        ingestor = DocumentIngestor(self.config.chunking.chunk_size, self.config.chunking.chunk_overlap)
        if self.config.parser.preferred == "local_mineru":
            parser = LocalMinerUParser(
                executable=self.config.parser.local_mineru_executable,
                home=self.config.parser.local_mineru_home,
                output_dir=self.config.parser.local_mineru_output_dir,
                backend=self.config.parser.local_mineru_backend,
            )
            pages = parser.parse_pdf(path)
            parser_name = "mineru"
        else:
            pages = ingestor.load_documents([path])
            parser_name = "pypdf2"
        new_chunks = ingestor.split_documents(pages)
        existing = [
            DocumentChunk(**row)
            for row in read_jsonl(self.config.paths.chunks)
            if row.get("doc_name") != path.name
        ]
        chunks = existing + new_chunks
        total_count = write_jsonl(self.config.paths.chunks, [chunk.to_dict() for chunk in chunks])
        self._build_vector_index(chunks)
        self._write_index_manifest(chunks)
        self.last_ingest_report = {
            "preferred_parser": self.config.parser.preferred,
            "fallback_enabled": self.config.parser.local_mineru_fallback,
            "documents": {
                path.name: {
                    "parser": parser_name,
                    "status": "success",
                    "pages": len(pages),
                    "chunks": len(new_chunks),
                }
            },
            "chunk_count": total_count,
            "uploaded_chunk_count": len(new_chunks),
        }
        return total_count

    def _load_pages(self, ingestor: DocumentIngestor):
        source_docs = self._source_docs()
        if self.config.parser.preferred != "local_mineru":
            pages = ingestor.load_documents(source_docs)
            self.last_ingest_report = {
                "preferred_parser": self.config.parser.preferred,
                "documents": {
                    path.name: {"parser": "pypdf2", "status": "success"}
                    for path in source_docs
                },
            }
            return pages
        parser = LocalMinerUParser(
            executable=self.config.parser.local_mineru_executable,
            home=self.config.parser.local_mineru_home,
            output_dir=self.config.parser.local_mineru_output_dir,
            backend=self.config.parser.local_mineru_backend,
        )
        pages = []
        documents = {}
        for path in source_docs:
            if path.suffix.lower() != ".pdf":
                parsed = ingestor.load_documents([path])
                pages.extend(parsed)
                documents[path.name] = {
                    "parser": path.suffix.lower().lstrip(".") or "text",
                    "status": "success",
                    "pages": len(parsed),
                }
                continue
            try:
                parsed = parser.parse_pdf(path)
                pages.extend(parsed)
                documents[path.name] = {
                    "parser": "mineru",
                    "status": "success",
                    "pages": len(parsed),
                }
            except Exception as exc:
                if not self.config.parser.local_mineru_fallback:
                    raise RuntimeError(f"MinerU failed for {path.name}: {exc}") from exc
                parsed = ingestor.load_documents([path])
                pages.extend(parsed)
                documents[path.name] = {
                    "parser": "pypdf2",
                    "status": "fallback",
                    "pages": len(parsed),
                    "error": f"{type(exc).__name__}: {exc}",
                }
        self.last_ingest_report = {
            "preferred_parser": "local_mineru",
            "fallback_enabled": self.config.parser.local_mineru_fallback,
            "documents": documents,
        }
        return pages

    def _source_docs(self):
        source_docs = list(self.config.paths.source_docs)
        seen = {path.resolve() for path in source_docs}
        examples_dir = self.config.paths.examples_dir
        if examples_dir and examples_dir.exists():
            for path in sorted(examples_dir.glob("*.pdf")):
                resolved = path.resolve()
                if resolved not in seen:
                    source_docs.append(path)
                    seen.add(resolved)
        return source_docs

    def search(self, question: str, top_k: int | None = None, doc_name: str | None = None, rerank: bool = True) -> list[dict]:
        top_k = top_k or self.config.retrieval.top_k
        chunks = [DocumentChunk(**row) for row in read_jsonl(self.config.paths.chunks)]
        candidate_k = max(top_k * self.config.retrieval.candidate_multiplier, top_k)
        keyword_retriever = KeywordRetriever(chunks)
        if self.config.retrieval.mode.lower() == "hybrid":
            vector_index = self._get_vector_index()
            candidates = HybridRetriever(
                keyword_retriever,
                vector_index,
                keyword_weight=self.config.retrieval.keyword_weight,
                vector_weight=self.config.retrieval.vector_weight,
                keyword_confidence_threshold=self.config.retrieval.keyword_confidence_threshold,
                confident_keyword_weight=self.config.retrieval.confident_keyword_weight,
                rrf_k=self.config.retrieval.rrf_k,
                vector_min_score=self.config.retrieval.vector_min_score,
                vector_only_min_score=self.config.retrieval.vector_only_min_score,
            ).retrieve(question, chunks, candidate_k, doc_name=doc_name)
        else:
            candidates = keyword_retriever.retrieve(question, candidate_k, doc_name=doc_name)
        # Parent page retrieval placeholder: current chunks preserve page markers in text.
        # Reranking stage: reorder candidates before building the final context.
        if rerank:
            boost_scale = 0.15 if self.config.retrieval.mode.lower() == "hybrid" else 1.0
            candidates = SimpleReranker().rerank(
                question, candidates, top_k, boost_scale=boost_scale
            )
        else:
            candidates = candidates[:top_k]
        return [item.to_dict() for item in candidates]

    def answer(self, question: str, top_k: int | None = None, doc_name: str | None = None, rerank: bool = True, answer_type: str = "综合") -> dict:
        retrieved_dicts = self.search(question, top_k=top_k, doc_name=doc_name, rerank=rerank)
        retrieved = [RetrievedChunk(**row) for row in retrieved_dicts]
        generator = AnswerGenerator(
            self.config.llm.provider,
            self.config.llm.model,
            self.config.llm.temperature,
            base_url=self.config.llm.base_url,
            api_key_env=self.config.llm.api_key_env,
        )
        answer = generator.generate(question, retrieved, answer_type=answer_type)
        generation = {
            "mode": generator.last_mode,
            "provider": self.config.llm.provider,
            "model": self.config.llm.model,
        }
        if generator.last_error:
            generation["error"] = generator.last_error
        return {"answer": answer, "sources": retrieved_dicts, "generation": generation}

    def _write_index_manifest(self, chunks: list[DocumentChunk]) -> None:
        self.config.paths.index_store.mkdir(parents=True, exist_ok=True)
        docs = sorted({chunk.doc_name for chunk in chunks})
        manifest = {
            "retriever": self.config.retrieval.mode.lower(),
            "chunk_count": len(chunks),
            "documents": docs,
            "chunk_path": str(self.config.paths.chunks),
        }
        if self.config.retrieval.mode.lower() == "hybrid":
            manifest["embedding_model"] = self.config.retrieval.embedding_model
            manifest["vector_store"] = str(self._vector_store())
        (self.config.paths.index_store / "index_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_vector_index(self, chunks: list[DocumentChunk]) -> None:
        if self.config.retrieval.mode.lower() != "hybrid":
            return
        vector_index = self._get_vector_index()
        vector_index.build(chunks)

    def _get_vector_index(self):
        if self._faiss_vector_index is None:
            self._faiss_vector_index = FaissVectorIndex(
                self._vector_store(),
                self.config.retrieval.embedding_model,
                self.config.retrieval.vector_batch_size,
            )
        return self._faiss_vector_index

    def _vector_store(self):
        return self.config.paths.vector_store or self.config.paths.index_store / "vectors"
