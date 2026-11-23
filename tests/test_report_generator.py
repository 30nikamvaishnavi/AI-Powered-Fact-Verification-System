"""Integration tests for report generation, pipeline execution, and exports."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fact_checker.models import ManualEvidenceInput, SearchResult, VerificationLabel
from fact_checker.report_generator import (
    export_report_csv,
    export_report_json,
    export_report_markdown,
    run_verification_pipeline,
    save_report_to_exports,
)
from fact_checker.search_provider import NullSearchProvider, SearchProvider


class _MockSearchProvider(SearchProvider):
    name = "mock-api"

    def is_configured(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Mock Chemistry Reference",
                url="https://chem.example.org/boiling",
                publisher="chem.example.org",
                publication_date="2024-09-01",
                snippet="Water boils at 100 degrees Celsius at standard atmospheric pressure.",
                provider=self.name,
            )
        ]


def test_pipeline_without_api_key_uses_manual_evidence_and_exports(tmp_path: Path) -> None:
    manual = [
        ManualEvidenceInput(
            title="Physics Reference",
            url="https://physics.example.org/water",
            text="At standard atmospheric pressure, pure water boils at 100 degrees Celsius.",
            publication_date="2024-01-15",
        )
    ]

    session_id, mode, reports = run_verification_pipeline(
        "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
        search_provider=NullSearchProvider(),
        manual_entries=manual,
    )
    assert session_id.startswith("sess-")
    assert mode == "Manual Evidence Mode"
    assert len(reports) == 1

    report = reports[0]
    assert report.label == VerificationLabel.SUPPORTED

    # JSON export
    json_payload = json.loads(export_report_json(report))
    assert json_payload["label"] == "SUPPORTED"
    assert json_payload["claim"] == report.claim

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


def test_pipeline_with_mocked_search_provider_and_http_retrieval() -> None:
    mock_html = (
        "<html><head><title>Boiling Point</title></head>"
        "<body><article><p>Pure water boils at 100 degrees Celsius at standard atmospheric pressure.</p>"
        "</article></body></html>"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.encoding = "utf-8"
    mock_resp.content = mock_html.encode("utf-8")

    with patch("fact_checker.source_retriever.requests.get", return_value=mock_resp):
        _, mode, reports = run_verification_pipeline(
            "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
            search_provider=_MockSearchProvider(),
        )

    assert mode == "Search API (mock-api)"
    assert len(reports) == 1
    assert reports[0].label == VerificationLabel.SUPPORTED
    assert reports[0].sources[0].url == "https://chem.example.org/boiling"
