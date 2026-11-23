"""About & Methodology page explaining verification rules, safety, and limitations."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fact_checker.ui_helpers import init_app_environment, inject_custom_css  # noqa: E402

init_app_environment()

st.set_page_config(
    page_title="About & Methodology | Fact Verification System",
    page_icon="📘",
    layout="wide",
)
inject_custom_css()

st.title("About & Verification Methodology")
st.markdown(
    "The **AI-Powered Fact Verification System** is designed to promote transparent, "
    "evidence-backed claim checking without fabricating citations or overstating certainty."
)

st.subheader("Primary Verification Labels")
st.markdown(
    """
- **SUPPORTED**: Accessible evidence statements align with the claim's key terms, polarity, and
  numeric/date values, with no contradicting evidence found.
- **CONTRADICTED**: Accessible evidence directly conflicts with the claim via explicit refutation
  cues, negation mismatch, antonym conflicts, or numeric/date discrepancies.
- **UNVERIFIED**: Evidence is missing, inaccessible, ambiguous, or sources directly disagree.
  When sources conflict, the system flags the disagreement instead of forcing a verdict.
"""
)

st.subheader("Why Text Similarity Is Not Proof")
st.info(
    "A statement like 'The Earth is flat' and 'The Earth is not flat' share almost the exact same "
    "keywords and therefore receive a high TF-IDF cosine similarity score. This system separates "
    "**topical relevance scoring** (TF-IDF + keyword overlap) from **stance analysis** (polarity, "
    "refutations, antonyms, and numeric checks) so similar wording never counts as automatic proof."
)

st.subheader("Source Credibility vs. Evidence Relevance")
st.write(
    "Publisher domains are displayed for attribution and comparison only. The system never assumes "
    "a source is authoritative solely because of its domain name, and users are encouraged to inspect "
    "primary references and publication dates directly."
)

st.subheader("Reliability, Privacy & Security Safeguards")
st.markdown(
    """
- **No fabricated citations**: Every excerpt, URL, and publication date comes directly from a
  retrieved webpage, configured search API response, or user-supplied input.
- **Respectful HTTP retrieval**: Enforces strict URL validation (blocking local/private IPs),
  timeouts, and byte caps; HTTP 401/403/429/451 restrictions are disclosed rather than bypassed.
- **Untrusted webpage handling**: Retrieved HTML is stripped of scripts/navigation and treated
  strictly as passive text—never as executable code or instructions.
- **Zero-key resilience**: Works cleanly in Manual Evidence Mode when no search API key is set,
  and never exposes API keys in logs or UI messages.
"""
)

st.subheader("Known Limitations")
st.markdown(
    """
- Rule-based and TF-IDF stance checks may mark complex, multi-hop, or heavily paraphrased claims
  as `UNVERIFIED` rather than risking a false positive.
- Dynamic JavaScript-rendered websites cannot be read without a search snippet or manual text entry.
- Automated verification assists human judgment and should not replace domain-expert review for
  high-stakes medical, legal, or financial decisions.
"""
)
