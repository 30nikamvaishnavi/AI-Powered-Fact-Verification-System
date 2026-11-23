"""AI-Powered Fact Verification System core package."""

from .claim_parser import ClaimValidationError, parse_claims
from .database import DatabaseError, VerificationDatabase
from .evidence_extractor import extract_candidate_statements
from .gemini_service import (
    GeminiAuthenticationError,
    GeminiFactCheckService,
    GeminiMissingKeyError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiServiceError,
    GeminiTimeoutError,
    get_gemini_model,
    is_gemini_configured,
)
from .models import (
    ComparisonSummary,
    EvidencePosition,
    EvidenceSnippet,
    GeminiClaimSplitResponse,
    GeminiEvidenceVerificationResponse,
    GeminiPreliminaryAnalysisResponse,
    GeminiSourceAssessment,
    ManualEvidenceInput,
    ParsedClaim,
    RetrievalStatus,
    RetrievedSource,
    ScoredEvidence,
    SourceComparisonRow,
    VerificationHistorySummary,
    VerificationLabel,
    VerificationMode,
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
from .source_comparator import build_source_comparison
from .source_retriever import (
    build_manual_source,
    retrieve_source_from_url,
    validate_public_url,
)
from .verification_engine import (
    build_preliminary_verification_payload,
    reconcile_gemini_source_assessment,
    verify_claim_from_evidence,
)

__version__ = "2.0.0"

__all__ = [
    "ClaimValidationError",
    "ComparisonSummary",
    "DatabaseError",
    "EvidencePosition",
    "EvidenceSnippet",
    "GeminiAuthenticationError",
    "GeminiClaimSplitResponse",
    "GeminiEvidenceVerificationResponse",
    "GeminiFactCheckService",
    "GeminiMissingKeyError",
    "GeminiPreliminaryAnalysisResponse",
    "GeminiRateLimitError",
    "GeminiResponseError",
    "GeminiServiceError",
    "GeminiSourceAssessment",
    "GeminiTimeoutError",
    "ManualEvidenceInput",
    "ParsedClaim",
    "RetrievalStatus",
    "RetrievedSource",
    "ScoredEvidence",
    "SourceComparisonRow",
    "VerificationDatabase",
    "VerificationHistorySummary",
    "VerificationLabel",
    "VerificationMode",
    "VerificationReport",
    "__version__",
    "build_manual_source",
    "build_preliminary_verification_payload",
    "build_source_comparison",
    "export_report_csv",
    "export_report_json",
    "export_report_markdown",
    "export_reports_csv",
    "export_reports_json",
    "extract_candidate_statements",
    "generate_verification_report",
    "get_gemini_model",
    "is_gemini_configured",
    "parse_claims",
    "reconcile_gemini_source_assessment",
    "retrieve_source_from_url",
    "run_verification_pipeline",
    "save_report_to_exports",
    "score_evidence_relevance",
    "validate_public_url",
    "verify_claim_from_evidence",
]
