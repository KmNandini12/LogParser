"""Drain3 Streaming Log Parser Module.

Provides online, tree-based log parsing to extract generalized templates
and mask dynamic variables (IPs, numbers, UUIDs, timestamps).
"""

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import logging

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence

from src.config import DRAIN3_CONFIG_PATH

logger = logging.getLogger(__name__)


class LogParser:
    """Online log template parser using Drain3 algorithm."""

    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        persistence_file: Optional[Union[str, Path]] = None,
    ):
        """Initialize the LogParser.

        Args:
            config_path: Path to drain3.ini configuration file.
            persistence_file: Optional file path to persist the Drain3 state.
                              If None, runs in-memory.
        """
        self.config_path = str(config_path or DRAIN3_CONFIG_PATH)
        self.persistence_file = str(persistence_file) if persistence_file else None

        self.config = TemplateMinerConfig()
        if Path(self.config_path).exists():
            self.config.load(self.config_path)
        else:
            logger.warning(
                f"Config file not found at {self.config_path}, using Drain3 defaults."
            )

        persistence = None
        if self.persistence_file:
            persistence = FilePersistence(self.persistence_file)

        self.miner = TemplateMiner(persistence_handler=persistence, config=self.config)
        self.processed_line_count = 0

    def parse_line(self, raw_log: str) -> Dict[str, Any]:
        """Parse a single raw log line into structured template information.

        Args:
            raw_log: Raw log string from file or network stream.

        Returns:
            Dictionary containing template_id, template_str, change_type,
            cluster_size, extracted parameters, and original log.
        """
        cleaned_log = raw_log.strip()
        if not cleaned_log:
            return {
                "template_id": -1,
                "template_str": "",
                "change_type": "empty",
                "cluster_size": 0,
                "parameters": [],
                "raw_log": raw_log,
            }

        result = self.miner.add_log_message(cleaned_log)
        self.processed_line_count += 1

        template_str = result.get("template_mined", "")
        template_id = result.get("cluster_id", -1)
        change_type = result.get("change_type", "none")
        cluster_size = result.get("cluster_size", 1)

        # Extract variable parameters matching the template wildcards
        try:
            parameters = self.miner.extract_parameters(template_str, cleaned_log)
            # Drain3 can return Parameter objects, convert them to string values
            extracted_params = [
                p.value if hasattr(p, "value") else str(p) for p in (parameters or [])
            ]
        except Exception:
            extracted_params = []

        return {
            "template_id": template_id,
            "template_str": template_str,
            "change_type": change_type,
            "cluster_size": cluster_size,
            "parameters": extracted_params,
            "raw_log": cleaned_log,
        }

    def parse_stream(self, lines: Iterator[str]) -> Iterator[Dict[str, Any]]:
        """Parse an iterable stream of log lines.

        Args:
            lines: Iterator of log lines.

        Yields:
            Structured parse result dictionaries for each line.
        """
        for line in lines:
            yield self.parse_line(line)

    def parse_file(self, file_path: Union[str, Path]) -> Iterator[Dict[str, Any]]:
        """Parse a log file line-by-line in a streaming manner.

        Args:
            file_path: Path to the log file.

        Yields:
            Structured parse result dictionaries for each line.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {path}")

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                yield self.parse_line(line)

    def get_total_clusters(self) -> int:
        """Return the number of unique log templates discovered so far."""
        return len(self.miner.drain.id_to_cluster)

    def get_all_templates(self) -> List[Dict[str, Any]]:
        """Get summary list of all discovered clusters and templates."""
        templates = []
        for cluster_id, cluster in self.miner.drain.id_to_cluster.items():
            templates.append(
                {
                    "template_id": cluster_id,
                    "template_str": cluster.get_template(),
                    "size": cluster.size,
                }
            )
        return templates

    def calculate_compression_ratio(self) -> float:
        """Calculate the percentage reduction in log volume.

        Formula: 1.0 - (total_unique_templates / total_processed_lines)

        Returns:
            Float between 0.0 and 1.0 representing compression ratio.
        """
        if self.processed_line_count == 0:
            return 0.0
        unique_clusters = self.get_total_clusters()
        return 1.0 - (unique_clusters / self.processed_line_count)
