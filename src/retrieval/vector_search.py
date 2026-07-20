"""Dense Vector Search Engine querying PostgreSQL with pgvector."""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.db.models import Incident
from src.retrieval.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


class VectorSearchEngine:
    """Dense vector semantic retrieval over PostgreSQL pgvector."""

    def __init__(self, embedder: Optional[EmbeddingGenerator] = None):
        """Initialize vector search engine.

        Args:
            embedder: Optional pre-configured EmbeddingGenerator.
        """
        self.embedder = embedder or EmbeddingGenerator()

    def search_by_vector(
        self,
        query_vector: List[float],
        top_k: int = 10,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Find the nearest incident documents using cosine distance in pgvector.

        Args:
            query_vector: 384-dimensional query vector.
            top_k: Number of nearest neighbors to retrieve.
            db: Optional active SQLAlchemy session.

        Returns:
            Ranked list of matching incident records with similarity scores.
        """
        owns_db = False
        session = db
        if session is None:
            session = SessionLocal()
            owns_db = True

        try:
            # Query ordering by cosine distance (<=>)
            query = (
                session.query(
                    Incident,
                    Incident.content_embedding.cosine_distance(query_vector).label(
                        "distance"
                    ),
                )
                .filter(Incident.content_embedding.isnot(None))
                .order_by("distance")
                .limit(top_k)
            )

            results = []
            for rank, (incident, distance) in enumerate(query.all(), start=1):
                cosine_dist = float(distance) if distance is not None else 1.0
                similarity = max(0.0, 1.0 - cosine_dist)
                results.append(
                    {
                        "id": incident.id,
                        "title": incident.title,
                        "service_name": incident.service_name,
                        "root_cause_summary": incident.root_cause_summary,
                        "remediation_steps": incident.remediation_steps,
                        "distance": cosine_dist,
                        "similarity": similarity,
                        "rank": rank,
                    }
                )
            return results
        finally:
            if owns_db:
                session.close()

    def search(
        self,
        query_text: str,
        top_k: int = 10,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Embed query text and find nearest neighbor incidents.

        Args:
            query_text: Natural language query or log snippet.
            top_k: Number of matches.
            db: Optional database session.

        Returns:
            Ranked list of results.
        """
        query_vector = self.embedder.embed_text(query_text)
        return self.search_by_vector(query_vector, top_k=top_k, db=db)
