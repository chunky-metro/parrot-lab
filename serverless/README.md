# parrot-lab serverless: phoneme alignment

FastAPI service. Takes a recorded utterance, returns phoneme-level scoring + native-tongue respelling of what the user actually sounded like.

Pipeline (per request):

1. Decode audio (`audio_url` or `audio_b64`) to 16 kHz mono float32.
2. STT via `fal-ai/wizper` (skipped if `FAL_KEY` unset; pipeline degrades gracefully).
3. Phoneme extraction via `facebook/wav2vec2-lv-60-espeak-cv-ft` (CTC head, IPA tokens).
4. Phoneme diff: Levenshtein with `data/similarity_es.json` substitution costs.
5. Score = `max(0, 100 - 100 * edit_distance / max(len_expected, len_actual))`.
6. `sounded_like_respelling`: greedy longest-match render via `data/respelling_es.json`.
7. `mistakes`: subset of edits tagged `english_speaker_error: true` with hint descriptions.

Plan reference: `runbooks/plans/parrot-lab-impl-plan.md` §3 + §4.

## Run locally (real model)

    cd serverless
    /opt/homebrew/bin/python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    # one-time: pre-download the Wav2Vec2 phoneme model (~1GB)
    python -c "from transformers import AutoProcessor, AutoModelForCTC; \
      AutoProcessor.from_pretrained('facebook/wav2vec2-lv-60-espeak-cv-ft'); \
      AutoModelForCTC.from_pretrained('facebook/wav2vec2-lv-60-espeak-cv-ft')"

    # source FAL key for STT (optional — service degrades gracefully without it)
    set -a; source /Users/vox/vox-agent/.env; set +a

    uvicorn main:app --port 8080
    # cold-start: model load ~30-45s on Mac Mini M-series
    # warm: < 100ms /align response on short clips

Generate a sample wav and round-trip it:

    say -o /tmp/sample.aiff "Buenos días"
    ffmpeg -y -i /tmp/sample.aiff -ar 16000 -ac 1 /tmp/sample.wav
    B64=$(base64 -i /tmp/sample.wav)
    curl -s -X POST http://localhost:8080/align \
      -H 'content-type: application/json' \
      -d "{\"audio_b64\":\"$B64\",\"expected_text\":\"Buenos días\",\"expected_ipa\":\"ˈbwe.nos ˈði.as\",\"lang\":\"es\"}" \
      | python -m json.tool

Healthz (returns `model_loaded: true` once lifespan finishes):

    curl http://localhost:8080/healthz

## Tests

    cd serverless
    source .venv/bin/activate
    pytest tests/                                  # schema tests only
    GATE_FUNCTIONAL_TESTS=1 pytest tests/          # also runs the real-audio smoke test

The functional class needs `tests/fixtures/buenos_dias.wav`. Generate it via the macOS `say` + `ffmpeg` recipe in `tests/test_align.py`.

## Data files (dual-location)

JSON tables live in two places:

- **`data/` at the repo root** — canonical, versioned, source of truth.
- **`serverless/data/`** — build-time mirror copied for the Docker build context.

The mirror exists because `Dockerfile`'s `COPY . .` only sees inside `serverless/`. Keeping the mirror checked in is simpler than a multi-stage build, a `.dockerignore` dance, or a symlink that breaks on case-insensitive filesystems. When you update `data/*.json`, also `cp data/*.json serverless/data/`. Future v2: replace with a Makefile target or build-step rsync.

The runtime resolves whichever exists first:

```
serverless/data/  →  ../data/  →  /app/data/  (in container)
```

## M7 deploy steps

    # one-time: create the persistent volume for the model cache
    fly volumes create model_cache --size 5 --region iad

    # set FAL_KEY as a Fly secret (do NOT commit it to fly.toml)
    fly secrets set FAL_KEY="$FAL_KEY"

    # deploy
    fly deploy

Memory: 4 GB. VM size: `performance-1x` (1 dedicated vCPU). Cold-start: ~30-45s for model load (first request after machine wake). Warm p50: <500ms.

Once warmed, set `min_machines_running = 1` in `fly.toml` to keep one machine hot 24/7 (~$3-5/mo). Disabled during M3 wiring to avoid burn while the eval harness is still landing.

## Architecture (M3 wired)

    /align  →  fal-ai/wizper STT  →  Wav2Vec2-XLSR phoneme extract  →  diff vs expected_ipa  →  respell + score
