"""Unit tests for Drain3 LogParser and template mining."""

import pytest
from pathlib import Path
from src.parser import LogParser
from src.config import CONFIG_DIR, DATA_DIR


@pytest.fixture
def parser():
    """Create a fresh in-memory parser instance."""
    config_path = CONFIG_DIR / "drain3.ini"
    return LogParser(config_path=config_path)


def test_parser_initialization(parser):
    """Verify parser initializes correctly with config."""
    assert parser is not None
    assert parser.get_total_clusters() == 0
    assert parser.calculate_compression_ratio() == 0.0


def test_parse_single_line_masking(parser):
    """Test that dynamic IP and numeric variables are masked properly."""
    raw_log = "2026-10-02 10:15:30 [INFO] Connection received from 192.168.1.50:8080 bytes: 1024"
    result = parser.parse_line(raw_log)

    assert result["template_id"] == 1
    assert result["change_type"] == "cluster_created"
    assert "<IP>" in result["template_str"] or "<NUM>" in result["template_str"] or "<:>" in result["template_str"]
    assert parser.get_total_clusters() == 1


def test_identical_log_clustering(parser):
    """Test that logs with the same structure map to the same template_id."""
    log1 = "2026-10-02 10:00:01 [ERROR] Connection lost to 10.0.0.1:9000 timeout"
    log2 = "2026-10-02 10:00:05 [ERROR] Connection lost to 10.0.0.8:9000 timeout"
    log3 = "2026-10-02 10:00:10 [ERROR] Connection lost to 10.1.2.3:8080 timeout"

    res1 = parser.parse_line(log1)
    res2 = parser.parse_line(log2)
    res3 = parser.parse_line(log3)

    assert res1["template_id"] == res2["template_id"]
    assert res2["template_id"] == res3["template_id"]
    assert parser.get_total_clusters() == 1
    assert res3["cluster_size"] == 3


def test_different_log_creates_new_cluster(parser):
    """Test that distinct log patterns generate distinct template IDs."""
    log_a = "2026-10-02 10:00:01 [INFO] User 1024 logged in successfully"
    log_b = "2026-10-02 10:00:02 [CRITICAL] Database disk failure on /dev/sda1"

    res_a = parser.parse_line(log_a)
    res_b = parser.parse_line(log_b)

    assert res_a["template_id"] != res_b["template_id"]
    assert parser.get_total_clusters() == 2


def test_empty_line_handling(parser):
    """Test that empty or whitespace lines are handled gracefully."""
    res = parser.parse_line("   \n")
    assert res["template_id"] == -1
    assert res["change_type"] == "empty"
    assert res["cluster_size"] == 0


def test_compression_ratio_on_hdfs_benchmark(parser):
    """Test that streaming 5,000 HDFS logs results in >= 90% compression."""
    sample_file = DATA_DIR / "sample_logs" / "sample_hdfs.log"
    if not sample_file.exists():
        pytest.skip("sample_hdfs.log not found")

    lines_processed = 0
    for parsed in parser.parse_file(sample_file):
        lines_processed += 1
        assert parsed["template_id"] > 0

    assert lines_processed == 5000
    total_clusters = parser.get_total_clusters()
    compression_ratio = parser.calculate_compression_ratio()

    # 8 distinct templates in 5000 lines should compress by > 99%
    assert total_clusters < 50
    assert compression_ratio >= 0.90
    print(
        f"\n[Test Result] Processed: {lines_processed} lines -> {total_clusters} unique templates. "
        f"Compression: {compression_ratio * 100:.2f}%"
    )


def test_compression_ratio_on_official_loghub_2k(parser):
    """Test that the real Loghub HDFS_2k.log achieves >= 90% compression."""
    loghub_file = DATA_DIR / "sample_logs" / "HDFS_2k.log"
    if not loghub_file.exists():
        pytest.skip("HDFS_2k.log not found")

    lines_processed = 0
    for parsed in parser.parse_file(loghub_file):
        lines_processed += 1

    assert lines_processed == 2000
    total_clusters = parser.get_total_clusters()
    compression_ratio = parser.calculate_compression_ratio()

    assert compression_ratio >= 0.90
    print(
        f"\n[Loghub 2k Result] Processed: {lines_processed} lines -> {total_clusters} unique templates. "
        f"Compression: {compression_ratio * 100:.2f}%"
    )
