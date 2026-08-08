# ControlGap : Regulatory-Change → Control-Gap Mapper

ControlGap takes the text of a public regulatory standard and a set of internal
controls/SOPs, maps each **requirement** to the relevant **control(s)**, assesses
coverage, and produces a reviewable, exportable **gap register**. The gap register
is the product — this is a decision-support tool for a GRC analyst, **not** a
chatbot.

> **Disclaimer.** Decision-support only - **not legal or compliance advice**. The
> bundled control library is **synthetic**. Every AI/stub proposal requires human
> validation before any reliance. Standard requirement text bundled here is an
> original paraphrase for demonstration, not the authoritative normative wording.

---

## What it does

- Loads a **standard** (default: a 25-item subset of **WCAG 2.2** success criteria;
  alternative: a 10-article **GDPR** subset) and a library of **~21 synthetic
  internal controls** for a fictional mid-size SaaS company.
- Runs a small **RAG pipeline**: parse → chunk by clause/control boundary → embed
  locally → retrieve top-k candidate controls per requirement → assess coverage
  with an LLM (or a deterministic stub).
- Emits a **gap register** where every row has: requirement id/summary, mapped
  control id(s), coverage status `{Met | Partial | Gap | N/A}`, confidence
  (0–1 plus Low/Med/High), grounded rationale that **quotes the exact control text**,
  severity, recommended remediation, review status
  `{AI-proposed | Accepted | Edited | Rejected}`, and a reviewer note.
- Lets the analyst **Accept / Edit / Reject** each row. Exports (CSV + XLSX)
  reflect the reviewed state and **flag any unreviewed rows**.

---

## Honest scope & limitations

This is a **proof of concept**, and the honest limitations matter more than the
feature list:

1. **Control data is synthetic.** `backend/data/controls.json` is fabricated to
   make the register non-trivial (some requirements fully covered, some partial,
   some with no control at all). Do not treat it as a real control library.
2. **Requirement text is paraphrased.** The WCAG/GDPR `text` fields are original
   concise summaries written for this PoC, so the tool ships without copying
   normative text. SC/article **identifiers, titles, and levels are factual**;
   the prose is not authoritative. Consult the official sources
   ([WCAG 2.2](https://www.w3.org/TR/WCAG22/),
   [GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj)) for real wording.
3. **The default runtime path is the weakest one.** With no API key and no model
   download, ControlGap runs the **stub assessor** (keyword heuristic) over the
   **TF-IDF fallback** retriever. This is deliberately labeled everywhere so a
   reviewer is never misled — but it is not the intended production quality. See
   the eval numbers below for exactly how it performs on the labeled set.
4. **No multi-document diffing / "regulatory change" over time.** The name frames
   the intended use (map a regulation to controls); this PoC maps a *current*
   standard snapshot. Comparing two versions of a regulation is future work.
5. **Small scale.** One user, local files + SQLite, no auth, ~20–25 requirements,
   ~21 controls. Retrieval and prompting are not tuned for thousands of controls.
6. **Not a compliance determination.** A "Met" row means a control's text appears
   to address a requirement's text — not that the control operates effectively or
   that an auditor would accept it.

---

## Architecture

```
                 backend/ (Python + FastAPI)
  data/*.json ──▶ parsing ──▶ chunking ──▶ embeddings ──▶ retrieval ──▶ assessor ──▶ grounding ──▶ gap rows ──▶ SQLite
  (requirements  (typed      (one chunk    (local ST      (top-k        (LLM or      (verify every         (persisted,
   + synthetic    records,    per clause/   model, else    candidates    stub, reasons  cited quote is        reviewable)
   controls)      stable IDs) control)      TF-IDF)        per req)       ONLY over      a real substring)
                                                                          retrieved)
                                                              │
                 frontend/ (React + Vite) ◀──── REST /api ───┘
                 audit-workbench UI: register table (hero) + split pane
                 (requirement clause | candidates + assessment), review, export
```

**Pipeline steps (as required):**
1. **Parse** requirements and controls into typed records with stable IDs
   (`parsing.py`).
2. **Chunk by boundary**  one chunk per requirement clause / per control, **not**
   fixed-size windows (`chunking.py`). The natural unit of meaning in compliance
   mapping is a single clause; splitting it would break citation traceability.
3. **Embed locally** with `sentence-transformers` (default `all-MiniLM-L6-v2`),
   so retrieval needs no API key. Automatic **TF-IDF fallback** if the model can't
   load (`embeddings.py`).
4. **Retrieve** the top-k candidate controls per requirement by cosine similarity
   (`retrieval.py`).
5. **Assess** each requirement against **only its retrieved candidates** with an
   LLM (Anthropic or OpenAI, key via env) or a deterministic **stub**
   (`assessor.py`). The model never sees whole documents only retrieved text.

**Grounding guarantee.** After assessment, `verify_grounding()` checks that every
cited `control_quote` is an **exact substring** of a retrieved candidate. Quotes
that fail are dropped, confidence is reduced, and a positive claim that loses all
its control evidence is **demoted to Gap**. This holds for the LLM path too — the
model cannot smuggle in a fabricated citation.

---

## Setup & run

### 1) Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# (optional) real neural embeddings — large download (PyTorch + model weights):
# pip install -r requirements-embeddings.txt

# (optional) real LLM assessment — copy the env template and add a key:
# cp ../.env.example ../.env   and fill in ANTHROPIC_API_KEY or OPENAI_API_KEY

python seed.py                 # builds a gap register for each bundled standard
uvicorn app.main:app --reload --port 8000
```

`seed.py` prints which assessor and embedder are active, e.g.:

```
[seed] standard=wcag22 run_id=wcag22-xxxxxxxx
       assessor = stub (stub=True)
       embedder = tfidf (fallback=True)
```

Load the `.env` automatically by running uvicorn with
`--env-file ../.env`, or export the variables in your shell.

### 2) Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api to :8000)
```

Open http://localhost:5173. Pick a standard, click **Run analysis**, select a
requirement row to open the split-pane working view, review rows, and export.

### Run the evaluation

```bash
cd backend && source .venv/bin/activate
python -m app.eval        # prints real metrics for the active configuration
```

or click **Eval** in the UI.

---

## How the mapping works, and where it fails

**How it works.** For each requirement we retrieve the few most similar controls,
then decide coverage. The stub decides using lexical keyword overlap between the
requirement and each candidate, plus detection of "partial-coverage" language in
the control text (e.g. *best-effort*, *not yet*, *recommends but does not require*,
*out of scope*). The LLM path instead reads the requirement and the same
candidates and returns a structured judgment. Either way, the decision is
**grounded**: the row quotes the exact control sentence it relied on, shown
highlighted in the UI on both the requirement and control side.

**Where it fails (observed, not hypothetical):**

- **Lexical retrieval misses paraphrases.** With the TF-IDF fallback, a control
  that covers a requirement using different vocabulary can score low. Turning on
  the neural embedder improves this; the stub still can't reason.
- **The stub confuses scoped disclaimers.** Example from the bundled data: control
  `ACC-04` fully satisfies *1.4.3 Contrast (Minimum)* but its text also says it
  covers text contrast *"only"* and that non-text contrast is *"not yet defined
  here"*. The stub sees the partial-language cue and marks *1.4.3* **Partial**
  instead of **Met**. This is a real limitation of keyword heuristics; an LLM
  handles it better.
- **The stub is conservative by design.** It would rather flag **Partial/Gap**
  (forcing review) than over-claim **Met**. On the labeled set it catches every
  real gap (recall 1.0) at the cost of a few false gap flags.

We did **not** tune the stub thresholds to the eval set to inflate the numbers —
that would overfit a 25-item set and misrepresent quality.

---

## Evaluation : real numbers (no invented figures)

A small **hand-labeled** ground-truth set (`backend/data/eval_labels.json`) maps
each WCAG requirement to its expected coverage status against the synthetic
controls. `app/eval.py` runs the **currently-configured** assessor + retriever
against it and reports what actually happens. If you configure an LLM key and/or
the neural embedder, re-run to measure that configuration.

**Latest measured run : stub assessor + TF-IDF fallback (the no-key default):**

| Metric | Value |
| --- | --- |
| Sample size (hand-labeled) | **25** |
| 3-way status accuracy (Met/Partial/Gap) | **0.68** (17/25) |
| Gap detection — precision | **0.786** |
| Gap detection — recall | **1.00** |
| Gap detection — F1 | **0.88** |
| Gap-detection confusion (Gap = positive) | tp 11 · fp 3 · fn 0 · tn 11 |
| Retrieval recall@4 | **1.00** (14/14 expected controls retrieved) |

Read this honestly: retrieval reliably surfaces the right control as a *candidate*
(recall@4 = 1.0), and gap detection never misses a real gap on this set (recall
1.0) but raises 3 false gap flags; the 3-way status call is right about two-thirds
of the time on the stub path. The eval is small — treat it as indicative, not a
guarantee. Numbers were produced by the pipeline on this machine, not asserted.

---

## Repository layout

```
controlgap/
├── README.md
├── .env.example
├── run.sh                      # convenience: set up + seed + start backend
├── backend/
│   ├── requirements.txt        # core (runs with stub + TF-IDF, no key/model)
│   ├── requirements-embeddings.txt  # optional neural embedder
│   ├── seed.py                 # build registers out of the box
│   ├── app/
│   │   ├── models.py           # typed records + coverage vocabulary
│   │   ├── parsing.py          # (1) parse to records with stable IDs
│   │   ├── chunking.py         # (2) chunk by clause/control boundary
│   │   ├── embeddings.py       # (3) local embeddings + TF-IDF fallback
│   │   ├── retrieval.py        # (4) top-k retrieval
│   │   ├── assessor.py         # (5) LLM + stub + grounding verification
│   │   ├── pipeline.py         # orchestration
│   │   ├── db.py               # SQLite persistence (runs + reviewable rows)
│   │   ├── export.py           # CSV + XLSX (flags unreviewed rows)
│   │   ├── eval.py             # hand-labeled eval, real numbers
│   │   └── main.py             # FastAPI endpoints
│   ├── data/
│   │   ├── wcag22.json         # requirements (paraphrased text, factual IDs)
│   │   ├── gdpr_subset.json    # alternative standard
│   │   ├── controls.json       # SYNTHETIC controls, mixed coverage
│   │   └── eval_labels.json    # hand-labeled ground truth
│   └── tests/test_pipeline.py  # traceability invariants (pytest)
└── frontend/
    ├── index.html
    ├── vite.config.js          # proxies /api → :8000
    └── src/
        ├── App.jsx             # toolbar, provenance badges, layout
        ├── api.js
        ├── styles.css          # audit-workbench design system
        └── components/         # RegisterTable, DetailPane, Primitives, EvalDialog
```

## License / data notes

Code is provided as-is for demonstration. WCAG is a W3C Recommendation and GDPR is
EU law; only factual identifiers/titles are referenced here, with original
paraphrased summaries. The control library is entirely synthetic.
