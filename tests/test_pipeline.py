"""Integration tests for the complete IngestionPipeline."""

import pytest
from src.pipeline import IngestionPipeline
from src.db.session import SessionLocal
from src.db.models import LogTemplate


@pytest.fixture
def pipeline():
    return IngestionPipeline(auto_init_db=True)


def test_pipeline_single_log(pipeline):
    """Test parsing, anomaly evaluation, and persistence of a single log."""
    raw_log = "2026-10-02 12:00:00 [ERROR] Database timeout connecting to 10.0.0.5:5432"
    result = pipeline.process_log(raw_log)

    assert result["persisted"] is True
    assert result["parsed"]["template_id"] > 0
    assert result["anomaly"]["is_anomaly"] is False

    # Check database
    db = SessionLocal()
    try:
        record = (
            db.query(LogTemplate)
            .filter_by(template_id=result["parsed"]["template_id"])
            .first()
        )
        assert record is not None
        assert record.occurrence_count >= 1
    finally:
        db.close()
