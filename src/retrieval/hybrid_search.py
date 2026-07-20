"""Hybrid Search Engine combining BM25 and Dense Vector search with Reciprocal Rank Fusion (RRF)."""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.retrieval.bm25_search import BM25SearchEngine
from src.retrieval.vector_search import VectorSearchEngine
from src.retrieval.embeddings import EmbeddingGenerator
from src.db.session import SessionLocal
from src.db.models import Incident

logger = logging.getLogger(__name__)


class HybridSearchEngine:
    """Combines lexical BM25 and dense pgvector search using Reciprocal Rank Fusion."""

    def __init__(
        self,
        bm25_engine: Optional[BM25SearchEngine] = None,
        vector_engine: Optional[VectorSearchEngine] = None,
        embedder: Optional[EmbeddingGenerator] = None,
        rrf_k: int = 60,
    ):
        """Initialize hybrid search engine.

        Args:
            bm25_engine: Lexical search engine.
            vector_engine: Dense vector search engine.
            embedder: Embedding model instance.
            rrf_k: Smoothing constant for RRF (default: 60, standard in IR literature).
        """
        self.embedder = embedder or EmbeddingGenerator()
        self.bm25 = bm25_engine or BM25SearchEngine()
        self.vector = vector_engine or VectorSearchEngine(embedder=self.embedder)
        self.rrf_k = rrf_k

    def sync_bm25_from_db(self, db: Optional[Session] = None) -> int:
        """Fetch all incidents from the database and populate the BM25 index.

        Returns:
            Number of documents indexed into BM25.
        """
        owns_db = False
        session = db
        if session is None:
            session = SessionLocal()
            owns_db = True

        try:
            incidents = session.query(Incident).all()
            docs = []
            for inc in incidents:
                # Composite searchable text combining title, service, root cause, and remediation
                search_text = (
                    f"{inc.title} {inc.service_name} {inc.root_cause_summary} {inc.remediation_steps or ''}"
                )
                docs.append(
                    {
                        "id": inc.id,
                        "text": search_text,
                        "title": inc.title,
                        "service_name": inc.service_name,
                        "root_cause_summary": inc.root_cause_summary,
                        "remediation_steps": inc.remediation_steps,
                    }
                )
            self.bm25.index_documents(docs)
            return len(docs)
        finally:
            if owns_db:
                session.close()

    def search(
        self,
        query: str,
        top_k: int = 5,
        bm25_candidates: int = 20,
        vector_candidates: int = 20,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Execute hybrid search using Reciprocal Rank Fusion (RRF).

        Formula:
            RRF_score(d) = sum_{m in {bm25, vector}} 1.0 / (k + rank_m(d))

        Args:
            query: User or log query string.
            top_k: Number of final fused results to return.
            bm25_candidates: Number of top results to retrieve from BM25.
            vector_candidates: Number of top results to retrieve from pgvector.
            db: Optional active DB session.

        Returns:
            List of fused results sorted by descending RRF score.
        """
        # Step 1: Execute Lexical BM25 search
        bm25_results = self.bm25.search(query, top_k=bm25_candidates)

        # Step 2: Execute Dense Vector search
        vector_results = self.vector.search(query, top_k=vector_candidates, db=db)

        # Step 3: Reciprocal Rank Fusion (RRF)
        # Map: doc_id -> { "doc": metadata, "rrf_score": float, "bm25_rank": int, "vector_rank": int }
        fused_scores: Dict[int, Dict[str, Any]] = {}

        for item in bm25_results:
            doc_id = item["id"]
            rank = item["rank"]
            rrf_score = 1.0 / (self.rrf_k + rank)

            doc_meta = item.get("document", {})
            fused_scores[doc_id] = {
                "id": doc_id,
                "title": doc_meta.get("title", ""),
                "service_name": doc_meta.get("service_name", ""),
                "root_cause_summary": doc_meta.get("root_cause_summary", ""),
                "remediation_steps": doc_meta.get("remediation_steps", ""),
                "rrf_score": rrf_score,
                "bm25_rank": rank,
                "vector_rank": None,
                "bm25_score": item["score"],
            }

        for item in vector_results:
            doc_id = item["id"]
            rank = item["rank"]
            rrf_contrib = 1.0 / (self.rrf_k + rank)

            if doc_id in fused_scores:
                fused_scores[doc_id]["rrf_score"] += rrf_contrib
                fused_scores[doc_id]["vector_rank"] = rank
                fused_scores[doc_id]["cosine_distance"] = item["distance"]
            else:
                fused_scores[doc_id] = {
                    "id": doc_id,
                    "title": item["title"],
                    "service_name": item["service_name"],
                    "root_cause_summary": item["root_cause_summary"],
                    "remediation_steps": item["remediation_steps"],
                    "rrf_score": rrf_contrib,
                    "bm25_rank": None,
                    "vector_rank": rank,
                    "cosine_distance": item["distance"],
                }

        # Sort all fused candidates by RRF score descending
        sorted_results = sorted(
            fused_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        return sorted_results[:top_k]
