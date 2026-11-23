"""SQLite persistence layer for storing and querying verification history."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from .models import (
    VerificationHistorySummary,
    VerificationLabel,
    VerificationReport,
)
from .source_retriever import utc_now_iso

DEFAULT_DATABASE_PATH = "data/fact_verification.db"


class DatabaseError(RuntimeError):
    """Raised when SQLite storage or retrieval encounters an error."""


class VerificationDatabase:
    """Manages SQLite persistence for verification sessions and reports."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        resolved = db_path or os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
        self.db_path = Path(resolved)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
        except (OSError, sqlite3.Error) as exc:
            raise DatabaseError(f"Unable to open SQLite database at {self.db_path}: {exc}") from exc

        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"SQLite transaction failed: {exc}") from exc
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create required tables and indexes if they do not exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS verification_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    search_mode TEXT NOT NULL,
                    claims_count INTEGER NOT NULL,
                    raw_input TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verification_reports (
                    report_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    disagreement_flagged INTEGER NOT NULL DEFAULT 0,
                    retrieval_timestamp TEXT NOT NULL,
                    search_mode TEXT NOT NULL,
                    source_count INTEGER NOT NULL DEFAULT 0,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES verification_sessions(session_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_reports_created_at
                    ON verification_reports(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_reports_label
                    ON verification_reports(label);
                """
            )

    def save_session_and_reports(
        self,
        *,
        session_id: str,
        raw_input: str,
        search_mode: str,
        reports: list[VerificationReport],
    ) -> None:
        """Persist a verification session and all of its generated reports."""
        self.init_db()
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO verification_sessions (
                    session_id, created_at, search_mode, claims_count, raw_input
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, now, search_mode, len(reports), raw_input),
            )
            for report in reports:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO verification_reports (
                        report_id,
                        session_id,
                        claim,
                        label,
                        confidence_score,
                        disagreement_flagged,
                        retrieval_timestamp,
                        search_mode,
                        source_count,
                        report_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.report_id,
                        session_id,
                        report.claim,
                        report.label.value,
                        float(report.confidence_score),
                        1 if report.disagreement_flagged else 0,
                        report.retrieval_timestamp,
                        report.search_mode,
                        len(report.sources),
                        report.model_dump_json(),
                        now,
                    ),
                )

    def list_reports(
        self,
        *,
        limit: int = 50,
        label_filter: VerificationLabel | str | None = None,
        search_query: str | None = None,
    ) -> list[VerificationHistorySummary]:
        """Return recent verification report summaries ordered newest first."""
        self.init_db()
        clauses: list[str] = []
        params: list[object] = []

        if label_filter and str(label_filter).upper() != "ALL":
            label_val = (
                label_filter.value
                if isinstance(label_filter, VerificationLabel)
                else str(label_filter).upper()
            )
            clauses.append("label = ?")
            params.append(label_val)

        if search_query and search_query.strip():
            clauses.append("LOWER(claim) LIKE ?")
            params.append(f"%{search_query.strip().lower()}%")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT
                report_id,
                session_id,
                claim,
                label,
                confidence_score,
                disagreement_flagged,
                retrieval_timestamp,
                search_mode,
                source_count
            FROM verification_reports
            {where_sql}
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
        """
        params.append(max(1, limit))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        summaries: list[VerificationHistorySummary] = []
        for row in rows:
            summaries.append(
                VerificationHistorySummary(
                    report_id=row["report_id"],
                    session_id=row["session_id"],
                    claim=row["claim"],
                    label=VerificationLabel(row["label"]),
                    confidence_score=float(row["confidence_score"]),
                    disagreement_flagged=bool(row["disagreement_flagged"]),
                    retrieval_timestamp=row["retrieval_timestamp"],
                    search_mode=row["search_mode"],
                    source_count=int(row["source_count"]),
                )
            )
        return summaries

    def get_report(self, report_id: str) -> VerificationReport | None:
        """Load a full VerificationReport by report_id, or return None if missing."""
        self.init_db()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM verification_reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            return VerificationReport.model_validate_json(row["report_json"])
        except ValidationError as exc:
            raise DatabaseError(
                f"Stored verification report '{report_id}' is malformed or corrupted: {exc}"
            ) from exc

    def delete_report(self, report_id: str) -> bool:
        """Delete a verification report by report_id. Returns True if a row was deleted."""
        self.init_db()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM verification_reports WHERE report_id = ?",
                (report_id,),
            )
            return cursor.rowcount > 0

    def get_stats(self) -> dict[str, int]:
        """Return aggregate verification counts by label."""
        self.init_db()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT label, COUNT(*) AS cnt FROM verification_reports GROUP BY label"
            ).fetchall()

        counts = {
            "total": 0,
            VerificationLabel.SUPPORTED.value: 0,
            VerificationLabel.CONTRADICTED.value: 0,
            VerificationLabel.UNVERIFIED.value: 0,
        }
        for row in rows:
            lbl = str(row["label"])
            cnt = int(row["cnt"])
            counts[lbl] = cnt
            counts["total"] += cnt
        return counts
