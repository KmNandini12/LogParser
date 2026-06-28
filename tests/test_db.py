"""Unit and integration tests for PostgreSQL + pgvector schema."""

import pytest
import numpy as np
from src.db.session import init_db, SessionLocal, engine
from src.db.models import LogTemplate, Incident, Base


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Ensure database schema is created and clean up only test-specific rows."""
    init_db()
    with SessionLocal() as session:
        session.query(LogTemplate).filter_by(template_id=999).delete()
        session.query(Incident).filter_by(id=9999).delete()
        session.commit()
    yield
    # Clean up test rows
    with SessionLocal() as session:
        session.query(LogTemplate).filter_by(template_id=999).delete()
        session.query(Incident).filter_by(id=9999).delete()
        session.commit()


def test_log_template_crud_and_vector():
    """Verify LogTemplate creation, vector storage, and querying."""
    db = SessionLocal()
    try:
        # Generate random 384-dimensional unit vector
        vec = np.random.randn(384).astype(np.float32)
        vec = (vec / np.linalg.norm(vec)).tolist()

        template = LogTemplate(
            template_id=999,
            pattern_str="Connection timed out to database <*> after <*> ms",
            occurrence_count=42,
            is_anomaly=True,
            embedding=vec,
        )
        db.add(template)
        db.commit()

        # Query back
        saved = db.query(LogTemplate).filter_by(template_id=999).first()
        assert saved is not None
        assert saved.template_id == 999
        assert saved.is_anomaly is True
        assert saved.occurrence_count == 42
        assert len(saved.embedding) == 384
    finally:
        db.close()


def test_incident_crud_and_similarity():
    """Verify Incident creation and pgvector cosine distance search."""
    db = SessionLocal()
    try:
        vec1 = np.zeros(384, dtype=np.float32)
        vec1[0] = 1.0  # Unit vector pointing along dimension 0
        vec1 = vec1.tolist()

        incident = Incident(
            id=9999,
            title="Database Connection Pool Exhaustion Test",
            service_name="payment-service-test",
            root_cause_summary="HikariCP connection pool exhausted due to unindexed query lock.",
            remediation_steps="1. Increase pool size to 50. 2. Add composite index on (user_id, status).",
            content_embedding=vec1,
        )
        db.add(incident)
        db.commit()

        # Query using pgvector cosine distance operator (<=>)
        closest = (
            db.query(Incident)
            .filter_by(id=9999)
            .order_by(Incident.content_embedding.cosine_distance(vec1))
            .first()
        )
        assert closest is not None
        assert closest.service_name == "payment-service-test"
        assert "HikariCP" in closest.root_cause_summary
    finally:
        db.close()
