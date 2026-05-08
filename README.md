# parrot-lab

> Pronunciation practice gamified. English speakers learning Spanish, with feedback that's specific — not generic.

**Status:** Early-stage but demo-ready. Single-sprite architecture, vanilla web client, real phoneme alignment on the backend.

## What it does

You see a Spanish word (or phrase). You say it. parrot-lab listens and tells you exactly what your mouth did wrong — not "try again" but "your /r/ stayed front; in Spanish it's a tap behind the teeth, here's the difference."

The bar we're aiming for: feedback that a real Spanish teacher would give if they had infinite patience and a microscope on your tongue.

## Why

Most language apps grade pronunciation as binary or scalar (pass/fail or 0–100). That tells you nothing about *how* you missed. We're going for phoneme-level diagnosis with concrete corrective hints.

## Tech stack

parrot-lab is **not** a Ruby app. (Earlier scaffolding sketched a Ruby+Sinatra server; that direction was dropped during M9 consolidation in favor of a single Python serverless deploy with a static client.)

- **Client:** Vanilla HTML + CSS + JavaScript. No framework, no build step. Lives in `web/`.
- **Backend:** Python FastAPI serverless function in `serverless/main.py`. Runs Wav2Vec2-XLSR phoneme alignment locally and calls `fal-ai/wizper` for STT. Same origin as the web client (mounts `/` as static files).
- **Data:** Static JSON files in `data/` (and `web/data/`, `serverless/data/`) — `corpus_es.json` (50 phrases), `respelling_es.json` (IPA → English-respelling lookup), `similarity_es.json` (phoneme distance matrix).
- **Deployment:** Single sprite at `parrot-lab-align-brxpk.sprites.app`. The same process serves `/align`, `/healthz`, and the web bundle at `/`. No CORS — same origin end-to-end.

### Companion packages

The respelling logic (IPA → English-spelling phonetic hint) is canonical-housed in two sibling repos so the algorithm is reusable outside parrot-lab:

- **[chunky-metro/respelling](https://github.com/chunky-metro/respelling)** — Ruby gem. Canonical implementation.
- **[chunky-metro/respelling-js](https://github.com/chunky-metro/respelling-js)** — npm package. Port for JS clients.

The static `data/respelling_es.json` shipped with parrot-lab is generated from these.

## Getting started

```bash
# Local dev — open the static client against the deployed backend (or your own)
cd web
python3 -m http.server 8000
# then visit http://localhost:8000
```

Or just open the deployed URL directly:

> **https://parrot-lab-align-brxpk.sprites.app**

For backend dev (alignment server):

```bash
cd serverless
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Attribution

Inspired by [SaulApeMan/SoundCheck-Words](https://github.com/SaulApeMan/SoundCheck-Words) — a project by a friend of the maintainer. Permission given to derive. parrot-lab is a full rewrite, not a fork; the gameplay loop and pedagogy debt is owed to SoundCheck-Words.

## License

MIT. See `LICENSE`.
