# parrot-lab

> Pronunciation practice gamified. English speakers learning Spanish, with feedback that's specific — not generic.

**Status:** Early scaffolding. v1 target: web-first pronunciation drills, English → Spanish.

## What it does

You see a Spanish word (or phrase). You say it. parrot-lab listens and tells you exactly what your mouth did wrong — not "try again" but "your /r/ stayed front; in Spanish it's a tap behind the teeth, here's the difference."

The bar we're aiming for: feedback that a real Spanish teacher would give if they had infinite patience and a microscope on your tongue.

## Why

Most language apps grade pronunciation as binary or scalar (pass/fail or 0–100). That tells you nothing about *how* you missed. We're going for phoneme-level diagnosis with concrete corrective hints.

## Tech stack

- **Server:** Ruby + Sinatra
- **Client:** vanilla JS (Web Audio API for capture)
- **Phoneme analysis:** Python sidecar (whatever forced-aligner / phoneme classifier ends up most accurate — Allosaurus, wav2vec2, or similar)
- **Speech synthesis / scoring helpers:** FAL APIs as needed (TTS reference audio, possibly speech-to-phoneme models if they outperform local sidecar)

## Getting started

*(Setup instructions land here once the bones exist. For now: this is scaffolding.)*

## Attribution

Inspired by [SaulApeMan/SoundCheck-Words](https://github.com/SaulApeMan/SoundCheck-Words) — a project by a friend of the maintainer. Permission given to derive. parrot-lab is a full rewrite, not a fork; the gameplay loop and pedagogy debt is owed to SoundCheck-Words.

## License

MIT. See `LICENSE`.
