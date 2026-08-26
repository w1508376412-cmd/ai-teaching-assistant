from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9][a-z0-9_.\-/]+", re.IGNORECASE)
VECTOR_DIMENSIONS = 2048


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese with phrase and character n-grams plus ASCII words."""
    tokens: list[str] = []
    for segment in TOKEN_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            if 2 <= len(segment) <= 12:
                tokens.append(segment)
            for size in (2, 3, 4):
                if len(segment) >= size:
                    tokens.extend(
                        segment[index : index + size]
                        for index in range(len(segment) - size + 1)
                    )
        elif len(segment) >= 2:
            tokens.append(segment)
    return tokens


@dataclass(frozen=True)
class RAGChunk:
    id: str
    disease: str
    disease_en: str
    category: str
    pathogen: str
    legal_class: str
    document: str
    section: str
    content: str
    source: str

    @classmethod
    def from_dict(cls, data: dict) -> "RAGChunk":
        required = ("id", "disease", "document", "section", "content", "source")
        missing = [field for field in required if not str(data.get(field, "")).strip()]
        if missing:
            raise ValueError(f"知识块缺少字段：{', '.join(missing)}")
        return cls(
            id=str(data["id"]).strip(),
            disease=str(data["disease"]).strip(),
            disease_en=str(data.get("disease_en", "")).strip(),
            category=str(data.get("category", "")).strip(),
            pathogen=str(data.get("pathogen", "")).strip(),
            legal_class=str(data.get("legal_class", "")).strip(),
            document=str(data["document"]).strip(),
            section=str(data["section"]).strip(),
            content=str(data["content"]).strip(),
            source=str(data["source"]).strip(),
        )

    def indexed_text(self) -> str:
        metadata = "\n".join(
            filter(
                None,
                [
                    self.disease,
                    self.disease,
                    self.disease_en,
                    self.category,
                    self.pathogen,
                    self.legal_class,
                    self.document,
                    self.document,
                    self.section,
                    self.section,
                ],
            )
        )
        return f"{metadata}\n{self.content}"


@dataclass
class RetrievalCandidate:
    chunk: RAGChunk
    bm25_score: float
    vector_score: float
    fusion_score: float
    rerank_score: float


class StructuredRAG:
    """In-memory hybrid RAG index for a small, curated structured corpus."""

    def __init__(self, path: Path):
        self.path = path
        self.chunks = self._load_chunks(path)
        self._token_counts: list[Counter[str]] = []
        self._document_lengths: list[int] = []
        document_frequency: Counter[str] = Counter()

        for chunk in self.chunks:
            counts = Counter(tokenize(chunk.indexed_text()))
            self._token_counts.append(counts)
            length = sum(counts.values())
            self._document_lengths.append(length)
            document_frequency.update(counts.keys())

        self._average_length = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 1.0
        )
        count = max(len(self.chunks), 1)
        self._idf = {
            token: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }
        self._vectors = [self._vectorize(counts) for counts in self._token_counts]

    @staticmethod
    def _load_chunks(path: Path) -> list[RAGChunk]:
        if not path.exists():
            raise FileNotFoundError(f"RAG 数据文件不存在：{path}")
        chunks: list[RAGChunk] = []
        seen_ids: set[str] = set()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                chunk = RAGChunk.from_dict(json.loads(line))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"RAG 数据第 {line_number} 行无效：{exc}") from exc
            if chunk.id in seen_ids:
                raise ValueError(f"RAG 数据存在重复 ID：{chunk.id}")
            seen_ids.add(chunk.id)
            chunks.append(chunk)
        if not chunks:
            raise ValueError("RAG 数据为空。")
        return chunks

    @staticmethod
    def _hash_token(token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % VECTOR_DIMENSIONS, 1.0 if value & 1 else -1.0

    def _vectorize(self, counts: Counter[str]) -> dict[int, float]:
        vector: dict[int, float] = {}
        for token, frequency in counts.items():
            index, sign = self._hash_token(token)
            idf = self._idf.get(token, math.log(len(self.chunks) + 1.0))
            weight = (1.0 + math.log(frequency)) * idf * sign
            vector[index] = vector.get(index, 0.0) + weight
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        return {index: value / norm for index, value in vector.items()}

    @staticmethod
    def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(index, 0.0) for index, value in left.items())

    def _bm25(self, query_tokens: list[str], index: int) -> float:
        counts = self._token_counts[index]
        document_length = self._document_lengths[index]
        score = 0.0
        k1 = 1.5
        b = 0.75
        for token in set(query_tokens):
            frequency = counts.get(token, 0)
            if not frequency:
                continue
            denominator = frequency + k1 * (
                1.0 - b + b * document_length / self._average_length
            )
            score += self._idf.get(token, 0.0) * frequency * (k1 + 1.0) / denominator
        return score

    @staticmethod
    def _rank_map(scores: list[float]) -> dict[int, int]:
        return {
            index: rank
            for rank, index in enumerate(
                sorted(range(len(scores)), key=lambda item: scores[item], reverse=True),
                1,
            )
        }

    def _deterministic_rerank(
        self,
        query: str,
        query_tokens: list[str],
        chunk: RAGChunk,
        fusion_score: float,
    ) -> float:
        searchable = chunk.indexed_text().lower()
        unique_terms = set(query_tokens)
        coverage = (
            sum(1 for term in unique_terms if term in searchable) / len(unique_terms)
            if unique_terms
            else 0.0
        )
        disease_match = 1.0 if chunk.disease and chunk.disease in query else 0.0
        document_match = 1.0 if chunk.document and chunk.document in query else 0.0
        section_terms = set(tokenize(chunk.section))
        section_overlap = (
            len(unique_terms & section_terms) / len(unique_terms) if unique_terms else 0.0
        )
        return (
            fusion_score * 100.0
            + coverage * 2.4
            + disease_match * 3.0
            + document_match * 1.5
            + section_overlap * 1.2
        )

    def search(self, query: str, candidate_k: int = 16) -> list[RetrievalCandidate]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        bm25_scores = [self._bm25(query_tokens, index) for index in range(len(self.chunks))]
        query_vector = self._vectorize(Counter(query_tokens))
        vector_scores = [self._cosine(query_vector, vector) for vector in self._vectors]
        bm25_ranks = self._rank_map(bm25_scores)
        vector_ranks = self._rank_map(vector_scores)

        candidates: list[RetrievalCandidate] = []
        for index, chunk in enumerate(self.chunks):
            fusion = 0.55 / (60 + bm25_ranks[index]) + 0.45 / (60 + vector_ranks[index])
            rerank = self._deterministic_rerank(query, query_tokens, chunk, fusion)
            candidates.append(
                RetrievalCandidate(
                    chunk=chunk,
                    bm25_score=bm25_scores[index],
                    vector_score=vector_scores[index],
                    fusion_score=fusion,
                    rerank_score=rerank,
                )
            )
        candidates.sort(key=lambda item: item.rerank_score, reverse=True)
        return candidates[:candidate_k]

    def stats(self) -> dict:
        return {
            "chunks": len(self.chunks),
            "diseases": len({chunk.disease for chunk in self.chunks}),
            "documents": len({chunk.document for chunk in self.chunks}),
            "sources": len({chunk.source for chunk in self.chunks}),
            "vector_dimensions": VECTOR_DIMENSIONS,
            "vector_method": "tfidf-feature-hashing",
            "fusion_method": "weighted-rrf",
        }


def build_context(
    candidates: list[RetrievalCandidate],
    max_chunks: int = 8,
    max_characters: int = 18000,
) -> tuple[str, list[dict]]:
    blocks: list[str] = []
    citations: list[dict] = []
    total = 0
    for candidate in candidates:
        chunk = candidate.chunk
        label = f"K{len(citations) + 1}"
        block = (
            f"[{label}]\n"
            f"病种：{chunk.disease}\n"
            f"类别：{chunk.category}\n"
            f"病原体：{chunk.pathogen or '未注明'}\n"
            f"法定分类：{chunk.legal_class or '未注明'}\n"
            f"文档：{chunk.document}\n"
            f"章节：{chunk.section}\n"
            f"来源：{chunk.source}\n"
            f"内容：{chunk.content}"
        )
        if blocks and total + len(block) > max_characters:
            continue
        blocks.append(block)
        total += len(block)
        excerpt = re.sub(r"\s+", " ", chunk.content).strip()
        citations.append(
            {
                "id": label,
                "chunk_id": chunk.id,
                "disease": chunk.disease,
                "document": chunk.document,
                "section": chunk.section,
                "source": chunk.source,
                "excerpt": excerpt[:220] + ("…" if len(excerpt) > 220 else ""),
            }
        )
        if len(citations) >= max_chunks:
            break
    return "\n\n---\n\n".join(blocks), citations


@lru_cache(maxsize=4)
def get_rag(path: str) -> StructuredRAG:
    return StructuredRAG(Path(path))
