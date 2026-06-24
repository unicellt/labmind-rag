from __future__ import annotations
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from src.schemas import DocumentChunk, RetrievedChunk

class KeywordRetriever:
    MIN_RELEVANCE_SCORE = 0.26

    def __init__(self, chunks: list[DocumentChunk]):
        self.chunks = chunks
        self.term_df: Counter = Counter()
        for chunk in chunks:
            self.term_df.update(set(self._tokenize(chunk.text)))

    def retrieve(self, query: str, top_k: int, doc_name: str | None = None) -> list[RetrievedChunk]:
        query_terms = self._tokenize_query(query)
        if not query_terms or self._is_out_of_vocabulary_query(query_terms):
            return []
        scored = []
        for chunk in self.chunks:
            if doc_name and chunk.doc_name != doc_name:
                continue
            doc_terms = self._tokenize(chunk.text)
            if not self._has_distinctive_match(query_terms, doc_terms):
                continue
            score = self._score(query_terms, doc_terms, chunk.text)
            if score >= self.MIN_RELEVANCE_SCORE:
                scored.append(RetrievedChunk(**chunk.to_dict(), score=score))
        return sorted(scored, key=lambda x: x.score, reverse=True)[:top_k]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        ascii_terms = re.findall(r"[a-zA-Z0-9_\-]+", text.lower())
        chinese_runs = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
        chinese_words = []
        for run in chinese_runs:
            chinese_words.append(run)
            chinese_words.extend(run[index:index + 2] for index in range(len(run) - 1))
        chinese_chars = re.findall(r"[\u4e00-\u9fa5]", text)
        return ascii_terms + chinese_words + chinese_chars

    @classmethod
    def _tokenize_query(cls, text: str) -> list[str]:
        normalized = text
        for phrase in ["请问", "如何", "怎么", "哪些", "什么", "是否", "需要", "这个", "当前", "文档", "实验室", "中", "有"]:
            normalized = normalized.replace(phrase, " ")
        normalized = re.sub(r"\b(sop|protocol)\b", " ", normalized, flags=re.I)
        return cls._tokenize(normalized)

    def _score(self, query_terms: list[str], doc_terms: list[str], raw_text: str) -> float:
        if not query_terms or not doc_terms:
            return 0.0
        doc_counter = Counter(doc_terms)
        lowered = raw_text.lower()
        unique_query_terms = set(query_terms)
        total_weight = 0.0
        matched_weight = 0.0
        for term in unique_query_terms:
            base_weight = 2.0 if len(term) > 1 else 0.1
            idf = math.log((len(self.chunks) + 1) / (self.term_df.get(term, 0) + 1)) + 1.0
            weight = base_weight * idf
            total_weight += weight
            if term in doc_counter:
                matched_weight += weight
            if len(term) > 1 and term.lower() in lowered:
                matched_weight += weight * 0.5
        return matched_weight / max(total_weight, 1.0)

    def _has_distinctive_match(self, query_terms: list[str], doc_terms: list[str]) -> bool:
        doc_term_set = set(doc_terms)
        max_df = max(2, int(len(self.chunks) * 0.1))
        return any(
            len(term) > 1 and 0 < self.term_df.get(term, 0) <= max_df and term in doc_term_set
            for term in set(query_terms)
        )

    def _is_out_of_vocabulary_query(self, query_terms: list[str]) -> bool:
        multi_terms = {term for term in query_terms if len(term) > 1}
        if not multi_terms:
            return False
        unseen = sum(1 for term in multi_terms if self.term_df.get(term, 0) == 0)
        return unseen / len(multi_terms) > 0.5

class SimpleReranker:
    """Lightweight local reranker matching the diagram's reranking stage.

    It boosts chunks that contain SOP markers, parameters, page marks, and exact query terms.
    Replace this class with an LLM reranker later if needed.
    """

    def rerank(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        top_k: int,
        boost_scale: float = 1.0,
    ) -> list[RetrievedChunk]:
        question_terms = set(KeywordRetriever._tokenize(question))
        for chunk in chunks:
            text = chunk.text.lower()
            boost = 0.0
            if chunk.page_no:
                boost += 0.05
            if re.search(r"\d+\s*(ul|uL|UL|ml|mL|ML|min|h|rpm|g|mg|ng|%)", text, re.I):
                boost += 0.18
            if any(token in text for token in ["步骤", "操作", "加入", "混匀", "孵育", "离心", "buffer", "pcr", "protocol", "sop"]):
                boost += 0.12
            if any(token in text for token in ["试剂", "材料", "primer", "enzyme", "抗体", "培养基"]):
                boost += 0.10
            if any(token in text for token in ["注意", "安全", "危险", "ppe", "废弃物"]):
                boost += 0.10
            exact_hits = sum(1 for term in question_terms if len(term) > 1 and term.lower() in text)
            boost += min(exact_hits * 0.04, 0.24)
            chunk.score = round(chunk.score + (boost * boost_scale), 4)
        return sorted(chunks, key=lambda x: x.score, reverse=True)[:top_k]


class FaissVectorIndex:
    INDEX_FILE = "chunks.faiss"
    METADATA_FILE = "chunks.metadata.json"

    def __init__(self, store_dir: Path, model_name: str, batch_size: int = 32):
        self.store_dir = Path(store_dir)
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None
        self._index = None
        self._metadata = None

    def build(self, chunks: list[DocumentChunk]) -> None:
        faiss = self._import_faiss()
        texts = [self._embedding_text(chunk) for chunk in chunks]
        embeddings = self._encode(texts)
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self.store_dir / self.INDEX_FILE))
        self._index = index
        metadata = {
            "model": self.model_name,
            "dimension": int(embeddings.shape[1]),
            "chunk_ids": [chunk.chunk_id for chunk in chunks],
        }
        (self.store_dir / self.METADATA_FILE).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._metadata = metadata

    def search(
        self,
        query: str,
        chunks: list[DocumentChunk],
        top_k: int,
        min_score: float = 0.3,
        doc_name: str | None = None,
    ) -> list[RetrievedChunk]:
        faiss = self._import_faiss()
        metadata = self._load_metadata()
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        expected_ids = metadata.get("chunk_ids", [])
        if metadata.get("model") != self.model_name or set(expected_ids) != set(chunk_by_id):
            raise RuntimeError("FAISS index is stale; rebuild the knowledge base index")

        if self._index is None:
            self._index = faiss.read_index(str(self.store_dir / self.INDEX_FILE))
        index = self._index
        query_vector = self._encode([query])
        search_k = index.ntotal if doc_name else min(index.ntotal, max(top_k * 8, top_k))
        scores, positions = index.search(query_vector, search_k)
        results = []
        for score, position in zip(scores[0], positions[0]):
            if position < 0 or float(score) < min_score:
                continue
            chunk = chunk_by_id.get(expected_ids[position])
            if chunk is None or (doc_name and chunk.doc_name != doc_name):
                continue
            results.append(RetrievedChunk(**chunk.to_dict(), score=float(score)))
            if len(results) >= top_k:
                break
        return results

    def exists(self) -> bool:
        return (self.store_dir / self.INDEX_FILE).exists() and (
            self.store_dir / self.METADATA_FILE
        ).exists()

    def _load_metadata(self) -> dict:
        if not self.exists():
            raise RuntimeError("FAISS index does not exist; rebuild the knowledge base index")
        if self._metadata is None:
            self._metadata = json.loads(
                (self.store_dir / self.METADATA_FILE).read_text(encoding="utf-8")
            )
        return self._metadata

    def _encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for vector retrieval"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=len(texts) > self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype="float32")

    @staticmethod
    def _embedding_text(chunk: DocumentChunk) -> str:
        section = f"\n章节：{chunk.section_title}" if chunk.section_title else ""
        return f"文档：{chunk.doc_name}{section}\n{chunk.text}"

    @staticmethod
    def _import_faiss():
        try:
            import faiss
        except ModuleNotFoundError as exc:
            raise RuntimeError("faiss-cpu is required for vector retrieval") from exc
        return faiss


class HybridRetriever:
    def __init__(
        self,
        keyword_retriever: KeywordRetriever,
        vector_index: FaissVectorIndex,
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
        keyword_confidence_threshold: float = 0.5,
        confident_keyword_weight: float = 0.7,
        rrf_k: int = 60,
        vector_min_score: float = 0.3,
        vector_only_min_score: float = 0.55,
    ):
        self.keyword_retriever = keyword_retriever
        self.vector_index = vector_index
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.keyword_confidence_threshold = keyword_confidence_threshold
        self.confident_keyword_weight = confident_keyword_weight
        self.rrf_k = rrf_k
        self.vector_min_score = vector_min_score
        self.vector_only_min_score = vector_only_min_score

    def retrieve(
        self,
        query: str,
        chunks: list[DocumentChunk],
        top_k: int,
        doc_name: str | None = None,
    ) -> list[RetrievedChunk]:
        keyword_results = self.keyword_retriever.retrieve(query, top_k, doc_name=doc_name)
        vector_results = self.vector_index.search(
            query,
            chunks,
            top_k,
            min_score=self.vector_min_score,
            doc_name=doc_name,
        )
        if not keyword_results and (
            not vector_results or vector_results[0].score < self.vector_only_min_score
        ):
            return []
        keyword_weight = self.keyword_weight
        vector_weight = self.vector_weight
        if keyword_results and keyword_results[0].score >= self.keyword_confidence_threshold:
            keyword_weight = self.confident_keyword_weight
            vector_weight = 1.0 - keyword_weight
        fused: dict[str, RetrievedChunk] = {}
        scores: Counter = Counter()
        for weight, results in (
            (keyword_weight, keyword_results),
            (vector_weight, vector_results),
        ):
            for rank, item in enumerate(results, start=1):
                fused[item.chunk_id] = item
                scores[item.chunk_id] += (
                    weight * (self.rrf_k + 1) / (self.rrf_k + rank)
                )
        if keyword_results and keyword_results[0].score >= self.keyword_confidence_threshold:
            for item in keyword_results:
                scores[item.chunk_id] += item.score
        elif keyword_results:
            scores[keyword_results[0].chunk_id] += keyword_results[0].score * 0.5
        for chunk_id, item in fused.items():
            item.score = round(scores[chunk_id], 6)
        return sorted(fused.values(), key=lambda item: item.score, reverse=True)[:top_k]
