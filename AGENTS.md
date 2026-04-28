# AGENTS.md — TraceMyClaim

> Authoritative reference for all agents in the TraceMyClaim system. Read this before generating, modifying, or invoking any agent. Every agent's behavior, I/O contract, and intelligence level is fixed here. If a task seems to require deviating from this file, stop and surface the conflict — do not silently change agent contracts.

---

## 1. System Overview

TraceMyClaim is a multi-agent fact-checking pipeline. A user submits a long-form article. The system extracts atomic factual claims, fans out one verifier agent per claim running in parallel via Codex `cloud exec`, and aggregates results into a color-coded credibility report.

**Design principles:**

1. **Atomic units.** Every agent operates on the smallest verifiable unit possible. No agent does two jobs.
2. **Parallel by default.** If N items can be processed independently, they run concurrently. No serial loops over claim lists.
3. **Graceful degradation.** A failed agent never blocks the pipeline. Timeouts return a structured "unknown" verdict, not an exception.
4. **Visible reasoning.** Every agent emits structured JSON. No free-form text outputs except where explicitly noted.
5. **Cost discipline.** Intelligence level is matched to task complexity, not maximized. See per-agent settings below.

---

## 2. Pipeline Topology

```
    [Article Input]
          │
          ▼
   ┌──────────────┐
   │  Extractor   │   1 agent · Extra High
   └──────┬───────┘
          │ claims[] (max 25)
          ▼
   ┌──────────────┐
   │  Verifiers   │   N parallel agents · Medium
   │  (1 per      │   (Codex cloud exec)
   │   claim)     │
   └──────┬───────┘
          │ verdicts[]
          ▼
   ┌──────────────┐
   │ DecisionGraph│   Deterministic (no LLM)
   │   Builder    │
   └──────┬───────┘
          │ graph + weighted scores
          ▼
   ┌──────────────┐
   │ MetaReviewer │   1 agent · Extra High
   └──────┬───────┘
          │ final report
          ▼
      [UI Render]
```

---

## 3. Shared Conventions

### 3.1 Identifiers

* `article_id`: UUID generated at ingestion.
* `claim_id`: `<article_id>::c<index>` where index is 0-padded, e.g. `c01`, `c02`.
* `agent_run_id`: `<claim_id>::r<attempt>` for verifier retries.

### 3.2 JSON Schemas

All inter-agent data lives in `shared/types.ts` (frontend) and `shared/schemas.py` (backend). These two must be kept in sync. If a schema changes, update both files in the same commit.

### 3.3 Error Handling

Every agent returns one of two top-level shapes:

```json
{ "status": "ok", "data": { ... } }
{ "status": "error", "error_code": "TIMEOUT|PARSE|UPSTREAM|UNKNOWN", "message": "..." }
```

Downstream agents must handle both. A pipeline run with errored verifiers is still valid — the Meta-Reviewer treats them as low-confidence "unknown" verdicts.

### 3.4 Logging

Every agent emits a structured log line on start and completion:

```
[<timestamp>] <agent_name> <agent_run_id> <event> <duration_ms> <status>
```

These feed the live agent panel in the UI. Do not use `print()` — use the shared `logger` from `backend/utils/logging.py`.

---

## 4. Agent Specifications

### 4.1 Claim Extractor

**Intelligence:** Extra High
**Concurrency:** 1 (sequential, only runs once per article)
**Timeout:** 60s
**Model:** GPT-5.4

**Purpose:** Convert article text into a ranked list of atomic factual claims suitable for independent verification.

**Input contract:**

```python
{
  "article_id": str,
  "text": str,           # raw article text, max 50,000 chars
  "source_url": str | None
}
```

**Output contract:**

```python
{
  "status": "ok",
  "data": {
    "claims": [
      {
        "claim_id": str,
        "text": str,                    # rewritten as standalone, decontextualized claim
        "original_quote": str,          # exact span from article
        "importance": float,            # 0.0-1.0
        "controversy": float,           # 0.0-1.0
        "topic_tags": list[str]         # e.g. ["economics", "covid"]
      }
    ]
  }
}
```

**Hard rules:**

* Atomic only. "X happened in 2024 because of Y" → two claims.
* Verifiable only. Filter out: opinions, predictions, value judgments, hypotheticals, rhetorical questions.
* Decontextualize. Each claim must stand alone — no "this", "they", "the author" references.
* Cap at 25 claims. If more are found, keep top-25 by `importance`.
* `importance` reflects how central the claim is to the article's thesis.
* `controversy` reflects how likely the claim is to be disputed in mainstream sources.

**Failure modes:**

* If article is < 200 words, return error `INSUFFICIENT_TEXT`.
* If no verifiable claims found, return `data.claims: []` with `status: ok`.

---

### 4.2 Verifier (parallel fan-out)

**Intelligence:** Medium
**Concurrency:** Up to 25 concurrent via Codex `cloud exec`
**Timeout:** 15s per agent (hard ceiling)
**Model:** GPT-5.4
**Tools:** Tavily search (primary), Wikipedia API (secondary)

**Purpose:** Verify a single atomic claim against external sources. One verifier per claim. No verifier ever sees more than its assigned claim.

**Input contract:**

```python
{
  "claim_id": str,
  "claim_text": str,
  "topic_tags": list[str]    # used to bias search queries
}
```

**Output contract:**

```python
{
  "status": "ok",
  "data": {
    "claim_id": str,
    "verdict": "supported" | "contested" | "unsupported",
    "confidence": float,                # 0.0-1.0
    "sources": [
      {
        "url": str,
        "title": str,
        "evidence_quote": str,          # exact text from source, max 200 chars
        "supports": bool                # does this source support or contradict the claim?
      }
    ],                                  # 2-3 sources required
    "reasoning": str                    # 1-2 sentences, max 300 chars
  }
}
```

**Hard rules:**

* Make at most 3 search queries before deciding. No deep recursive research.
* `verdict: supported` requires ≥2 sources where `supports=true` and 0 contradicting.
* `verdict: contested` means sources disagree.
* `verdict: unsupported` means no credible source confirms the claim (this is distinct from "the claim is false" — phrase reasoning carefully).
* Source quality matters: prefer .gov, .edu, established news, Wikipedia. Penalize confidence if only blogs/forums available.
* Quoted evidence must be ≤ 25 words and never reproduce more than one quote per source.
* On timeout, return `status: error, error_code: TIMEOUT` — never partial results.

**Failure modes:**

* Search API failure → `error_code: UPSTREAM`
* Timeout → `error_code: TIMEOUT`
* These are passed through to the Meta-Reviewer as "unknown" verdicts; the pipeline does not halt.

---

### 4.3 Decision Graph Builder

**Intelligence:** N/A — deterministic Python, no LLM call
**Concurrency:** 1
**Timeout:** 5s

**Purpose:** Build a claim graph that captures structural relationships and computes a weighted credibility score. This is the system's differentiator — make sure it is fully visualized in the UI.

**Input:** All extractor output + all verifier outputs.

**Output:**

```python
{
  "nodes": [
    {
      "claim_id": str,
      "verdict": str,
      "confidence": float,
      "importance": float,
      "weight": float            # importance × confidence, used for scoring
    }
  ],
  "edges": [
    {
      "from": claim_id,
      "to": claim_id,
      "type": "depends_on" | "shares_source" | "same_topic"
    }
  ],
  "credibility_score": float,    # 0-100, weighted aggregate
  "top_findings_input": list[claim_id]  # top 3 most consequential, passed to MetaReviewer
}
```

**Edge construction rules:**

* `shares_source`: two claims citing overlapping URLs.
* `same_topic`: claims sharing ≥2 `topic_tags`.
* `depends_on`: lightweight heuristic — if claim B's text contains an entity defined in claim A, draw the edge. Don't over-engineer this; even a simple version reads well in the demo.

**Scoring formula:**

```
credibility_score = 100 × Σ(weight_i × verdict_score_i) / Σ(weight_i)

where verdict_score = {
  supported: 1.0,
  contested: 0.5,
  unsupported: 0.0,
  unknown: 0.3   # errored verifiers
}
```

---

### 4.4 Meta-Reviewer

**Intelligence:** Extra High
**Concurrency:** 1
**Timeout:** 30s
**Model:** GPT-5.4

**Purpose:** Synthesize the verifier outputs and decision graph into a human-readable final report.

**Input contract:**

```python
{
  "article_id": str,
  "claims": list[ClaimWithVerdict],
  "graph": DecisionGraph,
  "credibility_score": float
}
```

**Output contract:**

```python
{
  "status": "ok",
  "data": {
    "credibility_score": float,        # passed through, not recalculated
    "credibility_label": "high" | "mixed" | "low",
    "top_findings": [
      {
        "claim_id": str,
        "headline": str,               # ≤ 80 chars
        "explanation": str             # 1-2 sentences
      }
    ],                                  # exactly 3
    "patterns": [                       # 0-3 cross-claim observations
      {
        "type": "source_clustering" | "topic_skew" | "consistency_break",
        "description": str
      }
    ],
    "summary": str                     # ≤ 400 chars, written for a general reader
  }
}
```

**Hard rules:**

* Do not recompute the score. The decision graph is the source of truth.
* `top_findings` must reflect the highest-weight claims (consequential), not the lowest-confidence ones (sensational). The Meta-Reviewer's job is to surface what matters, not what's juiciest.
* Patterns are optional. If none stand out, return `[]`. Don't fabricate patterns to fill space.
* Never quote source material — refer to it ("two sources contradicted this") rather than reproducing it.

---

## 5. Orchestration Rules

### 5.1 Parallel Execution

Verifier agents are launched via Codex `cloud exec` in a single fan-out call, not a Python loop with `asyncio.gather` over individual API calls. The cloud-exec model is the project's defining technical choice — preserve it.

```python
# correct
results = codex.cloud_exec_parallel(
    agent="verifier",
    inputs=[{"claim_id": c.id, "claim_text": c.text, ...} for c in claims],
    max_concurrency=25,
    timeout_per_agent=15
)

# wrong
results = await asyncio.gather(*[verifier_call(c) for c in claims])
```

### 5.2 Caching for Demo Reliability

For the 3 pre-tested demo articles, cache full pipeline results in `fixtures/demo_cache/<article_id>.json`. The UI checks the cache first when running a known article. This is the fallback if the network or APIs flake on stage.

The cache is **only** for demo articles. User-submitted articles always run live.

### 5.3 No Retries

Verifiers do not retry on failure. A failed verifier becomes an "unknown" verdict in the graph. Retrying inside a 48-hour build is a recipe for cascading delays during the demo. Build the system to be honest about uncertainty instead.

---

## 6. Code Layout

```
/
├── AGENTS.md                          # this file
├── backend/
│   ├── agents/
│   │   ├── extractor.py
│   │   ├── verifier.py
│   │   └── meta_reviewer.py
│   ├── graph/
│   │   └── decision_graph.py
│   ├── orchestrator.py                # entry point, wires the pipeline
│   ├── tools/
│   │   ├── tavily.py
│   │   └── wikipedia.py
│   ├── utils/
│   │   ├── logging.py
│   │   └── prompts.py                 # all system prompts live here
│   ├── schemas.py                     # pydantic models, mirror of shared/types.ts
│   └── api.py                         # FastAPI server
├── frontend/
│   ├── app/
│   │   ├── page.tsx                   # landing + input
│   │   ├── run/[id]/page.tsx          # live agent panel
│   │   └── report/[id]/page.tsx       # annotated article + report
│   ├── components/
│   │   ├── AgentCard.tsx              # single verifier card
│   │   ├── ClaimGraph.tsx             # React Flow visualization
│   │   └── CredibilityGauge.tsx
│   └── lib/
│       └── types.ts                   # mirror of backend/schemas.py
├── fixtures/
│   ├── articles/                      # 3 demo articles as .txt
│   └── demo_cache/                    # cached pipeline outputs
└── tests/
    ├── test_extractor.py              # iteration harness for prompt tuning
    └── test_pipeline_e2e.py
```

---

## 7. Build Order (do not skip steps)

1. Scaffold repo and shared schemas. Verify `shared/schemas.py` and `shared/types.ts` agree.
2. Implement the **Extractor** agent and its test harness against fixture articles. Iterate on prompt until extraction quality is acceptable on all 3 demo articles.
3. Implement a **stub Verifier** that returns canned data. Wire up parallel orchestration with the stub. Confirm 25 concurrent agents resolve correctly and emit logs.
4. Replace stub with real Verifier logic. Test on extracted claims from fixtures.
5. Implement the **Decision Graph Builder** (deterministic, no LLM).
6. Implement the **Meta-Reviewer**.
7. Build the live agent panel UI against streaming logs.
8. Build the annotated article view and the credibility report.
9. Generate demo cache for the 3 fixture articles.
10. End-to-end smoke test on all 3 articles, 5 runs each. Record demo video.

Each step is shippable on its own. Do not start step N+1 with step N broken.

---

## 8. What This System Does Not Do

Listed explicitly because Codex will otherwise try to add these:

* No PDF input. Text only.
* No podcast or video transcripts.
* No multi-language support.
* No user accounts or auth.
* No claim-editing UI. Extraction is final.
* No "ask follow-up questions" feature.
* No browser extension. Web app only.
* No mobile-optimized views (desktop demo only).
* No more than 25 claims per article ever.

If a feature isn't in this file, it isn't in scope.
