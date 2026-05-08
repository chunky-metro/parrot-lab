# Sprite deploy — parrot-lab-align

**Live URL:** https://parrot-lab-align-brxpk.sprites.app (auth: public)
**Deployed:** 2026-05-08
**Why sprite, not Fly.io direct:** Fleet already runs Kit + Iris on sprites.dev. One operational surface, pre-authed (`sprite org list` shows `matt-culpepper`), idle-to-zero same as Fly. Sprite-deploy SKILL.md confirms generic FastAPI services fit the `setup.sh + start.sh + service-register` pattern — identity injection is optional.

## One-time deploy steps (verified 2026-05-08)

```bash
# 1. Create the sprite
sprite create parrot-lab-align
sprite use parrot-lab-align

# 2. Install system deps (apt)
sprite exec -- bash -c '
  sudo apt-get install -y ffmpeg libsndfile1 espeak-ng \
    python3.13 python3.13-dev python3-venv libbz2-dev
'

# 3. Upload source (tar from host -> sprite stdin)
cd /opt/repos/chunky-metro/parrot-lab
tar czf - --exclude='__pycache__' --exclude='*.pyc' \
  serverless/main.py serverless/requirements.txt serverless/data data \
  | sprite exec -- bash -c '
    mkdir -p /home/sprite/parrot-lab && cd /home/sprite/parrot-lab && tar xzf -
  '

# 4. Build venv with system Python (NOT sprite's pyenv Python — see gotcha below)
sprite exec -- bash -c '
  /usr/bin/python3 -m venv /home/sprite/parrot-lab/.venv
  /home/sprite/parrot-lab/.venv/bin/pip install -r /home/sprite/parrot-lab/serverless/requirements.txt
'

# 5. Set env vars in ~/.profile (idempotent on rerun)
sprite exec -- bash -c "
  echo 'export FAL_KEY=$FAL_KEY' >> ~/.profile
  echo 'export MODEL_CACHE_DIR=/home/sprite/parrot-lab/model_cache' >> ~/.profile
  mkdir -p /home/sprite/parrot-lab/model_cache
"

# 6. Write start.sh and register sprite service
sprite exec -- bash -c '
  cat > /home/sprite/parrot-lab/start.sh << "EOF"
#!/bin/bash
set -e
source ~/.profile 2>/dev/null || true
cd /home/sprite/parrot-lab/serverless
exec /home/sprite/parrot-lab/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080
EOF
  chmod +x /home/sprite/parrot-lab/start.sh
  sprite-env curl -s -X PUT /v1/services/parrot-lab \
    -d '"'"'{"cmd": "/home/sprite/parrot-lab/start.sh", "args": [], "needs": [], "http_port": 8080}'"'"'
  sprite-env services start parrot-lab
'

# 7. Public URL access
sprite url update --auth public
```

## Verification (2026-05-08)

- `GET /healthz` → `{"status":"ok","model_loaded":true,"model_load_seconds":18.93}` (warm; cold-start 202.83s)
- `POST /align` with macOS `say -v Paulina "Hola, ¿cómo estás?"` (16k mono wav, base64) →
  - score: 77.78
  - expected_phonemes: `['ol','a','k','o','m','o','es','t','as']`
  - actual_phonemes: `['ol','a','k','o','m','ɑ','is','t','as']`
  - sounded_like: `ohlahkohmɑeestahs`
  - stt_transcript: `Hola, ¿cómo estás?` (FAL wizper, degraded:false)
  - latency_ms: 28816 (first request after wakeup; warm calls should be ~1-3s)

## Gotchas (worth recording)

1. **Sprite's pyenv-built Python 3.13 is missing `_bz2`** — `pooch` (a librosa transitive dep) imports bz2 at module-load, which crashes with `ModuleNotFoundError: No module named '_bz2'` on every `/align` call. Fix: install OS package `libbz2-dev`, then build a venv against `/usr/bin/python3` (the apt-installed system Python, which has bz2 baked in). Don't use the sprite's default `/.sprite/bin/python3`.
2. **`sprite url update --auth public`** — sprite URLs default to `Auth: sprite` (browser-only via Fly OAuth). Programmatic `curl /healthz` will hit a redirect to `sprites.dev/auth/sprite?...` until you flip auth to public.
3. **Cold-start cost:** first model load downloads ~1GB Wav2Vec2 weights from HuggingFace (~3.4 min). Subsequent restarts hit the on-disk cache (~19s). The `MODEL_CACHE_DIR=/home/sprite/parrot-lab/model_cache` env var is what makes this stick.
4. **No Docker on sprite** — that's fine, the FastAPI app runs directly under uvicorn. Dockerfile in this dir is for Fly.io / future container runtimes; sprites use the `setup.sh` + `sprite-env services` pattern.

## Cost estimate

Per sprite-deploy SKILL.md: idle-mostly web service ~$1.89/mo. Per-request CPU is `$0.07/CPU-hour` × ~0.5 CPU × ~3s = ~$0.00003 per /align call. Storage for model_cache (~1.2GB hot) ≈ $0.025/mo.

## Restart / debugging

```bash
sprite use parrot-lab-align
sprite exec -- bash -c 'sprite-env services restart parrot-lab'
sprite exec -- bash -c 'tail -50 /.sprite/logs/services/parrot-lab.log'
```
