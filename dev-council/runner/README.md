# Dev Council Runner

A standalone, host-agnostic CLI that runs a **multi-model dev council**: each advisor
persona runs as its own agent on a **different model** (GPT/Codex, Claude, Gemini),
reads the real repository, and backs every claim with `file:line` evidence. Responses
are anonymized, peer-reviewed, and a Chairman synthesizes a decisive verdict.

Execution is **pluggable** across backends: the default [Cursor SDK](https://cursor.com/docs/sdk/python)
backend runs grounded local agents that browse the repo, and optional provider backends
(`openai` — also covers AutoX/OpenAI-compatible gateways — `anthropic`, `google`) let you
bring your own per-model keys. Backend is per-persona, so you can run a hybrid (e.g. GPT
personas on AutoX, Claude/Gemini on Cursor).

> **New here? Read [`GUIDE.md`](GUIDE.md)** for the full explanation of how the skill and
> the tool fit together, prerequisites, backends, and the AutoX hybrid.

The tool is intentionally decoupled from any single editor. It can be triggered from
Cursor today (via the `dev-council` skill) and from other assistants later.

## Why

Asking one model gives you one set of blind spots. Running advisors on different model
**families** de-correlates those blind spots, which is the whole point of a council.
This runner makes "a different model per persona" the default, while keeping every
advisor grounded in the actual code.

## Install

```bash
pipx install /path/to/dev-council-runner
# or, for development:
pip install -e /path/to/dev-council-runner

# optional provider backends (bring your own keys):
pip install -e '/path/to/dev-council-runner[openai]'      # OpenAI / AutoX / compatible
pip install -e '/path/to/dev-council-runner[all]'         # openai + anthropic + google
```

Set your Cursor key (a user key or team service-account key):

```bash
export CURSOR_API_KEY="cursor_..."     # bash / zsh
$env:CURSOR_API_KEY = "cursor_..."     # PowerShell
```

Credentials are read from environment variables only — never commit a key. If a needed
key is missing, the CLI prompts for it (hidden) and can save it to your user environment.

## Quick start

```bash
# Confirm which models your key can actually use (Claude/Gemini included?)
council models

# REVIEW the uncommitted change in the current repo at the "risky" tier
council run --mode review --stakes risky --cwd . --brief-file brief.md

# PLAN a design (brief on stdin), standard tier
echo "Should we move order creation to async Kafka events?" | council run --mode plan

# See what you have spent and whether you are nearing your soft ceiling
council usage

# See which backends are configured and whether their credentials are ready
council backends
```

## Tiers (budget governance)

| Tier | Roster | Peer review | Use for |
|------|--------|-------------|---------|
| `trivial` | none | no | one-line fixes - the tool refuses to convene |
| `standard` (default) | core only | no | everyday changes |
| `risky` | core + triaged specialists | yes | production-facing gates, auth, money, migrations |

The diverse, expensive roster only runs at `risky`. Everything else stays cheap.

## Configuration

Defaults ship inside the package (`src/council/defaults/`). Override any of them by
copying into `~/.dev-council/`:

- `personas.yaml` - PLAN and REVIEW rosters: each persona's lens, model, `model_params`, and `backend`.
- `tiers.yaml` - which personas/stages run per stakes tier, and the soft budget ceiling.
- `backends.yaml` - backend definitions (type, credential env var, optional base_url).

Model ids in `personas.yaml` are validated at runtime against `council models`; any id
your account cannot use falls back to the configured default (the tool never invents a
slug).

## How it maps to the `dev-council` skill

The Cursor `dev-council` skill keeps owning framing (Step 1), triage (Step 2), and the
verdict presentation (Step 5). Instead of spawning advisors with the internal `Task`
tool, it calls `council run ...`. This runner performs the dispatch, peer review, and
Chairman synthesis with true per-persona models.
