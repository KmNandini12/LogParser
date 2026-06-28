"""Redis Rolling Window Anomaly Tracker using statistical Z-Score."""

import math
import time
import logging
from typing import Dict, List, Optional, Tuple, Union
import redis

from src.config import REDIS_HOST, REDIS_PORT, REDIS_DB

logger = logging.getLogger(__name__)


class AnomalyTracker:
    """Sliding window anomaly tracker using Redis 10-second buckets and Z-score."""

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        bucket_seconds: int = 10,
        window_minutes: int = 5,
        z_threshold: float = 3.0,
        key_prefix: str = "logparser:template",
    ):
        """Initialize the Anomaly Tracker.

        Args:
            redis_client: Optional existing redis.Redis instance.
            bucket_seconds: Duration of each bucket in seconds (default: 10s).
            window_minutes: Total rolling window span in minutes (default: 5m = 300s).
            z_threshold: Z-score cutoff to flag an anomaly (default: 3.0).
            key_prefix: Redis key namespace prefix.
        """
        self.redis = redis_client or redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
        self.bucket_seconds = bucket_seconds
        self.window_minutes = window_minutes
        self.total_window_seconds = window_minutes * 60
        self.num_buckets = self.total_window_seconds // bucket_seconds  # e.g., 300 / 10 = 30
        self.z_threshold = z_threshold
        self.key_prefix = key_prefix
        # TTL for the Redis hash to automatically reclaim memory (2x window duration)
        self.hash_ttl = self.total_window_seconds * 2

    def _get_bucket_id(self, timestamp: float) -> int:
        """Convert a Unix timestamp to its corresponding bucket index."""
        return int(timestamp // self.bucket_seconds)

    def _get_redis_key(self, template_id: int) -> str:
        """Generate Redis key for a given template."""
        return f"{self.key_prefix}:{template_id}:buckets"

    def record_occurrence(
        self,
        template_id: int,
        count: int = 1,
        timestamp: Optional[float] = None,
    ) -> int:
        """Increment the current bucket count for a given template.

        Args:
            template_id: Drain3 template cluster ID.
            count: Number of occurrences to add (default: 1).
            timestamp: Optional epoch timestamp (defaults to current time).

        Returns:
            The updated count in the active bucket.
        """
        ts = timestamp if timestamp is not None else time.time()
        bucket_id = self._get_bucket_id(ts)
        key = self._get_redis_key(template_id)

        pipe = self.redis.pipeline()
        pipe.hincrby(key, str(bucket_id), count)
        pipe.expire(key, self.hash_ttl)
        results = pipe.execute()
        return int(results[0])

    def get_window_counts(
        self,
        template_id: int,
        timestamp: Optional[float] = None,
    ) -> List[int]:
        """Retrieve bucket counts across the active rolling window.

        Args:
            template_id: Drain3 template cluster ID.
            timestamp: Optional epoch timestamp representing current time.

        Returns:
            List of integer counts for each bucket in the window (oldest to newest).
        """
        current_ts = timestamp if timestamp is not None else time.time()
        current_bucket = self._get_bucket_id(current_ts)
        # 30 buckets: [current_bucket - 29, ..., current_bucket]
        bucket_ids = [str(current_bucket - i) for i in reversed(range(self.num_buckets))]
        key = self._get_redis_key(template_id)

        raw_values = self.redis.hmget(key, bucket_ids)
        return [int(val) if val is not None else 0 for val in raw_values]

    def compute_z_score(
        self,
        template_id: int,
        timestamp: Optional[float] = None,
    ) -> Tuple[float, float, float, int]:
        """Compute the Z-score for the active template arrival rate.

        Formula:
            mean (mu) = sum(counts) / N
            std (sigma) = sqrt(sum((x - mu)^2) / N)
            Z = (current_count - mu_baseline) / max(sigma_baseline, 1.0)

        Args:
            template_id: Drain3 template cluster ID.
            timestamp: Optional epoch timestamp.

        Returns:
            Tuple of (z_score, mean, std_dev, current_bucket_count).
        """
        counts = self.get_window_counts(template_id, timestamp)
        current_count = counts[-1]
        baseline_counts = counts[:-1]  # History preceding the active bucket

        if not baseline_counts or sum(counts) == 0:
            return 0.0, 0.0, 0.0, current_count

        n = len(baseline_counts)
        mean = sum(baseline_counts) / n
        variance = sum((x - mean) ** 2 for x in baseline_counts) / n
        std_dev = math.sqrt(variance)

        # Division by zero guard: if std_dev is 0, use 1.0 as a floor
        effective_sigma = max(std_dev, 1.0)

        # Standard score calculation
        z_score = (current_count - mean) / effective_sigma

        # Floor at 0.0 (we flag rate surges, not dips below zero)
        z_score = max(0.0, z_score)

        return z_score, mean, std_dev, current_count

    def check_anomaly(
        self,
        template_id: int,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Union[bool, float, int]]:
        """Evaluate if the template is in an anomalous spike state.

        Args:
            template_id: Drain3 template cluster ID.
            timestamp: Optional epoch timestamp.

        Returns:
            Dict containing is_anomaly, z_score, mean, std_dev, current_rate.
        """
        z_score, mean, std_dev, current_count = self.compute_z_score(
            template_id, timestamp
        )
        is_anomaly = z_score >= self.z_threshold

        return {
            "template_id": template_id,
            "is_anomaly": is_anomaly,
            "z_score": round(z_score, 4),
            "mean": round(mean, 4),
            "std_dev": round(std_dev, 4),
            "current_bucket_count": current_count,
        }

    def reset_template(self, template_id: int) -> None:
        """Clear all metrics for a given template."""
        key = self._get_redis_key(template_id)
        self.redis.delete(key)
