"""Lexical BM25 Search Engine for exact error codes and keywords."""

import re
import logging
from typing import Any, Dict, List, Optional
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25SearchEngine:
    """Exact keyword and error-code matcher using BM25Okapi."""

    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.doc_ids: List[int] = []
        self.bm25: Optional[BM25Okapi] = None

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Tokenize text preserving error codes, file paths, and exceptions.

        Splits on whitespace and major delimiters but preserves underscores,
        dots, and colons inside technical tokens (e.g. ERR_502, NullPointerException).
        """
        # Lowercase and split on whitespace and punctuation except technical chars
        tokens = re.findall(r"[A-Za-z0-9_.:$#-]+", text.lower())
        return [t for t in tokens if len(t) > 1]

    def index_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Build the in-memory BM25 index over provided documents.

        Args:
            documents: List of dicts, each must have 'id' and 'text'.
        """
        self.documents = documents
        self.doc_ids = [doc["id"] for doc in documents]
        tokenized_corpus = [self.tokenize(doc["text"]) for doc in documents]
        self.bm25 = BM25Okapi(tokenized_corpus)
        logger.info(f"Indexed {len(documents)} documents into BM25.")

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search the BM25 index for matching documents.

        Args:
            query: Query string containing error codes or logs.
            top_k: Number of ranked results to return.

        Returns:
            List of results with id, score, rank (1-based), and original doc.
        """
        if self.bm25 is None or not self.documents:
            return []

        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)
        # Pair scores with document indices
        scored_pairs = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )

        results = []
        rank = 1
        for idx, score in scored_pairs[:top_k]:
            if score > 0:  # Only return documents with positive lexical overlap
                results.append(
                    {
                        "id": self.doc_ids[idx],
                        "score": float(score),
                        "rank": rank,
                        "document": self.documents[idx],
                    }
                )
                rank += 1

        return results
