# CLAUDE.md — parrot-lab

## Project context

parrot-lab is a pronunciation-practice web app. v1 is English speakers learning Spanish. The gameplay loop: see a target word/phrase, record yourself saying it, get phoneme-level feedback ("your /r/ went front, the Spanish tap is behind the teeth"). Inspired by SaulApeMan/SoundCheck-Words (full rewrite, permission given). The thesis: feedback should be specific, not generic.

## Domain

Pronunciation, phoneme analysis, speech audio. Forced alignment, IPA, articulatory phonetics. Not a chat app, not a flashcard app.

## Stack

- Ruby + Sinatra (server)
- Vanilla JS + Web Audio API (client)
- Python sidecar for phoneme analysis (Allosaurus / wav2vec2 / similar TBD)
- FAL APIs for TTS reference audio and possibly STT

## Conventions

- **Ruby code follows Sandi Metz rules:** classes ≤ 100 lines, methods ≤ 5 lines, ≤ 4 parameters per method, one instance variable per controller action.
- **BigDecimal for any scoring.** Floats lie about decimals; phoneme similarity scores get aggregated, so we want exact arithmetic.
- **RSpec for tests.** No Minitest. New code lands with specs.
- **No premature abstractions.** Build the concrete first. Extract when you have three.
- **Audio fixtures stay small.** Reference clips for tests must be < 100KB; longer fixtures live outside the repo.

## How to run locally

*(Placeholder — bin/dev once the app has bones.)*

## How to test

*(Placeholder — `bundle exec rspec` once specs exist.)*

## Surface boundaries

- **Linear project:** TBD (will be filled in by linear-keeper after bootstrap)
- **Notion page:** TBD (will be filled in after the project DB row is created)
- **Discord thread:** TBD (in #fleet-command, channel ID 1480012767191760967)

When you finish a meaningful chunk of work, post a one-line update to the Discord thread and tick the Linear issue. Don't ship silent.
