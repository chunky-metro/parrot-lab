FROM python:3.11-slim

WORKDIR /app

# System deps:
#   - ffmpeg + libsndfile1: required by librosa/soundfile/audioread for codec decode
#   - build-essential: needed for some torch transitive wheels on linux/arm64
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      libsndfile1 \
      build-essential \
      espeak-ng \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source + the data/ mirror (canonical lives at repo root data/; we keep
# a duplicate inside serverless/data/ so the docker build context stays scoped
# to serverless/. See README "Data files" for the dual-location rationale.)
COPY . .

# Wav2Vec2 model cache. fly.toml mounts a volume here so model survives
# machine restarts; locally falls back to in-image cache.
ENV MODEL_CACHE_DIR=/app/model_cache
RUN mkdir -p /app/model_cache

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
