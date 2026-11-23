/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { CheckCircle2, FileText, ShieldCheck, Sparkles } from 'lucide-react';

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center p-6">
      <div className="max-w-3xl w-full bg-white border border-slate-200 rounded-2xl shadow-sm p-8 space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              AI-Powered Fact Verification System
            </h1>
            <p className="text-sm text-slate-600">
              Python 3.13, Streamlit &amp; Google Gemini (google-genai)
            </p>
          </div>
        </div>

        <p className="text-slate-700 leading-relaxed">
          This repository implements a modular Python &amp; Streamlit fact verification system
          powered by Google Gemini via Google AI Studio (<code>GEMINI_API_KEY</code>) with
          Pydantic structured outputs, safe BeautifulSoup4 retrieval, scikit-learn TF-IDF relevance
          scoring, SQLite history, and JSON/CSV/Markdown exports.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              Mode A: Source Check
            </div>
            <p className="text-slate-600">
              Compares claims strictly against user-supplied URLs and excerpts without inventing
              citations.
            </p>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <Sparkles className="w-4 h-4 text-sky-600" />
              Mode B: Preliminary AI
            </div>
            <p className="text-slate-600">
              Knowledge-based initial screening clearly labeled as AI-generated preliminary
              analysis.
            </p>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <FileText className="w-4 h-4 text-blue-600" />
              Reports &amp; History
            </div>
            <p className="text-slate-600">
              Exports JSON, CSV, and Markdown reports and stores sessions in SQLite.
            </p>
          </div>
        </div>

        <div className="rounded-xl bg-slate-900 text-slate-100 p-4 font-mono text-xs space-y-1.5 overflow-x-auto">
          <div className="text-slate-400"># Launch the Streamlit app locally</div>
          <div>python3 -m venv .venv &amp;&amp; source .venv/bin/activate</div>
          <div>pip install -r requirements.txt</div>
          <div>cp .env.example .env  # add GEMINI_API_KEY</div>
          <div>streamlit run app.py</div>
          <div className="text-slate-400 pt-2"># Run tests and Ruff quality checks</div>
          <div>pytest &amp;&amp; ruff check .</div>
        </div>
      </div>
    </div>
  );
}
