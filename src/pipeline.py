"""Log Ingestion & Processing Pipeline.

Coordinates Drain3 template extraction, Redis rolling window anomaly detection,
and PostgreSQL persistence.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Union
from pathlib import Path

from sqlalchemy.orm import Session

from src.parser import LogParser
from src.anomaly import AnomalyTracker
from src.db.session import SessionLocal, init_db
from src.db.models import LogTemplate

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """End-to-end ingestion pipeline coordinating parsing, anomaly scoring, and storage."""

    def __init__(
        self,
        parser: Optional[LogParser] = None,
        tracker: Optional[AnomalyTracker] = None,
        auto_init_db: bool = True,
    ):
        """Initialize the pipeline with its core sub-engines.

        Args:
            parser: Optional pre-configured LogParser instance.
            tracker: Optional pre-configured AnomalyTracker instance.
            auto_init_db: If True, automatically creates database tables.
        """
        self.parser = parser or LogParser()
        self.tracker = tracker or AnomalyTracker()

        if auto_init_db:
            try:
                init_db()
            except Exception as e:
                logger.warning(f"Could not automatically initialize DB: {e}")

    def process_log(
        self,
        raw_log: str,
        timestamp: Optional[float] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Ingest, parse, calculate anomaly status, and persist a single log line.

        Args:
            raw_log: Raw log string.
            timestamp: Optional epoch timestamp.
            db: Optional active SQLAlchemy session.

        Returns:
            Dictionary with template info, anomaly metrics, and DB record status.
        """
        ts = timestamp if timestamp is not None else time.time()

        # Step 1: Parse with Drain3
        parsed = self.parser.parse_line(raw_log)
        template_id = parsed["template_id"]

        if template_id == -1:  # Empty line
            return {
                "parsed": parsed,
                "anomaly": {"is_anomaly": False, "z_score": 0.0},
                "persisted": False,
            }

        # Step 2: Record in Redis and check Z-Score
        self.tracker.record_occurrence(template_id, count=1, timestamp=ts)
        anomaly_result = self.tracker.check_anomaly(template_id, timestamp=ts)

        # Step 3: Persist or update in PostgreSQL
        persisted = False
        owns_db = False
        session = db
        if session is None:
            session = SessionLocal()
            owns_db = True

        try:
            record = session.query(LogTemplate).filter_by(template_id=template_id).first()
            now_utc = datetime.now(timezone.utc)

            if record is None:
                record = LogTemplate(
                    template_id=template_id,
                    pattern_str=parsed["template_str"],
                    occurrence_count=1,
                    is_anomaly=anomaly_result["is_anomaly"],
                    first_seen=now_utc,
                    last_seen=now_utc,
                )
                session.add(record)
            else:
                record.occurrence_count += 1
                record.last_seen = now_utc
                # Once marked anomaly, it remains flagged or updates based on active state
                if anomaly_result["is_anomaly"]:
                    record.is_anomaly = True

            session.commit()
            persisted = True
        except Exception as e:
            session.rollback()
            logger.error(f"Error persisting template {template_id} to DB: {e}")
        finally:
            if owns_db:
                session.close()

        return {
            "parsed": parsed,
            "anomaly": anomaly_result,
            "persisted": persisted,
        }

    def process_file(
        self,
        file_path: Union[str, Path],
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        """Process an entire log file through the pipeline.

        Args:
            file_path: Path to the log file.
            batch_size: Database commit batch frequency.

        Returns:
            Summary dictionary with processed count, anomaly count, and clusters.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        total_lines = 0
        anomaly_count = 0
        anomalous_templates = set()

        db = SessionLocal()
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    res = self.process_log(line, db=db)
                    total_lines += 1
                    if res["anomaly"]["is_anomaly"]:
                        anomaly_count += 1
                        anomalous_templates.add(res["parsed"]["template_id"])

                    if total_lines % batch_size == 0:
                        db.commit()

            db.commit()
        finally:
            db.close()

        return {
            "total_lines": total_lines,
            "total_templates": self.parser.get_total_clusters(),
            "anomalous_events": anomaly_count,
            "anomalous_templates": list(anomalous_templates),
            "compression_ratio": self.parser.calculate_compression_ratio(),
        }
