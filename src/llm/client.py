"""Async client for local Ollama Llama 3.2 execution with deterministic fallback."""

import re
import logging
from typing import Any, Dict, List, Optional
import httpx

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)


class OllamaClient:
    """Async client communicating with local Ollama daemon."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """Initialize Ollama client.

        Args:
            base_url: Ollama HTTP endpoint (default: http://localhost:11434).
            model: Ollama model tag (default: llama3.2:3b).
            timeout: HTTP request timeout in seconds.
        """
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.model = model or OLLAMA_MODEL
        self.timeout = timeout

    async def is_available(self) -> bool:
        """Check if local Ollama service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def generate_rca(
        self,
        prompt: str,
        matched_incidents: Optional[List[Dict[str, Any]]] = None,
        anomalies: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate a structured RCA report using local Ollama or deterministic fallback.

        Args:
            prompt: Structured prompt containing telemetry and matched incident evidence.
            matched_incidents: Retrieved post-mortem documents.
            anomalies: Active anomaly spike signals.

        Returns:
            Dictionary with report_markdown, probable_root_cause,
            affected_services, remediation_steps, and engine_source.
        """
        # Try local Ollama if available
        if await self.is_available():
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    payload = {
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Low temperature for deterministic output
                            "num_predict": 1024,
                        },
                    }
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json=payload,
                    )
                    if response.status_code == 200:
                        raw_output = response.json().get("response", "")
                        parsed = self._parse_markdown_sections(raw_output)
                        parsed["report_markdown"] = raw_output
                        parsed["engine_source"] = f"ollama-{self.model}"
                        return parsed
            except Exception as e:
                logger.warning(f"Ollama inference failed: {e}. Utilizing deterministic synthesis.")

        # Deterministic zero-cost fallback synthesis
        return self._synthesize_fallback(matched_incidents or [], anomalies or [])

    @staticmethod
    def _parse_markdown_sections(markdown_text: str) -> Dict[str, Any]:
        """Extract structured sections from markdown RCA report."""
        root_cause = ""
        services = []
        remediation = []

        rc_match = re.search(
            r"###\s*1\.\s*Probable Root Cause\s*\n(.*?)(?=\n###|\Z)",
            markdown_text,
            re.DOTALL | re.IGNORECASE,
        )
        if rc_match:
            root_cause = rc_match.group(1).strip()

        svc_match = re.search(
            r"###\s*2\.\s*Affected Services\s*\n(.*?)(?=\n###|\Z)",
            markdown_text,
            re.DOTALL | re.IGNORECASE,
        )
        if svc_match:
            lines = [
                l.strip("-* ").strip()
                for l in svc_match.group(1).strip().split("\n")
                if l.strip()
            ]
            services = lines

        rem_match = re.search(
            r"###\s*3\.\s*Remediation Steps\s*\n(.*?)(?=\n###|\Z)",
            markdown_text,
            re.DOTALL | re.IGNORECASE,
        )
        if rem_match:
            steps = [
                re.sub(r"^\d+\.\s*", "", l).strip()
                for l in rem_match.group(1).strip().split("\n")
                if l.strip()
            ]
            remediation = steps

        return {
            "probable_root_cause": root_cause,
            "affected_services": services,
            "remediation_steps": remediation,
        }

    @staticmethod
    def _synthesize_fallback(
        matched_incidents: List[Dict[str, Any]],
        anomalies: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Synthesize a deterministic 3-part RCA report directly from retrieved ground-truth."""
        if matched_incidents:
            primary = matched_incidents[0]
            root_cause = primary.get("root_cause_summary", "Unknown failure mechanism.")
            service = primary.get("service_name", "unknown-service")
            raw_rem = primary.get("remediation_steps", "")
            remediation_steps = [
                s.strip() for s in re.split(r"\d+\.\s*", raw_rem) if s.strip()
            ]
            services = [service]
        else:
            root_cause = "Insufficient historical match to identify confirmed root cause."
            services = ["unknown"]
            remediation_steps = [
                "Inspect live service metrics and stack traces.",
                "Verify database connection pool health.",
                "Review recent code and configuration deployments.",
            ]

        spike_info = ""
        if anomalies:
            spike_info = (
                f"\n*Correlated Anomaly:* Template #{anomalies[0].get('template_id')} "
                f"spiked to Z-score={anomalies[0].get('z_score', 0):.2f} "
                f"with {anomalies[0].get('current_bucket_count', 0)} arrivals."
            )

        report_markdown = f"""### 1. Probable Root Cause
{root_cause}{spike_info}

### 2. Affected Services
- {', '.join(services)}

### 3. Remediation Steps
""" + "\n".join(f"{i}. {step}" for i, step in enumerate(remediation_steps, 1))

        return {
            "report_markdown": report_markdown,
            "probable_root_cause": root_cause,
            "affected_services": services,
            "remediation_steps": remediation_steps,
            "engine_source": "deterministic-rca-synthesizer",
        }
