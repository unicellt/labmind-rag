from __future__ import annotations
from dataclasses import asdict, dataclass, field

@dataclass
class ParsedPage:
    doc_name: str
    page_no: int
    text: str
    section_title: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DocumentChunk:
    chunk_id: str
    doc_name: str
    page_no: int
    text: str
    section_title: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class RetrievedChunk(DocumentChunk):
    score: float = 0.0
