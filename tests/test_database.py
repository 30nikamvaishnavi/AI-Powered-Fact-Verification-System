"""Unit and integration tests for SQLite verification history storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fact_checker.database import DatabaseError, VerificationDatabase
from fact_checker.models import ManualEvidenceInput, VerificationLabel
from fact_checker.report_generator import run_verification_pipeline


def test_database_saves_lists_filters_retrieves_and_deletes(tmp_path: Path) -> None:
    db_file = tmp_path / "history.db"
    db = VerificationDatabase(db_file)
    db.init_db()
    assert db_file.exists()

    manual = [
        ManualEvidenceInput(
            title="Reference",
            url="https://example.org/ref",
            text="Water boils at 100 degrees Celsius at standard pressure.",
        )
    ]
    session_id, mode, reports = run_verification_pipeline(
        "Water boils at 100 degrees Celsius at standard pressure.",
        manual_entries=manual,
    )
    db.save_session_and_reports(
        session_id=session_id,
        raw_input="Water boils at 100 degrees Celsius at standard pressure.",
        search_mode=mode,
        reports=reports,
    )

    stats = db.get_stats()
    assert stats["total"] == 1
    assert stats["SUPPORTED"] == 1

    listed = db.list_reports(label_filter=VerificationLabel.SUPPORTED, search_query="boils")
    assert len(listed) == 1
    report_id = listed[0].report_id

    loaded = db.get_report(report_id)
    assert loaded is not None
    assert loaded.claim == reports[0].claim
    assert loaded.label == VerificationLabel.SUPPORTED

    assert db.delete_report(report_id) is True
    assert db.get_report(report_id) is None
    assert db.delete_report(report_id) is False


def test_database_handles_corrupted_report_json_gracefully(tmp_path: Path) -> None:
    db_file = tmp_path / "bad.db"
    db = VerificationDatabase(db_file)
    db.init_db()

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO verification_sessions VALUES ('s1', '2026-01-01T00:00:00Z', 'manual', 1, 'x')"
        )
        conn.execute(
            """
            INSERT INTO verification_reports VALUES (
                'bad-rep', 's1', 'Test claim', 'SUPPORTED', 0.5, 0,
                '2026-01-01T00:00:00Z', 'manual', 0, '{not-valid-json', '2026-01-01T00:00:00Z'
            )
            """
        )

    with pytest.raises(DatabaseError, match="corrupted"):
        db.get_report("bad-rep")
