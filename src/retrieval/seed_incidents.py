"""Seed script to populate historical incident post-mortems into PostgreSQL with pgvector embeddings."""

import json
import logging
from pathlib import Path
from typing import Optional

from src.db.session import SessionLocal, init_db
from src.db.models import Incident
from sqlalchemy import text
from src.retrieval.embeddings import EmbeddingGenerator
from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


def seed_incidents(
    json_path: Optional[Path] = None,
    batch_size: int = 16,
) -> int:
    """Load incidents from JSON, generate dense embeddings, and save to PostgreSQL.

    Args:
        json_path: Path to incidents_seed.json.
        batch_size: Embedding batch size.

    Returns:
        Number of seeded incident documents.
    """
    init_db()
    file_path = json_path or (PROJECT_ROOT / "data" / "incidents_seed.json")
    if not file_path.exists():
        raise FileNotFoundError(f"Seed file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        incidents_data = json.load(f)

    logger.info(f"Loaded {len(incidents_data)} incident documents from {file_path.name}")

    # Prepare composite text for embedding
    texts_to_embed = []
    for inc in incidents_data:
        composite = (
            f"Title: {inc['title']}. "
            f"Service: {inc['service_name']}. "
            f"Root Cause: {inc['root_cause_summary']}. "
            f"Remediation: {inc.get('remediation_steps', '')}"
        )
        texts_to_embed.append(composite)

    embedder = EmbeddingGenerator()
    embeddings = embedder.embed_batch(texts_to_embed, batch_size=batch_size)

    db = SessionLocal()
    inserted_count = 0
    try:
        for idx, (inc, emb) in enumerate(zip(incidents_data, embeddings)):
            inc_id = inc["id"]
            existing = db.query(Incident).filter_by(id=inc_id).first()

            if existing is None:
                record = Incident(
                    id=inc_id,
                    title=inc["title"],
                    service_name=inc["service_name"],
                    root_cause_summary=inc["root_cause_summary"],
                    remediation_steps=inc.get("remediation_steps", ""),
                    content_embedding=emb,
                )
                db.add(record)
                inserted_count += 1
            else:
                existing.title = inc["title"]
                existing.service_name = inc["service_name"]
                existing.root_cause_summary = inc["root_cause_summary"]
                existing.remediation_steps = inc.get("remediation_steps", "")
                existing.content_embedding = emb
                inserted_count += 1

        db.commit()

        # Synchronize PostgreSQL auto-increment sequence with the max explicit ID
        db.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('incidents', 'id'), "
                "COALESCE((SELECT MAX(id) FROM incidents), 1));"
            )
        )
        db.commit()

        logger.info(f"Successfully seeded {inserted_count} incidents into PostgreSQL.")
        return inserted_count
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_incidents()
