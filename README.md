# AI-Powered Fact Verification System

## 1. Project Overview

The **AI-Powered Fact Verification System** is a modular Python 3.13 and Streamlit web application powered by **Google Gemini** via the official `google-genai` Python SDK. It helps users analyze factual claims transparently without external search API keys (no Tavily or Serper keys required), compare multiple user-supplied sources side by side, highlight unsupported statements, flag conflicting evidence, store history in SQLite, and export structured JSON, CSV, and Markdown reports.

---

## 2. Features

- **Zero External Search API Keys Required**: Works completely without Tavily or Serper API keys.
- **Google Gemini Integration (`google-genai`)**: Uses structured JSON outputs validated against Pydantic v2 schemas for claim splitting, source-grounded comparison, and preliminary analysis.
- **Two Distinct Verification Modes**:
  - **Mode A — Manual Source Verification**: Compares a claim strictly against user-supplied URLs and evidence excerpts (plus optional safe public webpage fetching).
  - **Mode B — Gemini Knowledge-Based Preliminary Analysis**: Provides an AI-generated initial screening clearly marked as preliminary model knowledge—never presented as live source verification.
- **Anti-Fabrication Safeguards**: Prohibits Gemini from inventing sources, URLs, citations, publication dates, or excerpts; cross-checks Mode A excerpts against actual source text.
- **Respectful Public Webpage Retrieval**: Validates URLs (blocking private/loopback IPs), strips scripts/navigation with BeautifulSoup4, respects HTTP 401/403/429/451 restrictions, and discloses inaccessible pages cleanly.
- **Transparent Relevance & Conflict Detection**: Combines scikit-learn TF-IDF cosine similarity with keyword overlap and conservative conflict rules—automatically flagging disagreements as `UNVERIFIED` rather than forcing a verdict.
- **SQLite Verification History & Exports**: Persists reports locally in `data/fact_verification.db` and exports **JSON**, **CSV**, and **Markdown** reports.

---

## 3. Architecture

```mermaid
flowchart TD
    A[User Enters Claim(s)] --> B[Claim Parser & Optional Gemini Claim Splitter]
    B --> C{Verification Mode}
    C -- Mode A: Manual Source Verification --> D[User Source URLs & Excerpts / Safe Web Fetch]
    D --> E[Evidence Extractor & TF-IDF Relevance Analyzer]
    E --> F[Gemini Service: Compare Claim vs. Provided Sources]
    F --> G[Verification Engine: Ground Excerpts & Flag Disagreements]
    G --> H[Multi-Source Comparator]
    C -- Mode B: Preliminary Analysis --> I[Gemini Service: Model-Knowledge Screening]
    I --> J[Preliminary Payload + Prominent Non-Live Disclaimer]
    H --> K[Structured Verification Report]
    J --> K
    K --> L[(SQLite: data/fact_verification.db)]
    K --> M[JSON / CSV / Markdown Exports]
```

### Project Structure

```text
ai-fact-verification-system/
├── app.py                              # Streamlit Home Dashboard
├── requirements.txt                    # Python dependencies (incl. google-genai)
├── pyproject.toml                      # Pytest and Ruff configuration
├── README.md                           # Project documentation
├── .env.example                        # Environment template
├── .gitignore                          # Git ignore rules (.env excluded)
├── data/
│   └── .gitkeep                        # SQLite database directory
├── exports/
│   └── .gitkeep                        # Exported reports directory
├── pages/
│   ├── 1_Verify_Claims.py              # Claim input, Mode A / Mode B, & reports
│   ├── 2_Source_Comparison.py          # Side-by-side multi-source comparison
│   ├── 3_Verification_History.py       # SQLite history browser & manager
│   └── 4_About.py                      # Methodology & responsible-use guide
├── src/
│   └── fact_checker/
│       ├── __init__.py
│       ├── models.py                   # Pydantic v2 schemas & enums
│       ├── gemini_service.py           # Dedicated Google Gemini (google-genai) client
│       ├── claim_parser.py             # Claim validation & splitting
│       ├── source_retriever.py         # Safe URL checks & BeautifulSoup4 retrieval
│       ├── evidence_extractor.py       # Candidate statement extraction
│       ├── relevance_analyzer.py       # TF-IDF + keyword overlap relevance scoring
│       ├── verification_engine.py      # Grounded reconciliation & conservative verdicts
│       ├── source_comparator.py        # Multi-source comparison builder
│       ├── report_generator.py         # Pipeline orchestrator & JSON/CSV/MD exports
│       ├── database.py                 # SQLite history persistence
│       └── ui_helpers.py               # Shared Streamlit components
└── tests/
    ├── test_claim_parser.py
    ├── test_database.py
    ├── test_gemini_service.py
    ├── test_relevance_analyzer.py
    ├── test_report_generator.py
    ├── test_source_comparator.py
    └── test_verification_engine.py
```

---

## 4. How Gemini Works in the Application

All Gemini calls are isolated inside `src/fact_checker/gemini_service.py` using the official `google-genai` SDK (`from google import genai`) and Pydantic `response_schema` structured outputs:

1. **Claim Decomposition (Optional)**: Breaks long multi-sentence paragraphs into concise, self-contained factual claims while preserving numbers and entities.
2. **Mode A Source Comparison**: Receives only the user-supplied and successfully retrieved source texts (tagged by `source_id`) and returns per-source assessments (`Supports`, `Contradicts`, `Unclear`), quoted excerpts, unsupported statements, and disagreement notes. `verification_engine.py` then validates every `source_id` and excerpt against the real sources and forces `UNVERIFIED` whenever sources conflict.
3. **Mode B Preliminary Analysis**: Evaluates a claim using Gemini's pre-trained knowledge when no sources are attached, returning preliminary supporting/contradicting considerations and open questions while forbidding fabricated URLs or citations.

---

## 5. How to Create a Google AI Studio API Key

1. Visit **Google AI Studio**: <https://aistudio.google.com/>
2. Sign in with your Google account.
3. Click **Get API key** (or **Create API key** in the API Keys panel).
4. Select or create a Google Cloud project and copy the generated key.
5. Keep the key private—place it only in your local `.env` file (which is ignored by `.gitignore`) and never hardcode it into Python files.

---

## 6. Installation Instructions

Ensure **Python 3.13** (or 3.11+) is installed:

```bash
python3 --version
```

### Create and Activate a Virtual Environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 7. Environment Variable Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

*(Windows PowerShell: `Copy-Item .env.example .env`)*

Edit `.env` with your Google AI Studio key:

```env
GEMINI_API_KEY=your_google_ai_studio_api_key
GEMINI_MODEL=gemini-2.5-flash

REQUEST_TIMEOUT_SECONDS=15
DATABASE_PATH=data/fact_verification.db
EXPORTS_DIR=exports
```

| Variable | Default | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | *(required for Gemini calls)* | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model used for analysis |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Timeout for Gemini requests and public webpage fetches |
| `DATABASE_PATH` | `data/fact_verification.db` | Local SQLite database path |
| `EXPORTS_DIR` | `exports` | Output folder when saving exports to disk |

---

## 8. How to Run the Streamlit Application

```bash
streamlit run app.py
```

Open the local URL shown in your terminal (typically `http://localhost:8501`).

---

## 9. Verification Modes

### Mode A: Manual Source Verification
1. Open **Verify Claims** and keep **Manual Source Verification** selected.
2. Enter one or more factual claims (or load a sample scenario).
3. Add one or more source URLs and paste their relevant text/excerpts (or enable automatic fetching of publicly accessible webpages).
4. Click **Run Gemini Analysis**.
5. Gemini compares your claim strictly against the submitted sources, flags any disagreements, highlights unsupported parts, and builds a side-by-side comparison table with clickable URLs.

### Mode B: Gemini Knowledge-Based Preliminary Analysis
1. Select **Gemini Knowledge-Based Preliminary Analysis**.
2. Review the prominent warning banner: **Gemini preliminary analysis is NOT live fact verification**.
3. Click **Run Gemini Analysis** to receive an AI-generated initial screening based solely on model knowledge, along with unsupported statements and questions to investigate using primary sources.

---

## 10. Verification Labels

| Label | Meaning |
| --- | --- |
| **SUPPORTED** | Provided evidence supports the claim with no contradicting evidence found. |
| **CONTRADICTED** | Provided evidence directly conflicts with the claim. |
| **UNVERIFIED** | Available evidence is insufficient, inaccessible, inconclusive, or sources disagree. |

When sources disagree, the system explicitly reports the disagreement (`disagreement_flagged = True`) and labels the claim `UNVERIFIED` instead of forcing a verdict.

---

## 11. Testing & Linting Instructions

All tests mock `google.genai.Client` and HTTP requests so they run completely offline without an API key or paid usage:

```bash
pytest
```

Run Ruff code-quality and lint checks:

```bash
ruff check .
```

---

## 12. Limitations and Responsible Use

- **Gemini preliminary analysis is NOT live fact verification**: Mode B relies on Gemini's pre-training knowledge without checking live websites, databases, or recent events. Always verify important claims with authoritative primary sources.
- **No fabricated citations**: Gemini cannot invent URLs, publication dates, or citations. Any URL that cannot be fetched (e.g., HTTP 403/429, timeout, or JavaScript-only pages) is disclosed as inaccessible and excluded from evidence verification.
- **Text similarity is not proof**: TF-IDF similarity ranks topical overlap only; stance and factual consistency are evaluated separately.
- **Decision support only**: Do not rely solely on automated outputs for medical, legal, financial, or safety-critical decisions.
