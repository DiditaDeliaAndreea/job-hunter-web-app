"""Small dependency-free lexical index with optional OpenAI semantic reranking."""

import hashlib
import math
import os
import re
import sqlite3
from typing import Any, Dict, List


_query_embedding_cache: Dict[str, List[float]] = {}
_document_embedding_cache: Dict[str, List[float]] = {}


def _document_text(job: Dict[str, Any]) -> str:
    embedding_text = str(job.get("Embedding Text") or "").strip()
    if embedding_text:
        return embedding_text
    return " ".join(
        str(job.get(field) or "")
        for field in ("Job Title", "Company", "Location", "Job Description", "Missing Requirements")
    ).strip()


def _fts_query(value: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+.#/-]*", value.lower())
    return " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _openai_embeddings(texts: List[str]) -> List[List[float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not texts:
        return []
    try:
        from openai import OpenAI

        response = OpenAI(api_key=api_key).embeddings.create(
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            input=texts,
        )
        return [item.embedding for item in response.data]
    except Exception:
        return []


def search_jobs(jobs: List[Dict[str, Any]], query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Rank jobs using BM25-style FTS5 relevance and optional semantic similarity."""
    if not query.strip():
        return jobs[:limit]

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE jobs_fts USING fts5(job_index UNINDEXED, content)")
        connection.executemany(
            "INSERT INTO jobs_fts(job_index, content) VALUES (?, ?)",
            [(index, _document_text(job)) for index, job in enumerate(jobs)],
        )
        fts_query = _fts_query(query)
        lexical_scores = {
            int(row[0]): max(0.0, -float(row[1]))
            for row in connection.execute(
                "SELECT job_index, bm25(jobs_fts) FROM jobs_fts WHERE jobs_fts MATCH ? ORDER BY bm25(jobs_fts)",
                (fts_query,),
            )
        } if fts_query else {}
    finally:
        connection.close()

    query_key = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
    query_embedding = _query_embedding_cache.get(query_key)
    if query_embedding is None:
        embeddings = _openai_embeddings([query])
        query_embedding = embeddings[0] if embeddings else []
        if query_embedding:
            _query_embedding_cache[query_key] = query_embedding

    candidate_indexes = list(lexical_scores)
    if query_embedding and not candidate_indexes:
        candidate_indexes = list(range(len(jobs)))
    document_embeddings: Dict[int, List[float]] = {}
    document_keys = {
        index: hashlib.sha256(_document_text(jobs[index]).encode("utf-8")).hexdigest()
        for index in candidate_indexes
    }
    missing_indexes = [index for index in candidate_indexes if document_keys[index] not in _document_embedding_cache]
    if query_embedding and missing_indexes:
        embeddings = _openai_embeddings([_document_text(jobs[index]) for index in missing_indexes])
        for index, embedding in zip(missing_indexes, embeddings):
            _document_embedding_cache[document_keys[index]] = embedding
    if query_embedding:
        document_embeddings = {
            index: _document_embedding_cache[document_keys[index]]
            for index in candidate_indexes
            if document_keys[index] in _document_embedding_cache
            and isinstance(_document_embedding_cache[document_keys[index]], list)
        }

    def score(index: int) -> tuple[float, float]:
        lexical = 1 / (1 + abs(lexical_scores.get(index, 0.0)))
        semantic = _cosine_similarity(query_embedding, document_embeddings[index]) if index in document_embeddings else 0.0
        return (0.65 * semantic + 0.35 * lexical, lexical)

    ranked_indexes = sorted(candidate_indexes, key=score, reverse=True)
    return [jobs[index] for index in ranked_indexes[:limit]]