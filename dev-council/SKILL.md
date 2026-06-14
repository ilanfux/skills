---
name: dev-council
description: >-
  Run a development decision or a code change through a council of role-based AI advisors who work in parallel, peer-review each other anonymously, then a Chairman synthesizes a decisive verdict. Two modes — PLAN (challenge an approach, design, or architecture BEFORE writing code) and REVIEW (challenge an implementation AFTER writing code, to catch bugs and quality issues before it ships). A small core council always runs; specialist advisors (Security, Performance, SRE/Reliability, Data/DBA, UX, API-compatibility, QA) are convened only when the change touches their domain (triage), so coverage stays complete without noise. Advisors must back every claim with real evidence from the codebase (cite file:line); no vibes-only opinions. MANDATORY TRIGGERS: "dev council", "council this", "convene the council", "challenge this", "pressure-test this", "stress-test this", "war room this", "תכנס את המועצה", "תאתגר את זה". STRONG TRIGGERS (real engineering decision or non-trivial change): "should we build it this way", "is this the right design/architecture", "review this before I ship", "challenge my approach", "is this code correct", "did I miss anything", "what could break". Do NOT trigger on trivial lookups, one-line fixes, or pure factual questions.
---

# Dev Council

Asking one model gives you one perspective. For an architecture decision or a risky change, one perspective hides blind spots until they cost you in production. The council runs the question through role-based advisors who each push hard on a different angle, then peer-review each other, then a Chairman makes the call.

Adapted from Andrej Karpathy's LLM Council (dispatch → anonymous peer review → chairman), specialized for software development.

## The non-negotiable rule: evidence over opinion

This council reviews engineering work, not marketing copy. An advisor's claim is worthless unless it is grounded in the actual code/design.

- Every advisor reads the relevant files (use `Read`, `Grep`, `Glob`) before answering.
- Every concrete claim cites `path:line` or a specific function/contract.
- "This might have a bug" is rejected. "In `OrderService.create()` line 84 the `null` branch is unhandled, so X input throws NPE" is accepted.
- All council sub-agents run `readonly: true`. They analyze; they never edit.

## Modes

| Mode | When | Triggered by |
|------|------|--------------|
| **PLAN** | Before code exists — challenge an approach, design, or architecture | "council this design", "challenge my approach", "is this the right architecture" |
| **REVIEW** | After code is written — catch bugs/quality issues before shipping | "review this with the council", "challenge this code", "did I miss anything before I ship" |

If the mode is ambiguous, infer from whether code already exists for the thing in question. If still unclear, ask one short question, then proceed.

## Roster: core + conditional specialists

A small **core** always runs (the essential tensions). **Specialists** are convened only when the change touches their domain — this keeps coverage complete without flooding the council with "not my area" noise. Typical run = 5–7 advisors. Triage tables are in [Step 2](#step-2-triage--convene-parallel-sub-agents).

---

## Mode PLAN — advisors

Each is a thinking lens, not a job title, chosen to create deliberate tension so no single bias dominates.

**Core (always):**

1. **Product Manager** — Are we solving the *right* problem? Real user/business value, who needs this, correct scope (over-/under-built), unstated or assumed requirements.
2. **Architect** — System shape: boundaries and responsibilities, data model, API/contract design, coupling, failure modes, backward compatibility, scalability, observability. For microservices: service boundaries, sync vs async (Kafka/events), version impact on consumers.
3. **Dev Lead A — The Pragmatist** — Simplest thing that works. YAGNI, smallest diff, lowest risk *now*. Suspicious of speculative abstraction and gold-plating.
4. **Dev Lead B — The Long-term Engineer** — The codebase in 12 months. Correctness, testability, maintainability, avoiding tech debt and footguns. Clashes with Dev Lead A by design.

**Specialists (convened by triage):**

5. **UX/UI Expert** — Flows, clarity, error/empty/loading states, accessibility, consistency with existing patterns.
6. **Security / Threat Modeler** — Threat model the design: trust boundaries, authn/authz, data exposure (PII), input validation, secrets handling, abuse cases. Shift-left: catch the flaw before it's built.
7. **Performance / Scalability Engineer** — Design-time perf: data access patterns (N+1 risk), volume/throughput at scale, latency budget, caching strategy, pagination, hot paths.
8. **SRE / Reliability & Operability** — What happens at 2am? Failure modes of every dependency, timeouts/retries/circuit-breakers, idempotency, rollback/rollout, config, alerting, and what's observable in logs/metrics when it breaks.
9. **Data / DBA** — Schema and data: model correctness, backward-compatible migrations, indexing, integrity/constraints, bulk-data and data-volume implications.
10. **QA / Test Strategy** — How will we *prove* this works? Testability of the design, key scenarios and edge cases, what's hard to test and how to make it testable.

---

## Mode REVIEW — reviewers

> **Java / Spring Boot:** do NOT reimplement reviewers here. Invoke the existing `java-code-review` skill (it triages its own specialized pipeline against team standards), collect its findings as the council's review inputs, then go straight to the **Chairman** step to produce the decisive ship/no-ship gate.

**For any other language/stack:**

**Core (always):**

1. **Bug Hunter** — Logic and edge cases: null/None/undefined, off-by-one, boundary inputs, empty collections, concurrency/races, resource leaks, swallowed/incorrect error handling. Assumes a bug exists and hunts it.
2. **Maintainability Reviewer** — Readability, naming, SOLID, duplication, dead code, complexity, adherence to project conventions.
3. **Test Reviewer** — Coverage of the **changed lines**, missing edge-case and failure-path tests, brittle/flaky tests, tests asserting the wrong thing.

**Specialists (convened by triage):**

4. **Security Reviewer** — Injection (SQL/command/template), authz/authn gaps, secrets in code/logs, input validation, sensitive data in logs, unsafe deserialization, weak crypto, SSRF/path traversal.
5. **Performance Reviewer** — N+1 queries, unbounded loops/allocations, blocking I/O on hot paths, missing pagination, inefficient queries, missing/incorrect caching, chatty network calls.
6. **API Contract & Backward-Compatibility Reviewer** — Will this break consumers? Public API/DTO/event-schema changes, removed/renamed fields, default/nullability changes, versioning.
7. **Data / DBA Reviewer** — Migration safety and reversibility, backward-compatible schema changes, missing indexes, lock/locking risk on large tables, data integrity.

> **Scope rule (REVIEW):** flag issues only on lines that were **changed** (use `git diff`). Full files are context only; don't flag pre-existing untouched code.

---

## Workflow

Copy and track this checklist:

```
- [ ] Step 1: Frame (gather context + write the neutral brief)
- [ ] Step 2: Triage + convene advisors (parallel)
- [ ] Step 3: Peer review (anonymized, parallel)
- [ ] Step 4: Chairman synthesis
- [ ] Step 5: Present verdict in chat
```

### Step 1: Frame the question (with context)

Spend ~30s gathering the context that turns generic advice into specific, grounded advice. In one batch:

- Read files the user referenced/attached and the code directly involved.
- PLAN: scan for `AGENTS.md`/`CLAUDE.md`/`README`, the existing modules the change touches, and any design docs.
- REVIEW: get the diff — `git diff --name-only` then `git diff` for changed files (committed vs base branch **and** uncommitted). Read full content of complex changed files for context.

Then write a **neutral brief** all advisors receive. Don't inject your own opinion. Include:
1. The core decision (PLAN) or what the change does (REVIEW)
2. Key context from user + workspace (stack, constraints, consumers, conventions)
3. What's at stake / why it matters
4. Relevant code locations (paths, key functions, contracts)

If too vague to frame ("council my service"), ask exactly one clarifying question, then proceed.

### Step 2: Triage + convene (parallel sub-agents)

Run the **core** advisors for the mode. Then add each **specialist** whose trigger fires:

**PLAN triage:**

| Specialist | Convene when the change involves |
|------------|----------------------------------|
| UX/UI | A user-facing surface (UI, CLI, user-consumed API, response-shape change) |
| Security / Threat Modeler | authn/authz, PII/sensitive data, untrusted/external input, secrets, a new network boundary, deserialization/file handling |
| Performance / Scalability | hot paths, high volume/throughput, large datasets, latency-sensitive flows, new queries or external calls in a loop |
| SRE / Reliability | a new service/endpoint, calls to external dependencies, async/messaging, stateful behavior, deploy/config/rollback impact |
| Data / DBA | schema/migration, new tables/columns/indexes, data-model change, bulk data ops |
| QA / Test Strategy | any non-trivial new behavior or logic (i.e. most changes except pure config/docs) |

**REVIEW triage** (non-Java; Java delegates to `java-code-review`):

| Specialist | Convene when changed files include |
|------------|------------------------------------|
| Security | auth, input handling, secrets, crypto, data exposure, external I/O |
| Performance | services, data access, loops, queries, hot paths |
| API Contract & Backward-Compat | public API, DTO/contract, event/message schema |
| Data / DBA | schema/migration files, queries, data-model code |

Spawn all selected advisors **simultaneously in ONE message** (multiple `Task` calls in one batch) — sequential spawning wastes time and lets answers bleed together.

- `subagent_type`: `generalPurpose` (or `code-reviewer` for REVIEW reviewers)
- `readonly`: `true`
- Tell the user which advisors convened and which were skipped (and why), e.g. `"Council: PM, Architect, 2 Dev Leads, Security, Data (skipped UX/Perf — no UI or hot path)."`

**Sub-agent prompt template:**
```
You are the {ROLE} on a Dev Council reviewing engineering work.

Your lens: {ROLE DESCRIPTION}

The brief:
---
{FRAMED BRIEF}
---

Relevant code to read first: {PATHS / FUNCTIONS}

Rules:
- Read the actual code before forming any opinion (Read/Grep/Glob).
- Back every claim with evidence: cite path:line or a specific function/contract.
- Lean fully into your lens. Do NOT hedge or try to be balanced — other advisors cover the angles you don't. Synthesis comes later.
- If this change genuinely doesn't touch your domain, say so in ONE line and stop. Don't manufacture concerns.
- 150–300 words. No preamble. Be concrete and specific to THIS code/decision.
{REVIEW ONLY: Flag issues only on changed lines. Label each finding Critical / Major / Minor.}
```

### Step 3: Peer review (parallel sub-agents)

This is what makes it more than "ask N times." Collect the responses and **anonymize** them as Response A, B, C, … (randomize the letter→advisor mapping so there's no positional or role bias). Spawn one reviewer per advisor, in parallel.

**Reviewer prompt template:**
```
{N} advisors independently analyzed this engineering {decision|change}:
---
{FRAMED BRIEF}
---
Anonymized responses:
**A:** {...}  **B:** {...}  **C:** {...}  ... (all responses)

Answer, referencing responses by letter, under 200 words:
1. Which response is strongest, and why?
2. Which has the biggest blind spot or weakest-supported claim? What is it missing?
3. What did ALL responses miss that the council must consider?
```

### Step 4: Chairman synthesis

One agent (or you) receives the brief, the **de-anonymized** advisor responses, and all peer reviews. The Chairman is decisive, may overrule the majority when the dissenter's evidence is stronger, and stays grounded in the cited evidence.

### Step 5: Present the verdict in chat

Markdown only — no HTML, no files (unless the user asks to save). Keep it scannable.

**PLAN verdict format:**
```
## Council Verdict (Plan): {topic}
_Convened: {advisors} · skipped: {specialists + why}_

### Where the council agrees
{high-confidence points multiple advisors converged on, independently}

### Where the council clashes
{genuine disagreements — present both sides + why each is reasonable}

### Blind spots the council caught
{things that only surfaced in peer review}

### The recommendation
{a clear, decisive call with reasoning — not "it depends"}

### The one thing to do first
{a single concrete next step}
```

**REVIEW verdict format:**
```
## Council Verdict (Review): {what changed}
_Convened: {reviewers} · skipped: {specialists + why}_

### 🔴 Must fix before merge (blocking)
- {finding} — `path:line` — why it matters

### 🟡 Should fix (non-blocking)
- {finding} — `path:line`

### Where reviewers disagreed
{the call, with reasoning}

### What everyone missed
{surfaced in peer review}

### Verdict
{SHIP ✅ | FIX-THEN-SHIP 🛠️ | RETHINK ⛔} — one-line justification
```

---

## Optional: continuous "challenge mode"

If you want to be challenged automatically (not only when you say "council this"): after completing a non-trivial implementation, run **Mode REVIEW** on your own diff before declaring the work done, and present the verdict, treating 🔴 findings as a gate. Use this when the user opts in (e.g. "stay in challenge mode" / "always council my changes this session"). Skip it for trivial one-line edits — not worth the latency.

## Important notes

- **Triage, don't flood** — run core + only the specialists whose trigger fires. An advisor with nothing to say is noise that weakens peer review and synthesis.
- **Always spawn advisors in parallel** (one batched message of `Task` calls).
- **Always anonymize before peer review** — otherwise reviewers defer to roles instead of judging on merit.
- **Evidence or it doesn't count** — reject any finding without a `path:line` / contract reference.
- **The Chairman decides** — a real recommendation, and may side with a lone dissenter whose evidence is strongest.
- **Don't council the trivial** — one right answer or a one-line fix → just do it.
- **Java/Spring Boot REVIEW** → delegate to `java-code-review`, then apply the Chairman gate.
