# Dev Council — How It Works, Prerequisites, and Usage

This guide explains the **Dev Council**: what it is, how the skill and the
`council` tool fit together, what you need to run it, the pluggable model
backends (including a token-per-model / AutoX hybrid), and how to operate it
safely.

---

## 1. What the Dev Council is

Asking one AI model to review a design or a code change gives you **one
perspective with one set of blind spots**. The Dev Council instead runs the
question through several role-based advisors — each pushing hard on a different
angle — then has them **peer-review each other anonymously**, and finally a
**Chairman** synthesizes a single decisive verdict.

It has two modes:

- **PLAN** — challenge an approach/architecture *before* you write code.
- **REVIEW** — catch bugs and quality issues *after* code is written, before it ships.

The non-negotiable rule is **evidence over opinion**: every claim must cite real
`file:line` from the codebase. "This might have a bug" is rejected; "in
`OrderService.create()` line 84 the null branch is unhandled" is accepted.

---

## 2. The two pieces: the skill and the `council` tool

| Piece | Where | Responsibility |
|-------|-------|----------------|
| **`dev-council` skill** | `~/.cursor/skills/dev-council/SKILL.md` | The "brain": framing the question, triaging which advisors to convene, and presenting the verdict. Invoked when you ask Cursor (or another assistant) to run the council. |
| **`council` CLI/tool** | this repo (`dev-council-runner`) | The "engine": runs each advisor as its own agent **on its own model**, performs anonymized peer review, runs the Chairman, meters usage, and returns the verdict markdown. |

**Why two pieces?** Cursor's built-in `Task` sub-agents all run on the *same*
model — "one opinion wearing six hats." The `council` tool exists to give each
persona a genuinely **different model**, which is the entire value of a council.
The skill delegates execution to the tool.

When you ask Cursor to "run the dev council," the chat agent reads the skill,
triages, and then shells out to `council run ...`. The multi-model diversity
comes from the tool, not from Cursor's `Task` mechanism.

---

## 3. How a run flows

```
You: "council this change"
        │
        ▼
  [skill] frame the brief + triage roster/stakes
        │  council run --mode review --stakes risky --cwd . --brief-file brief.md
        ▼
  [tool] dispatch advisors  ── each persona → its own backend + model (parallel)
        │                        cursor personas browse the repo; provider
        │                        personas get injected repo context
        ▼
  [tool] anonymize responses (A/B/C…) → peer review (cross-family reviewers)
        │
        ▼
  [tool] Chairman synthesizes the de-anonymized analyses + peer reviews
        │
        ▼
  Verdict markdown  →  presented back to you
        │
        └─ one usage row per agent run appended to ~/.dev-council/usage.jsonl
```

A single failed advisor never sinks the run — it is captured and the council
continues.

---

## 4. The roster (personas)

A small **core** always runs; **specialists** are convened only when the change
touches their domain (triage), so coverage is complete without noise.

**REVIEW mode:** Bug Hunter (core), Maintainability (core), Test Reviewer (core),
Standards & Compliance (core), plus specialists Security, Performance,
API/Backward-Compat, Data/DBA.

**PLAN mode:** Product Manager (core), Architect (core), Pragmatist (core),
Long-term Engineer (core), plus specialists UX, Security/Threat Modeler,
Performance/Scalability, SRE/Reliability, Data/DBA, QA.

Each persona is assigned a model by **capability** (heavy reasoning lenses get
strong "thinking" models; light lenses get cheaper/faster ones) and **diversity**
(roles spread across model families so they don't share blind spots). Heavy
personas run at high reasoning effort.

At the **`risky`** tier, REVIEW convenes a **second Bug Hunter on a different model
family** ("Bug Hunter — Deep Reasoning", Claude Opus) alongside the primary
(Codex) one. Bug-finding is the highest-value lens and the one where models
disagree most, so two independent hunts de-correlate blind spots; when both flag
the same issue the Chairman can treat it as high-confidence. This pair runs only
at `risky` — `standard` keeps a single Bug Hunter to stay lean.

---

## 5. Prerequisites

**Required (default Cursor backend):**

1. **Python 3.10+**.
2. **The tool installed:** `pip install -e .` (or `pipx install .`) from this repo.
   This also installs the `cursor-sdk` dependency and the `council` command.
3. **A Cursor API key** in the environment variable `CURSOR_API_KEY`
   (a user key or a team service-account key from
   <https://cursor.com/dashboard/integrations>).
4. The `council` command on your **PATH** (pip prints the Scripts directory if it
   isn't; add it once). If `council` isn't found, you can always use
   `python -m council` instead.

**Optional (provider backends — only if you use them):**

- `pip install 'dev-council-runner[openai]'` and `OPENAI_API_KEY` (and optionally
  `OPENAI_BASE_URL`) — also covers **AutoX** and other OpenAI-compatible gateways.
- `pip install 'dev-council-runner[anthropic]'` and `ANTHROPIC_API_KEY`.
- `pip install 'dev-council-runner[google]'` and `GOOGLE_API_KEY` (or `GEMINI_API_KEY`).
- `pip install 'dev-council-runner[all]'` for all three.

> **Credentials are read from environment variables only.** Never put a key in a
> config file or commit it. See [§9 Security](#9-security--secret-hygiene).

If a key for a backend you're about to use is missing, the CLI **asks you for it
interactively** (input hidden) and offers to save it for future sessions; in
non-interactive contexts it fails fast with a clear message naming the env var.

---

## 6. Backends (where each persona actually runs)

Execution is **pluggable**. Each persona declares a `backend`; the default is
`cursor`.

| Backend | Grounding | Credentials | Notes |
|---------|-----------|-------------|-------|
| `cursor` *(default)* | **Grounded** — the agent browses the repo and cites `file:line` | `CURSOR_API_KEY` | One key gives GPT/Codex + Claude + Gemini. Recommended. |
| `openai` | Prompt-context (injected diff/files) | `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`) | Works against OpenAI **and any OpenAI-compatible gateway** (AutoX, OpenRouter, vLLM…). |
| `anthropic` | Prompt-context | `ANTHROPIC_API_KEY` | Native Claude API. |
| `google` | Prompt-context | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Native Gemini API. |

**Grounding tradeoff:** only the Cursor backend lets an advisor open any file in
the repo. Provider backends are plain chat calls, so the tool injects a bounded
repo-context snapshot (the diff under review, or a file listing) into their
prompt. That is lower-fidelity than a browsing agent — keep your highest-value
lenses on `cursor` when you can.

### Choosing how it runs (decision tree)

1. **`python -m council --version` works → use the CLI** (real per-persona models):
   - **Cursor key set** → default `cursor` backend (GPT + Claude + Gemini from one
     key, grounded). Best path.
   - **No Cursor key, provider keys set** → provider backends (see below).
2. **CLI not installed, inside Cursor** → the skill falls back to internal `Task`
   sub-agents (single model — the limitation this tool removes).

Always preview with `--dry-run` (see §7) to see the resolved plan and which keys
are missing before running.

### Running without Cursor (a token per model)

If you don't have a Cursor key, run entirely on provider keys. Two ready-made
overrides ship under `examples/` — copy one to `~/.dev-council/personas.yaml`
(it deep-merges over the defaults) and edit the model ids to match your account:

- **`examples/personas.providers.yaml`** — token-per-family, no Cursor at all.
  Set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` for the families
  you use, `pip install 'dev-council-runner[all]'`, then `--dry-run` to confirm.
  Cross-family peer review works via per-family `peer_review_backends`.
- **`examples/personas.autox-hybrid.yaml`** — GPT personas on AutoX, Claude/Gemini
  on Cursor (needs both `CURSOR_API_KEY` and `AUTOX_API_KEY`/`AUTOX_BASE_URL`).

> Diversity needs at least two providers. With a single provider key every persona
> collapses onto one family — one blind spot — which defeats the council.

### Recommended: the AutoX hybrid

Because `backend` is **per-persona**, you can mix backends in one council. If you
have AutoX (GPT-only) plus a Cursor key, the best setup is:

- **GPT personas → AutoX** (uses quota you already have), and
- **Claude + Gemini personas → Cursor** (preserves cross-family diversity).

Define an `autox` backend once (it ships as an example in `backends.yaml`), set
`AUTOX_API_KEY` + `AUTOX_BASE_URL`, and point the GPT personas at
`backend: autox` in your `~/.dev-council/personas.yaml` override.

---

## 7. Using it

### Through Cursor (recommended day-to-day)

Just ask in plain language: *"Run the dev council to review my changes"* or
*"Convene the council to plan this design."* The skill triages and drives the
tool. To force the tool path explicitly: *"Run the dev council via the council
CLI."*

### Directly on the command line

```bash
council run   --mode review --stakes risky --cwd . --brief "Review my auth changes"
council run   --mode plan   --stakes standard --cwd . --brief-file design.md
council run   ... --dry-run      # preview the plan (personas, backends, models, readiness) WITHOUT running
council run   ... --dry-run --json   # same, machine-readable
council models     # which Cursor models your key can use + per-persona resolution
council backends   # which backends are configured and whether their keys are set
council usage      # runs this month vs the soft budget ceiling, by model/backend
```

**Always preview first.** `--dry-run` resolves the roster, per-persona backend +
model, peer-review/chairman backends, and a **READY / NOT READY** status per
backend, then exits without spending anything. Use it to confirm the run is
multi-model and to see exactly which key/package to supply if it's blocked.

Useful `run` flags: `--stakes trivial|standard|risky`, `--roster k1,k2,...`
(force specific personas), `--brief` / `--brief-file` / stdin, `--diff-scope`,
`--out file.md`, `--no-peer-review` / `--peer-review`.

---

## 8. Tiers (budget governance)

| Tier | Roster | Peer review | Models | Use for |
|------|--------|-------------|--------|---------|
| `trivial` | — | no | — | one-line fixes — the tool refuses to convene |
| `standard` *(default)* | core only | no | heavy personas downgraded to cheaper models | everyday changes |
| `risky` | core + triaged specialists | yes | full diverse roster at high effort | production gates: auth, money, migrations, concurrency |

The expensive diverse roster only runs at `risky`. Everything else stays cheap.
`council usage` tracks runs against a soft monthly ceiling and warns as you
approach it.

---

## 9. Security & secret hygiene

- **No secret is ever stored in the repo.** All credentials come from environment
  variables. The repo `.gitignore` excludes `.env`, key files, and the local
  usage log.
- The interactive key prompt hides input and only persists to your **user
  environment** if you say yes — never to a file in the project.
- Council advisors run read-only: they analyze and cite; they never edit code.

---

## 10. Configuration & overrides

Defaults ship inside the package (`src/council/defaults/`). Override any subset by
dropping files into `~/.dev-council/`:

- `personas.yaml` — rosters, per-persona model, `model_params` (reasoning effort),
  and `backend`.
- `tiers.yaml` — which personas/stages run per stakes tier and the budget ceiling.
- `backends.yaml` — backend definitions (type, credential env var, optional base_url).

Cursor model ids are validated at runtime against `council models`; an id your
account can't use falls back to the configured default, and unsupported model
params are dropped with a warning (the tool never invents a slug or sends an
invalid param). Provider-backed personas are not validated against the Cursor
catalog.

---

## 11. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `council: command not found` | The Scripts dir isn't on PATH. Use `python -m council`, or add the dir pip printed at install. |
| `... model list came back empty` | Cursor discovery failed (network/key). Run `council models`; check `CURSOR_API_KEY`. |
| `one or more configured backends are not ready` | A backend in use is missing its package or key. Run `council backends` to see which, then install the extra / set the env var. |
| Key is set but reported **missing** (e.g. `CURSOR_API_KEY` not set) | Stale editor environment: Cursor captured its env at launch, so a key you set afterward isn't in the spawned process. On Windows the CLI now self-heals by reading the persisted value from the registry; if it still shows missing, **fully quit and reopen Cursor** (Reload Window is not enough), or set it for the current shell: `$env:CURSOR_API_KEY = [Environment]::GetEnvironmentVariable('CURSOR_API_KEY','User')`. |
| A single persona shows `status=error` | Captured and reported; the council still produces a verdict. Check the `error` field in `~/.dev-council/usage.jsonl`. |
| First command is slow (~10–20s) | The Cursor SDK bridge cold-starts. Subsequent calls in the same session are faster. |
| Provider persona gives weak citations | Expected: provider backends can't browse the repo. Keep high-value lenses on `cursor`. |
