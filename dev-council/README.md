# Dev Council

Run an engineering decision or a code change through a **council of role-based AI
advisors** that work in parallel, each pushing hard on a different angle (bugs,
security, performance, API compatibility, tests, …), then peer-review each other
anonymously, then a **Chairman** synthesizes one decisive verdict. Every claim must
cite real `file:line` evidence — no vibes.

Two modes:
- **PLAN** — challenge an approach/design/architecture *before* you write code.
- **REVIEW** — catch bugs and quality issues in a change *before* it ships.

The whole point is **diversity**: advisors run on *different model families*
(GPT/Codex, Claude, Gemini) so they don't share blind spots. One model wearing six
hats is still one opinion.

---

## What's in this folder

| Path | What it is |
|------|------------|
| **`SKILL.md`** | The skill itself — instructions the Cursor agent follows. This is what makes the skill work. |
| **`GUIDE.md`** | Full explanation: how it works, prerequisites, backends, usage, tiers, security, troubleshooting. **Read this for depth.** |
| **`runner/`** | The optional `council` CLI — the multi-model engine (a `pip`-installable Python package). |
| `README.md` | This file. |

## The two parts (and what each gives you)

1. **The skill** (`SKILL.md`) — works on its own. Without the runner, when invoked
   inside Cursor it falls back to internal sub-agents, which run on a **single
   model** (Cursor's `Task` tool can't guarantee a different model per advisor).
2. **The runner** (`runner/`) — the upgrade. When the `council` CLI is installed,
   the skill hands off to it and each persona runs as its **own agent on its own
   model**, grounded in your repo, with budget metering. **This is what delivers
   true multi-model review.**

> TL;DR: install the skill to use it; install the runner to make it multi-model.

---

## Install

### 1. Install the skill

```bash
git clone https://github.com/ilanfux/skills.git
cp -r skills/dev-council ~/.cursor/skills/dev-council
```

PowerShell (Windows):

```powershell
git clone https://github.com/ilanfux/skills.git
Copy-Item -Recurse skills\dev-council "$env:USERPROFILE\.cursor\skills\dev-council"
```

### 2. Install the runner (recommended — unlocks multi-model)

```bash
pip install -e skills/dev-council/runner
# optional: bring-your-own-key provider backends (OpenAI/AutoX, Anthropic, Google)
pip install -e 'skills/dev-council/runner[all]'
```

Verify: `python -m council --version` should print a version.

### 3. Provide a key (never commit keys)

The default setup uses one Cursor key for all model families:

```bash
# get a key at https://cursor.com/dashboard/integrations
export CURSOR_API_KEY=...        # macOS/Linux
setx CURSOR_API_KEY "..."        # Windows (then fully restart your editor)
```

Keys are read from environment variables only — they are never written to a file
or this repo. No Cursor? You can run on your own provider keys instead — see
[`GUIDE.md` → Running without Cursor](GUIDE.md).

---

## Use it

### In Cursor (day-to-day)

Just ask, using a trigger phrase:

- `council this design: <your approach>` — PLAN
- `review this with the council` — REVIEW (challenge your current changes)
- `challenge this` / `did I miss anything before I ship?`

The agent frames the question, picks the roster, and — if the `council` CLI is
installed — runs it multi-model and reports back. It will **tell you how it's
running** (which models on which backend) before spending anything.

### Directly on the command line

Always preview first with `--dry-run` (resolves the roster, per-persona model, and
shows which keys are ready) — then drop the flag to run for real:

```bash
python -m council run --mode review --stakes risky --cwd . --brief-file brief.md --dry-run
python -m council run --mode review --stakes risky --cwd . --brief-file brief.md
```

Helpful commands: `council models` (models your key can use), `council backends`
(configured backends + credential status), `council usage` (spend vs. budget).

---

## How a run works

```
frame the brief → dispatch advisors in parallel (each on its own model, reading the repo)
              → anonymized peer review → Chairman synthesizes the verdict
```

Stakes tiers control cost: `standard` runs a lean core roster; `risky` convenes the
full diverse roster (including a second, cross-family Bug Hunter) plus peer review.

## Requirements

- Python 3.10+ (for the runner)
- A `CURSOR_API_KEY` (or provider keys for a no-Cursor setup)

## Learn more

- **[`GUIDE.md`](GUIDE.md)** — the complete how-it-works, prerequisites, backend
  decision tree, no-Cursor setup, tiers, security, and troubleshooting.
- **[`runner/README.md`](runner/README.md)** — the engine's quick-start and install.
