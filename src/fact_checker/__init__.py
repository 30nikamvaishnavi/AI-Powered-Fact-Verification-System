"""AI-Powered Fact Verification System core package."""

from .claim_parser import ClaimValidationError, parse_claims
from .database import DatabaseError, VerificationDatabase
from .evidence_extractor import extract_candidate_statements
from .models import (
    ComparisonSummary,
    EvidencePosition,
    EvidenceSnippet,
    ManualEvidenceInput,
    ParsedClaim,
    RetrievalStatus,
    RetrievedSource,
    ScoredEvidence,
    SearchResult,
    SourceComparisonRow,
    VerificationHistorySummary,
    VerificationLabel,
    VerificationReport,
)
from .relevance_analyzer import score_evidence_relevance
from .report_generator import (
    export_report_csv,
    export_report_json,
    export_report_markdown,
    export_reports_csv,
    export_reports_json,
    generate_verification_report,
    run_verification_pipeline,
    save_report_to_exports,
)
from .search_provider import (
    NullSearchProvider,
    SearchProvider,
    SearchProviderError,
    SerperSearchProvider,
    TavilySearchProvider,
    get_search_provider,
)
from .source_comparator import build_source_comparison
from .source_retriever import (
    build_manual_source,
    retrieve_source_from_url,
    retrieve_sources_from_search_results,
    validate_public_url,
)
from .verification_engine import verify_claim_from_evidence

__version__ = "1.0.0"

__all__ = [
    "ClaimValidationError",
    "ComparisonSummary",
    "DatabaseError",
    "EvidencePosition",
    "EvidenceSnippet",
    "ManualEvidenceInput",
    "NullSearchProvider",
    "ParsedClaim",
    "RetrievalStatus",
    "RetrievedSource",
    "ScoredEvidence",
    "SearchProvider",
    "SearchProviderError",
    "SearchResult",
    "SerperSearchProvider",
    "SourceComparisonRow",
    "TavilySearchProvider",
    "VerificationDatabase",
    "VerificationHistorySummary",
    "VerificationLabel",
    "VerificationReport",
    "__version__",
    "build_manual_source",
    "build_source_comparison",
    "export_report_csv",
    "export_report_json",
    "export_report_markdown",
    "export_reports_csv",
    "export_reports_json",
    "extract_candidate_statements",
    "generate_verification_report",
    "get_search_provider",
    "parse_claims",
    "retrieve_source_from_url",
    "retrieve_sources_from_search_results",
    "run_verification_pipeline",
    "save_report_to_exports",
    "score_evidence_relevance",
    "validate_public_url",
    "verify_claim_from_evidence",
]
