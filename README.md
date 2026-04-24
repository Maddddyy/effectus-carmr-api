# Effectus CARMR Extraction API

An agentic pipeline that converts board documents into structured **CARMR** governance records using Claude Opus with extended thinking.

Live API: **https://api.effectus.madhvendra.com**  
Interactive docs: **https://api.effectus.madhvendra.com/docs**  
Frontend app: **https://effectus.madhvendra.com**

---

## What it does

You upload one or more board documents (PDF, DOCX, TXT, VTT/SRT transcript). The pipeline analyses them using formal argumentation theory and produces a fully structured **Strategy Commitment Record (SCR)** in the CARMR schema - ready to import directly into the Effectus frontend.

CARMR stands for:

| Letter | Layer | What it captures |
|--------|-------|-----------------|
| **C** | Commitment | The governed organisational commitment - what, why now, scope, outcomes, reversibility |
| **A** | Assumptions | Defeasible premises with falsification conditions - what must remain true |
| **R** | Reasoning | Causal logic (Walton's Practical Reasoning): IF assumptions hold, THEN outcome, BECAUSE mechanism |
| **M** | Meaning | Contested terms whose drift would break falsification conditions (equivocation prevention) |
| **R** | Review | Pre-agreed time-based and event-based triggers for mandatory review |

The output also includes a **Commitment Integrity Score (CIS)** - a structured quality indicator weighted across all five CARMR layers.

---

## Architecture

```
POST /api/jobs          Upload documents → returns job_id
GET  /api/jobs/{id}/stream   SSE stream: real-time pipeline progress
GET  /api/jobs/{id}/status   Poll job status
GET  /api/jobs/{id}/result   Final CARMR record (when complete)
GET  /api/health        Health check
```

### Pipeline stages (8 total)

```
Stage 0 - Ingest        Parse PDF/DOCX/TXT/transcript into clean text
Stage 1 - Pre-Analysis  Map structural argument: claims, grounds, implicit premises
Stage 2 - Commitment    Extract 4-part commitment statement + ownership + reversibility
Stage 3 - Assumptions   2-pass extraction: draft + adversarial QC using 4 argumentation tests
Stage 4 - Reasoning     Walton's Practical Reasoning: THEN/BECAUSE/ELABORATION blocks (max 3)
Stage 5 - Meaning       Equivocation prevention: contested terms in falsification conditions only (max 5)
Stage 6 - Review        Falsification-style governance triggers (max 2 time + 2 event)
Stage 7 - Cross-validation  Structural integrity check + CIS computation
Stage 8 - Synthesis     Final record assembly
```

Each stage uses **extended thinking** (Claude Opus with `thinking: adaptive`, `effort: high`). Stages 2, 3, and 5 include targeted web research via Exa AI.

### Research integration

Research is used at exactly 3 surgical points:

1. **Post-commitment** - validate strategic context, find counter-evidence
2. **Post-assumptions** - adversarially test each parent assumption against current market data
3. **Post-meaning** - find how contested terms are actually defined in industry/regulation

This is intentional. Research everywhere produces noise. Research at these three points sharpens the governance-critical content.

### Assumption quality enforcement

The assumptions stage applies four formal argumentation tests to every draft assumption:

1. **Defeater test** - if this premise were false, does the commitment actually fail?
2. **Independence test** - is this premise logically distinct from every other assumption?
3. **Testability test** - does the falsification condition name a specific metric, threshold, timeframe, and data source?
4. **Atomicity test** - does this assumption test exactly one claim?

Parent-child structure is enforced: max 3 parent assumptions, each may have at most 1 child. Parents always outnumber children. Total cap: 5 assumptions.

---

## Project structure

```
effectus-api/
├── main.py                     FastAPI app, routes, job lifecycle
├── start.sh                    Production start script
├── .env.example                Environment variable template
│
├── jobs/
│   ├── __init__.py
│   └── store.py                In-memory job store with TTL (1 hour)
│
├── models/
│   ├── __init__.py
│   └── carmr_schema.py         Pydantic models matching Effectus frontend schema
│
├── pipeline/
│   ├── __init__.py
│   ├── orchestrator.py         8-stage pipeline, SSE event emission
│   ├── stages.py               Stage implementations (all LLM extraction logic)
│   ├── llm_client.py           Claude Opus wrapper with retry + JSON extraction
│   └── ingest.py               Document parsing: PDF (PyMuPDF), DOCX, TXT, VTT/SRT
│
├── prompts/
│   ├── __init__.py
│   └── carmr_framework.py      Stage system prompts + argumentation theory + reference cases
│
└── research/
    ├── __init__.py
    └── web_research.py         Exa AI neural search (3 targeted research points)
```

---

## Setup

### Requirements

- Python 3.12+
- An Anthropic API key (Claude Opus access required)
- Exa AI API key (optional - research features degrade gracefully without it)

### Install

```bash
git clone https://github.com/Maddddyy/effectus-carmr-api.git
cd effectus-carmr-api

python3 -m venv venv
source venv/bin/activate

pip install fastapi==0.136.0 uvicorn==0.46.0 anthropic==0.96.0 \
    python-dotenv==1.2.2 pydantic==2.13.3 httpx==0.28.1 \
    PyMuPDF==1.27.2.2 python-docx==1.2.0
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPUS_MODEL=claude-opus-4-5
EXA_API_KEY=your-exa-key-here        # optional
ALLOWED_ORIGIN=https://yourapp.com
MAX_UPLOAD_MB=50
```

### Run

```bash
source venv/bin/activate
export PYTHONPATH=/path/to/effectus-carmr-api
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Or use the included start script (production):

```bash
bash start.sh
```

API will be available at `http://localhost:8001`.  
Swagger UI at `http://localhost:8001/docs`.

---

## API reference

### POST /api/jobs

Upload one or more documents. Returns a `job_id` immediately.

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `files` | File[] | One or more documents (PDF, DOCX, TXT, MD, VTT, SRT) |

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "files": ["board_minutes.pdf"],
  "stream_url": "/api/jobs/550e8400.../stream"
}
```

**Limits:** Max 50MB per file (configurable via `MAX_UPLOAD_MB`).

---

### GET /api/jobs/{job_id}/stream

SSE stream delivering real-time pipeline progress. Connect immediately after `POST /api/jobs`.

**Event types:**

| Event | When | Payload |
|-------|------|---------|
| `stage_start` | Stage begins | `stage`, `stage_num`, `total_stages`, `message` |
| `stage_complete` | Stage finishes | `stage`, `quality_score`, `partial_result` |
| `thinking` | LLM reasoning step | `stage`, `message` |
| `quality_check` | QC pass result | `stage`, `quality_score`, `issues`, `passed` |
| `research` | Web research result | `stage`, `query`, `finding`, `status` |
| `complete` | Pipeline done | Full CARMR result (see below) |
| `error` | Pipeline failed | `message`, `job_id` |

**Complete event payload:**

```json
{
  "job_id": "...",
  "carmr": {
    "scrId": "SCR-550E8400",
    "recordData": {
      "title": "...",
      "date": "YYYY-MM-DD",
      "sponsor": "...",
      "owner": "...",
      "statementWhat": "...",
      "statementWhyNow": "...",
      "statementScope": "...",
      "statementOutcomes": "...",
      "reversibility": "full|partial|irreversible",
      "exitCostMin": "...",
      "exitCostMax": "...",
      "portfolio": "...",
      "status": "draft"
    },
    "assumptions": [
      {
        "id": "A1",
        "parentId": null,
        "statement": "...",
        "owner": "...",
        "status": "active|at-risk|failed|superseded",
        "confidence": "high|medium|low|unknown",
        "falsification": "...",
        "dissentingView": ""
      }
    ],
    "reasoningBlocks": [
      {
        "id": "RB1",
        "linkedAssumptions": ["A1", "A2"],
        "then": "...",
        "because": "...",
        "elaboration": "..."
      }
    ],
    "meaningTerms": [
      {
        "id": "M1",
        "term": "...",
        "autoDetected": true,
        "contextQuote": "...",
        "definition": "...",
        "driftRisk": "..."
      }
    ],
    "reviewTriggers": [
      {
        "id": "RT1",
        "type": "time|event",
        "description": "...",
        "nextReviewDue": "YYYY-MM-DD",
        "overdue": false
      }
    ],
    "reviewEvents": []
  },
  "cis": 82.4,
  "cis_breakdown": {
    "C": 90.0,
    "A": 85.0,
    "R": 78.0,
    "M": 70.0,
    "Review": 80.0
  },
  "overall_confidence": 0.84,
  "warnings": [],
  "research_citations": ["Commitment context: ...", "Assumption test: A1"],
  "extracted_from": ["board_minutes.pdf"],
  "processing_time_seconds": 47.2
}
```

---

### GET /api/jobs/{job_id}/status

Poll job status without streaming.

**Response:**

```json
{
  "job_id": "...",
  "status": "queued|running|complete|error",
  "current_stage": "assumptions",
  "progress_pct": 37.5,
  "filenames": ["board_minutes.pdf"]
}
```

---

### GET /api/jobs/{job_id}/result

Get the final CARMR record. Only available when `status == "complete"`.

Returns the same payload as the `complete` SSE event.

Returns HTTP 202 if the job is not yet complete.

---

### GET /api/health

```json
{
  "status": "ok",
  "api_key_configured": true,
  "model": "claude-opus-4-5",
  "allowed_origin": "https://effectus.madhvendra.com"
}
```

---

## Usage example

### curl

```bash
# 1. Upload document
JOB=$(curl -s -X POST https://api.effectus.madhvendra.com/api/jobs \
  -F "files=@board_minutes.pdf" | jq -r .job_id)

echo "Job: $JOB"

# 2. Stream progress (Ctrl-C when done, or wait for 'complete' event)
curl -N "https://api.effectus.madhvendra.com/api/jobs/$JOB/stream"

# 3. Or poll status
curl "https://api.effectus.madhvendra.com/api/jobs/$JOB/status"

# 4. Get result when complete
curl "https://api.effectus.madhvendra.com/api/jobs/$JOB/result"
```

### JavaScript (SSE client)

```javascript
async function extractCARMR(file) {
  // 1. Upload
  const form = new FormData();
  form.append('files', file);

  const { job_id, stream_url } = await fetch('/api/jobs', {
    method: 'POST',
    body: form,
  }).then(r => r.json());

  // 2. Stream progress
  return new Promise((resolve, reject) => {
    const source = new EventSource(`/api/jobs/${job_id}/stream`);

    source.addEventListener('stage_start', e => {
      const { stage, stage_num, total_stages } = JSON.parse(e.data);
      console.log(`[${stage_num}/${total_stages}] ${stage}`);
    });

    source.addEventListener('complete', e => {
      source.close();
      resolve(JSON.parse(e.data));
    });

    source.addEventListener('error', e => {
      source.close();
      reject(new Error(JSON.parse(e.data).message));
    });
  });
}
```

---

## CARMR schema

The output schema matches the Effectus frontend data model exactly (`src/data.js`). A completed CARMR record can be pasted directly into the frontend's extract flow (`/extract` route) to create a new SCR.

### Commitment Integrity Score (CIS)

The CIS is a 0-100 quality indicator computed from structured record data. Weights:

| Layer | Weight | What drives the score |
|-------|--------|----------------------|
| C - Commitment | 15% | All 4 statement fields complete, reversibility documented with exit costs |
| A - Assumptions | 35% | Count (min 3), completeness (statement + owner + falsification + status), confidence rated |
| R - Reasoning | 25% | All assumptions linked, THEN and BECAUSE fields complete, multiple blocks |
| M - Meaning | 10% | Terms complete with operational definition and drift risk |
| Review | 15% | Time and event triggers present, not overdue |

---

## Supported document types

| Format | Parser | Notes |
|--------|--------|-------|
| PDF | PyMuPDF | Extracts text per page with page numbers |
| DOCX / DOC | python-docx | Extracts paragraphs and tables |
| TXT / MD | Native | UTF-8, errors replaced |
| VTT / SRT | Custom regex | Strips timestamps, returns clean transcript |
| Other | UTF-8 fallback | Best-effort text extraction |

Max file size: 50MB (configurable). Max context fed to LLM: 80,000 characters (beginning + end preserved for truncation).

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.136.0 | Web framework |
| uvicorn | 0.46.0 | ASGI server |
| anthropic | 0.96.0 | Claude Opus API client |
| pydantic | 2.13.3 | Schema validation |
| httpx | 0.28.1 | Async HTTP (Exa research calls) |
| PyMuPDF | 1.27.2.2 | PDF text extraction |
| python-docx | 1.2.0 | DOCX text extraction |
| python-dotenv | 1.2.2 | Environment variable loading |

---

## Notes

- **Job storage is in-memory.** Jobs expire after 1 hour. The API is stateless between restarts.
- **One stream connection per job.** The SSE stream can only be consumed once. If you need the result later, use `/api/jobs/{id}/result`.
- **CORS.** The API allows all origins by default. Set `ALLOWED_ORIGIN` in `.env` to restrict.
- **Model.** Defaults to `claude-opus-4-5`. Set `OPUS_MODEL` in `.env` to use a different model. Models `4-6` and `4-7` use adaptive thinking + high effort automatically.
- **Research.** If `EXA_API_KEY` is not set, research steps are silently skipped. Extraction still works - research only improves sharpness of falsification conditions and assumption status flags.

---

## Related

- **Effectus frontend:** https://github.com/Maddddyy/effectus-strategy-governance
- **Live app:** https://effectus.madhvendra.com
- **CARMR framework:** Strategic Validity Management by Brian Mooney / Effectus Research
