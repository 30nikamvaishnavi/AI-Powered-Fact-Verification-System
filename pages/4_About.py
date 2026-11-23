"""About & Methodology page explaining Gemini integration, verification rules, and limitations."""

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
    "The **AI-Powered Fact Verification System** pairs **Google Gemini** (`google-genai`) with "
    "strict Pydantic schema validation, transparent TF-IDF relevance scoring, and conservative "
    "evidence-grounding safeguards."
)

st.subheader("Verification Modes")
st.markdown(
    """
- **Mode A — Manual Source Verification**: Users supply source URLs and excerpts (or enable safe
  public webpage extraction). Gemini compares the claim strictly against the provided evidence,
  identifies supporting/contradicting excerpts, highlights unsupported statements, and flags
  disagreements.
- **Mode B — Gemini Knowledge-Based Preliminary Analysis**: Uses Gemini's internal training
  knowledge for an initial screening when external sources have not been collected yet. Results
  are prominently marked **AI-GENERATED PRELIMINARY ANALYSIS** and never claim that live sources
  or URLs were checked.
"""
)

st.subheader("Primary Verification Labels")
st.markdown(
    """
- **SUPPORTED**: Provided evidence supports the claim with no contradicting evidence found.
- **CONTRADICTED**: Provided evidence directly conflicts with the claim.
- **UNVERIFIED**: Evidence is insufficient, inconclusive, inaccessible, or sources disagree.
  When sources conflict, the system flags the disagreement rather than forcing a verdict.
"""
)

st.subheader("Anti-Fabrication & Security Safeguards")
st.markdown(
    """
- **No invented citations or URLs**: Gemini is strictly prohibited from inventing URLs, dates,
  or source excerpts. Excerpts returned in Mode A are cross-checked against actual source text.
- **Text similarity is not proof**: Topical TF-IDF similarity ranks candidate excerpts, never
  proving factual truth on its own.
- **Respectful HTTP retrieval**: Blocks private/loopback IPs, enforces timeouts, strips HTML
  scripts, treats webpage text as untrusted data, and discloses HTTP 401/403/429 blocks rather
  than bypassing them.
- **Secret protection**: `GEMINI_API_KEY` is read solely from environment variables (`.env`) and
  never exposed in logs, reports, or UI fields.
"""
)

st.subheader("Known Limitations")
st.markdown(
    """
- Gemini is not a live search engine; Mode B preliminary analyses reflect pre-training knowledge
  and may miss recent developments or niche primary records.
- Paywalled or JavaScript-only webpages cannot be read automatically unless you paste the
  relevant excerpt manually in Mode A.
- Automated verification assists human judgment and should not replace domain-expert review for
  high-stakes medical, legal, financial, or safety decisions.
"""
)
