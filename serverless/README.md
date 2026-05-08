# parrot-lab serverless: phoneme alignment

FastAPI service that takes a recorded utterance and returns phoneme-level scoring + native-tongue respelling of what the user actually sounded like.

## Run locally

    cd serverless
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8080

Test the mock /align:

    curl -X POST http://localhost:8080/align \
      -H 'content-type: application/json' \
      -d '{"audio_url":"https://example/x.webm","expected_text":"Buenos días","expected_ipa":"ˈbweno̞s ˈði.as","lang":"es"}'

Healthz:

    curl http://localhost:8080/healthz

## Deploy (M3, not yet)

`fly launch` then `fly deploy`. Config in fly.toml. Memory needs bump to ≥4GB once Wav2Vec2 model lands.

## Architecture (M3 wire-up)

    /align  →  fal-ai/wizper STT  →  Wav2Vec2-XLSR phoneme extract  →  diff vs expected_ipa  →  respell + score
