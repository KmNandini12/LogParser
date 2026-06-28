"""Unit and integration tests for Redis rolling window AnomalyTracker."""

import time
import pytest
import redis
from src.anomaly import AnomalyTracker
from src.config import REDIS_HOST, REDIS_PORT, REDIS_DB


@pytest.fixture
def tracker():
    """Create a clean AnomalyTracker connected to test Redis."""
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    # Clean up test keys
    for key in r.keys("logparser:test:*"):
        r.delete(key)

    tr = AnomalyTracker(
        redis_client=r,
        bucket_seconds=10,
        window_minutes=5,
        z_threshold=3.0,
        key_prefix="logparser:test:template",
    )
    yield tr
    for key in r.keys("logparser:test:*"):
        r.delete(key)


def test_record_and_window_retrieval(tracker):
    """Verify recording increments the current bucket correctly."""
    template_id = 101
    now = time.time()

    # Record 5 occurrences in current bucket
    for _ in range(5):
        tracker.record_occurrence(template_id, timestamp=now)

    counts = tracker.get_window_counts(template_id, timestamp=now)
    assert len(counts) == 30  # 300s / 10s = 30 buckets
    assert counts[-1] == 5  # Most recent bucket has count 5


def test_zero_division_guard(tracker):
    """Verify standard deviation zero-division edge case is safely handled."""
    template_id = 102
    # No history exists
    z, mean, std, count = tracker.compute_z_score(template_id)
    assert z == 0.0
    assert mean == 0.0
    assert std == 0.0


def test_steady_traffic_does_not_trigger_anomaly(tracker):
    """Verify steady, uniform log arrival rate produces Z near zero and no anomaly."""
    template_id = 103
    base_time = 100000.0  # Simulated fixed epoch

    # Populate 29 historical buckets with steady 10 logs each
    for bucket_offset in range(29):
        t = base_time + (bucket_offset * 10)
        tracker.record_occurrence(template_id, count=10, timestamp=t)

    # Current bucket arrives with normal 10 logs
    current_time = base_time + (29 * 10)
    tracker.record_occurrence(template_id, count=10, timestamp=current_time)

    result = tracker.check_anomaly(template_id, timestamp=current_time)
    assert result["is_anomaly"] is False
    assert result["z_score"] < 1.0


def test_mandatory_burst_anomaly_sensitivity_test_2(tracker):
    """Execute Mandatory Test 2 from technical document:

    Procedure:
    1. Stream normal logs (e.g. 10 logs/sec = 100 logs per 10s bucket) for 3 minutes (18 buckets).
    2. Inject an artificial burst of 500 error logs within 5 seconds.
    3. Metric: Peak Z-score > 3.0 within 5 seconds and is_anomaly = True.
    """
    error_template_id = 500
    base_time = 200000.0

    # 1. Simulate 3 minutes (18 buckets of 10s) of background traffic
    # Normal arrival rate: ~10 logs/sec with slight natural variance (95 to 105 per bucket)
    import random
    random.seed(42)

    for bucket_idx in range(18):
        t = base_time + (bucket_idx * 10)
        normal_rate = 100 + random.randint(-5, 5)
        tracker.record_occurrence(error_template_id, count=normal_rate, timestamp=t)

    # 2. Inject artificial burst: 500 errors in active 5-second window
    burst_time = base_time + (18 * 10) + 2  # 2 seconds into the next bucket
    tracker.record_occurrence(error_template_id, count=500, timestamp=burst_time)

    # 3. Evaluate anomaly
    metrics = tracker.check_anomaly(error_template_id, timestamp=burst_time)

    print("\n--- Mandatory Test 2 Verification Results ---")
    print(f"Template ID:           {error_template_id}")
    print(f"Historical Mean (mu):  {metrics['mean']:.2f} logs/bucket")
    print(f"Historical Std (sigma): {metrics['std_dev']:.2f}")
    print(f"Burst Count (x):       {metrics['current_bucket_count']}")
    print(f"Peak Z-Score:          {metrics['z_score']:.2f} (Threshold = 3.0)")
    print(f"Is Anomaly Flagged:    {metrics['is_anomaly']}")
    print("---------------------------------------------")

    # Assertions required by document:
    assert metrics["is_anomaly"] is True
    assert metrics["z_score"] >= 3.0
