# skills

A personal collection of [Cursor Agent Skills](https://docs.cursor.com/).

Each skill lives in its own folder with a `SKILL.md` file that teaches the agent how to perform a specific workflow.

## Skills

| Skill | Description |
|-------|-------------|
| [`dev-council`](dev-council/) | Runs a development decision (PLAN) or a code change (REVIEW) through a council of role-based AI advisors who work in parallel, peer-review each other anonymously, then a Chairman synthesizes a decisive verdict. A small core council always runs; specialists (Security, Performance, SRE/Reliability, Data/DBA, UX, API-compatibility, QA) are convened only when the change touches their domain. Every claim must be backed by evidence from the codebase. |

## Installation

Clone the repo and copy any skill into your Cursor skills directory:

- **Personal** (available in all your projects): `~/.cursor/skills/<skill-name>/`
- **Project** (shared via a repo): `.cursor/skills/<skill-name>/`

```bash
git clone https://github.com/ilanfux/skills.git
cp -r skills/dev-council ~/.cursor/skills/dev-council
```

On Windows (PowerShell):

```powershell
git clone https://github.com/ilanfux/skills.git
Copy-Item -Recurse skills\dev-council "$env:USERPROFILE\.cursor\skills\dev-council"
```

> **`dev-council` is more than a `SKILL.md`.** It ships with an optional
> multi-model engine (the `council` CLI under [`dev-council/runner/`](dev-council/runner/))
> that runs each advisor on a *different model family* (GPT/Codex, Claude, Gemini).
> Start at **[`dev-council/README.md`](dev-council/README.md)** for the full
> install + usage, and [`dev-council/GUIDE.md`](dev-council/GUIDE.md) for how it works.

## Usage

Once installed, invoke a skill by name or trigger phrase in Cursor. For `dev-council`:

- `council this design: ...` — challenge an approach/architecture before coding (PLAN)
- `review this with the council` — challenge an implementation before shipping (REVIEW)

For true multi-model review (not single-model), also install the runner — see
[`dev-council/README.md`](dev-council/README.md).
