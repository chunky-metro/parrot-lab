# AGENTS.md — parrot-lab

Roster of agents that should be used when working in this repo. Each agent has a defined surface; don't ask the wrong one.

## Roster

### `ruby-builder`
Implements Ruby code per Sandi Metz rules. Owns Sinatra routes, models, services. Writes specs alongside code. Stops at green tests + manual verification.

### `reviewer`
Proof-gate before merge. Verifies:
- Tests pass (RSpec green)
- Manual verification ran (with receipts — curl output, screenshot, or recorded smoke run)
- Acceptance criteria from the Linear issue are met

If any of those is missing, reviewer rejects and routes back to the implementer.

### `forge`
Second-opinion code review. Independent of `reviewer` — focuses on design quality, idiom adherence, test coverage shape. Catches things the implementer and the proof-gate both missed.

### `slop-cleaner`
Pre-merge cleanup pass. Scans for:
- Backwards-compat shims for code that was never released
- "Removed because X" comments instead of just removing
- `except: pass` / `rescue => e; nil` swallowed errors
- Premature abstractions (one-implementation interfaces)
- Dead imports, stale TODOs, no-op shims

Reports findings; does not auto-fix in phase 1.

### `linear-keeper`
Keeps the Linear board honest. After every meaningful change:
- Updates issue status (todo → in-progress → done)
- Adds a comment with PR/commit links
- Surfaces blockers to the project description if they're load-bearing

If Linear and reality disagree, linear-keeper updates Linear, not reality.

### `discord-voice`
Posts milestones to the parrot-lab Discord thread. Style: one line, plain English, link the PR or commit. Does not announce intent — only shipped state.

## Working pattern

1. `linear-keeper` claims an issue (status → in-progress)
2. `ruby-builder` implements + writes specs
3. `slop-cleaner` scans the diff
4. `reviewer` proof-gates
5. `forge` second-opinions
6. Merge
7. `linear-keeper` closes the issue
8. `discord-voice` posts the milestone if the work is user-facing or fleet-relevant

Skip steps when proportional. A typo fix doesn't need forge + slop-cleaner.
