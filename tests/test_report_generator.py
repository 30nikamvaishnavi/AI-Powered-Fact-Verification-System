"""Integration tests for report generation, Gemini pipeline modes, and exports."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

from fact_checker.gemini_service import GeminiFactCheckService
from fact_checker.models import (
    ManualEvidenceInput,
    VerificationLabel,
    VerificationMode,
)
from fact_checker.report_generator import (
    export_report_csv,
    export_report_json,
    export_report_markdown,
    run_verification_pipeline,
    save_report_to_exports,
)


def _mock_gemini_client_for_source_mode(source_id_placeholder: str | None = None) -> MagicMock:
    """Create a mock genai.Client whose generate_content inspects source_id dynamically."""
    mock_client = MagicMock()

    def _side_effect(*, model: str, contents: str, config: object) -> MagicMock:
        resp = MagicMock()
        # Extract the first SOURCE_ID from the formatted prompt so the mock grounds properly
        sid = source_id_placeholder
        if sid is None:
            for line in contents.splitlines():
                if line.startswith("SOURCE_ID: "):
                    sid = line.replace("SOURCE_ID: ", "").strip()
                    break
        resp.text = json.dumps(
            {
                "label": "SUPPORTED",
                "confidence_score": 0.88,
                "confidence_explanation": "Provided textbook confirms the boiling point.",
                "short_explanation": "The submitted source confirms water boils at 100 degrees Celsius.",
                "source_assessments": (
                    [
                        {
                            "source_id": sid,
                            "evidence_excerpt": "At standard atmospheric pressure, pure water boils at 100 degrees Celsius.",
                            "position": "Supports",
                            "rationale": "Matches claim directly.",
                        }
                    ]
                    if sid
                    else []
                ),
                "unsupported_statements": [],
                "unresolved_questions": [],
                "disagreement_summary": "",
            }
        )
        return resp

    mock_client.models.generate_content.side_effect = _side_effect
    return mock_client


def test_mode_a_manual_source_pipeline_with_mocked_gemini_and_exports(tmp_path: Path) -> None:
    manual = [
        ManualEvidenceInput(
            title="Physics Reference",
            url="https://physics.example.org/water",
            text="At standard atmospheric pressure, pure water boils at 100 degrees Celsius.",
            publication_date="2024-01-15",
        )
    ]
    service = GeminiFactCheckService(
        api_key="test-key",
        model="gemini-2.5-flash",
        client=_mock_gemini_client_for_source_mode(),
    )

    session_id, mode, reports = run_verification_pipeline(
        "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
        verification_mode=VerificationMode.MANUAL_SOURCE,
        manual_entries=manual,
        gemini_service=service,
    )
    assert session_id.startswith("sess-")
    assert mode == VerificationMode.MANUAL_SOURCE.value
    assert len(reports) == 1

    report = reports[0]
    assert report.label == VerificationLabel.SUPPORTED
    assert report.is_preliminary_ai_only is False

    # JSON export
    json_payload = json.loads(export_report_json(report))
    assert json_payload["label"] == "SUPPORTED"
    assert json_payload["verification_mode"] == VerificationMode.MANUAL_SOURCE.value

    # CSV export
    csv_text = export_report_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert rows[0]["final_label"] == "SUPPORTED"
    assert rows[0]["publisher"] == "physics.example.org"

    # Markdown export
    md_text = export_report_markdown(report)
    assert "# Verification Report: `SUPPORTED`" in md_text
    assert "https://physics.example.org/water" in md_text

    # Save exports to directory
    saved_json = save_report_to_exports(report, "json", tmp_path)
    saved_csv = save_report_to_exports(report, "csv", tmp_path)
    saved_md = save_report_to_exports(report, "md", tmp_path)
    assert saved_json.exists() and saved_csv.exists() and saved_md.exists()


def test_mode_b_preliminary_analysis_does_not_invent_sources() -> None:
    mock_client = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps(
        {
            "label": "UNVERIFIED",
            "confidence_score": 0.55,
            "confidence_explanation": "Needs primary source verification.",
            "short_explanation": "Preliminary knowledge suggests the claim requires current budget data.",
            "supporting_points": ["Related program existed previously."],
            "contradicting_points": [],
            "unsupported_statements": ["Exact 2026 funding figure is unverified."],
            "unresolved_questions": ["What does the official 2026 budget state?"],
        }
    )
    mock_client.models.generate_content.return_value = resp

    service = GeminiFactCheckService(api_key="test-key", client=mock_client)
    _, mode, reports = run_verification_pipeline(
        "The 2026 research budget doubled to 50 billion dollars.",
        verification_mode=VerificationMode.PRELIMINARY_KNOWLEDGE,
        gemini_service=service,
    )

    assert mode == VerificationMode.PRELIMINARY_KNOWLEDGE.value
    assert len(reports) == 1
    report = reports[0]
    assert report.is_preliminary_ai_only is True
    assert report.sources == []
    assert report.source_comparison.rows == []
    assert report.label == VerificationLabel.UNVERIFIED
    assert "AI-GENERATED PRELIMINARY ANALYSIS" in export_report_markdown(report)


def test_missing_source_evidence_returns_unverified_without_calling_gemini() -> None:
    mock_client = MagicMock()
    service = GeminiFactCheckService(api_key="test-key", client=mock_client)

    _, _, reports = run_verification_pipeline(
        "Water boils at 100 degrees Celsius.",
        verification_mode=VerificationMode.MANUAL_SOURCE,
        manual_entries=[],
        gemini_service=service,
    )
    assert len(reports) == 1
    assert reports[0].label == VerificationLabel.UNVERIFIED
    mock_client.models.generate_content.assert_not_called()
