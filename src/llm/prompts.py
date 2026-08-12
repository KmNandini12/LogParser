"""Prompt templates for deterministic Root Cause Analysis."""

from typing import Any, Dict, List


def build_rca_prompt(
    log_query: str,
    templates: List[Dict[str, Any]],
    anomalies: List[Dict[str, Any]],
    matched_incidents: List[Dict[str, Any]],
) -> str:
    """Construct a constrained prompt guiding the LLM to output a strict 3-part RCA report.

    Args:
        log_query: Input query or raw log snippet.
        templates: Parameterized log templates extracted by Drain3.
        anomalies: Active anomaly spike metrics (Z-score, counts).
        matched_incidents: Top post-mortems retrieved via Hybrid RRF search.

    Returns:
        Formatted prompt string.
    """
    # 1. Format extracted templates
    templates_str = ""
    for t in templates[:5]:
        templates_str += f"- Template #{t.get('template_id')}: {t.get('template_str')} (Count: {t.get('cluster_size', 1)})\n"

    # 2. Format anomaly metrics
    anomalies_str = ""
    for a in anomalies:
        anomalies_str += (
            f"- Template #{a.get('template_id')}: Peak Z-Score={a.get('z_score', 0):.2f}, "
            f"Arrival Count={a.get('current_bucket_count', 0)}, Active Spike={a.get('is_anomaly')}\n"
        )
    if not anomalies_str:
        anomalies_str = "- No high-frequency statistical burst detected.\n"

    # 3. Format matched historical incident context
    incidents_str = ""
    for i, inc in enumerate(matched_incidents[:3], start=1):
        incidents_str += (
            f"\n[Historical Post-Mortem #{i}]\n"
            f"Title: {inc.get('title')}\n"
            f"Service: {inc.get('service_name')}\n"
            f"Historical Root Cause: {inc.get('root_cause_summary')}\n"
            f"Proven Remediation: {inc.get('remediation_steps')}\n"
            f"RRF Match Score: {inc.get('rrf_score', 0):.4f}\n"
        )

    prompt = f"""You are a Principal Site Reliability Engineer (SRE).
Analyze the following active cloud outage telemetry and generate a deterministic Root Cause Analysis (RCA) report.

CRITICAL INSTRUCTIONS:
- Base your analysis STRICTLY on the extracted log templates, anomaly metrics, and matching historical incident post-mortems provided below.
- Do NOT hallucinate causes outside the evidence.
- Your response MUST follow this exact 3-part Markdown format:

### 1. Probable Root Cause
[Explain the precise technical failure mechanism based on the matched evidence]

### 2. Affected Services
[List the specific microservices or components directly impacted]

### 3. Remediation Steps
1. [Immediate mitigation action]
2. [Permanent configuration or code fix]
3. [Preventative observability action]

---
=== TELEMETRY CONTEXT ===
Incoming Crash Query / Log Snippet:
{log_query}

Extracted Drain3 Templates:
{templates_str or '- None'}

Active Anomaly Signals (Redis Z-Score):
{anomalies_str}

Retrieved Historical Post-Mortems (Hybrid RRF Search):
{incidents_str or '- No historical matches found'}
"""
    return prompt
