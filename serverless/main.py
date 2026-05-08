"""
parrot-lab serverless: phoneme alignment FastAPI app (M3 — real model).

Pipeline (per attempt):
  1. Decode audio (audio_url or audio_b64) to 16 kHz mono float32.
  2. STT via fal-ai/wizper (degraded mode if FAL_KEY missing or call fails).
  3. Phoneme extraction via Wav2Vec2-XLSR phoneme model
     (facebook/wav2vec2-lv-60-espeak-cv-ft).
  4. Phoneme diff: Levenshtein with similarity_es.json substitution costs.
  5. Score = max(0, 100 - 100 * edit_distance / max(len_expected, len_actual)).
  6. sounded_like_respelling: greedy longest-match using respelling_es.json.
  7. mistakes: english-speaker-error edits with hint descriptions.

Plan reference: runbooks/plans/parrot-lab-impl-plan.md §3 + §4.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# ---------- Logging ----------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("parrot-lab.align")


# ---------- Config ----------

PHONEME_MODEL_ID = "facebook/wav2vec2-lv-60-espeak-cv-ft"
DATA_DIR_CANDIDATES = [
    Path(__file__).parent / "data",          # serverless/data/ mirror
    Path(__file__).parent.parent / "data",   # repo-root data/ (local dev)
    Path("/app/data"),                        # docker image
]


def _find_data_dir() -> Path:
    for p in DATA_DIR_CANDIDATES:
        if p.exists() and (p / "respelling_es.json").exists():
            return p
    raise FileNotFoundError(
        f"could not locate data/ directory; tried: {[str(p) for p in DATA_DIR_CANDIDATES]}"
    )


# ---------- Module-level globals (populated in lifespan) ----------

_state: Dict[str, Any] = {
    "model_loaded": False,
    "model_load_seconds": None,
    "processor": None,
    "model": None,
    "respelling_table": None,   # list of (ipa, respelling) sorted longest-first
    "respelling_meta": None,    # raw json for stress markers etc.
    "similarity_matrix": None,  # dict[(expected, actual)] -> {cost, hint, english_speaker_error}
    "similarity_meta": None,
}


# ---------- Pydantic shapes ----------


class AlignRequest(BaseModel):
    audio_url: Optional[str] = None
    audio_b64: Optional[str] = None
    expected_text: str
    expected_ipa: str
    lang: str = "es"


class AlignmentOp(BaseModel):
    type: Literal["match", "sub", "ins", "del"]
    expected: Optional[str] = None
    actual: Optional[str] = None
    cost: float = 0.0


class Mistake(BaseModel):
    phoneme: str
    expected: str
    actual: str
    hint: str


class AlignResponse(BaseModel):
    score: float
    expected_phonemes: List[str]
    actual_phonemes: List[str]
    alignment: List[AlignmentOp]
    sounded_like_respelling: str
    mistakes: List[Mistake]
    stt_transcript: Optional[str] = None
    model_version: str = Field(default=PHONEME_MODEL_ID)
    latency_ms: int = 0
    degraded: bool = False


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_load_seconds: Optional[float] = None
    timestamp: str


# ---------- Lifespan: load model + JSON tables ----------


def _load_json_tables() -> None:
    data_dir = _find_data_dir()
    log.info("loading json tables from %s", data_dir)

    with (data_dir / "respelling_es.json").open() as f:
        resp_raw = json.load(f)
    entries = [(e["ipa"], e["respelling"]) for e in resp_raw["entries"]]
    # longest-first so greedy match doesn't shadow multi-char IPA tokens
    entries.sort(key=lambda kv: -len(kv[0]))
    _state["respelling_table"] = entries
    _state["respelling_meta"] = resp_raw

    with (data_dir / "similarity_es.json").open() as f:
        sim_raw = json.load(f)
    matrix: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in sim_raw["matrix"]:
        key = (row["expected"], row["actual"])
        matrix[key] = {
            "cost": row["cost"],
            "english_speaker_error": row.get("english_speaker_error", False),
            "description": row.get("description", ""),
        }
    _state["similarity_matrix"] = matrix
    _state["similarity_meta"] = sim_raw
    log.info(
        "loaded %d respelling entries, %d similarity rows",
        len(entries),
        len(matrix),
    )


def _load_phoneme_model() -> None:
    """Load the Wav2Vec2 phoneme model.

    NOTE: We avoid AutoProcessor / Wav2Vec2Processor because those try to
    instantiate the phonemizer-espeak backend at construction time — the
    espeak C library is required to be installed at OS level (homebrew on
    Mac, apt-get on Linux). The phonemizer is only used for training-time
    text→phoneme conversion. At inference we only need:
      - Wav2Vec2FeatureExtractor: raw waveform → input tensor
      - Wav2Vec2CTCTokenizer: CTC ids → IPA tokens
    Both load without espeak.
    """
    from transformers import (  # type: ignore
        Wav2Vec2CTCTokenizer,
        Wav2Vec2FeatureExtractor,
        Wav2Vec2ForCTC,
    )

    cache_dir = os.environ.get("MODEL_CACHE_DIR")  # honor /app/model_cache on Fly
    log.info("loading phoneme model %s (cache_dir=%s)", PHONEME_MODEL_ID, cache_dir)
    t0 = time.monotonic()
    kwargs: Dict[str, Any] = {}
    if cache_dir:
        kwargs["cache_dir"] = cache_dir
    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(PHONEME_MODEL_ID, **kwargs)
    tokenizer = Wav2Vec2CTCTokenizer.from_pretrained(PHONEME_MODEL_ID, **kwargs)
    model = Wav2Vec2ForCTC.from_pretrained(PHONEME_MODEL_ID, **kwargs)
    model.eval()
    elapsed = time.monotonic() - t0
    _state["feature_extractor"] = feature_extractor
    _state["tokenizer"] = tokenizer
    _state["model"] = model
    _state["model_load_seconds"] = round(elapsed, 2)
    _state["model_loaded"] = True
    log.info("phoneme model loaded in %.2fs", elapsed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_json_tables()
    try:
        await asyncio.to_thread(_load_phoneme_model)
    except Exception as e:  # noqa: BLE001
        log.exception("model load failed: %s", e)
        # leave model_loaded=False; /align will 503
    yield


app = FastAPI(title="parrot-lab align", version="0.1.0-m3", lifespan=lifespan)

# CORS still wide-open as a belt-and-suspenders measure (in case anyone hits
# /align cross-origin during dev). After M9 the web bundle is served from the
# same origin via StaticFiles below, so production traffic doesn't hit CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Audio fetch + decode ----------


async def _fetch_audio_bytes(req: AlignRequest) -> bytes:
    if req.audio_b64:
        try:
            return base64.b64decode(req.audio_b64)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid audio_b64: {e}")
    if req.audio_url:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(req.audio_url)
            r.raise_for_status()
            return r.content
    raise HTTPException(status_code=400, detail="must provide audio_url or audio_b64")


def _decode_to_16k_mono(audio_bytes: bytes) -> np.ndarray:
    import librosa  # type: ignore

    # librosa.load handles wav/mp3/flac/m4a via soundfile + audioread.
    # ffmpeg is required for non-wav formats — Dockerfile installs it.
    waveform, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
    return waveform.astype(np.float32)


# ---------- Phoneme extraction ----------


def _extract_phonemes(waveform: np.ndarray) -> List[str]:
    import torch  # type: ignore

    feature_extractor = _state["feature_extractor"]
    tokenizer = _state["tokenizer"]
    model = _state["model"]
    inputs = feature_extractor(waveform, sampling_rate=16000, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values).logits
    pred_ids = torch.argmax(logits, dim=-1)
    transcription = tokenizer.batch_decode(pred_ids)[0]
    # CTC decode collapses repeats but produces a single concatenated string
    # (the model's vocab tokens are individual IPA characters). Split on
    # whitespace first; if that yields a single chunk, run our IPA tokenizer
    # over it to get phoneme-level granularity matching how the expected_ipa
    # is tokenized.
    chunks = [c for c in transcription.strip().split() if c]
    if len(chunks) <= 1:
        # Use the same tokenizer as the expected IPA so the diff is comparable.
        return _tokenize_ipa(transcription)
    return chunks


# ---------- IPA tokenization ----------


# Stress + syllable markers we strip before phoneme diff, but keep around for respelling.
_STRESS_RE = re.compile(r"[ˈˌ.]")


def _tokenize_ipa(ipa: str) -> List[str]:
    """Split an IPA string into a list of phoneme tokens.

    Uses the respelling table's known IPA fragments (longest-first) as a vocabulary.
    Falls back to single-char tokens for anything not in the table.
    """
    cleaned = _STRESS_RE.sub("", ipa).replace(" ", "")
    tokens: List[str] = []
    table = _state.get("respelling_table") or []
    vocab = [k for k, _ in table]
    i = 0
    while i < len(cleaned):
        matched = None
        for v in vocab:
            if v and cleaned.startswith(v, i):
                matched = v
                break
        if matched:
            tokens.append(matched)
            i += len(matched)
        else:
            tokens.append(cleaned[i])
            i += 1
    return tokens


# ---------- Levenshtein with similarity costs ----------


def _sub_cost(expected: str, actual: str) -> Tuple[float, Dict[str, Any]]:
    if expected == actual:
        return 0.0, {"english_speaker_error": False, "description": ""}
    matrix = _state.get("similarity_matrix") or {}
    row = matrix.get((expected, actual)) or matrix.get((actual, expected))
    if row is not None:
        return row["cost"], row
    sim_meta = _state.get("similarity_meta") or {}
    return float(sim_meta.get("default_substitution_cost", 1.0)), {
        "english_speaker_error": False,
        "description": "",
    }


def _phoneme_align(
    expected: List[str],
    actual: List[str],
) -> Tuple[float, List[AlignmentOp], List[Mistake]]:
    sim_meta = _state.get("similarity_meta") or {}
    ins_cost = float(sim_meta.get("default_insertion_cost", 0.8))
    del_cost = float(sim_meta.get("default_deletion_cost", 0.8))

    n, m = len(expected), len(actual)
    # dp[i][j] = (cost, op, sub_meta) where op is one of 'match','sub','ins','del','start'
    dp: List[List[float]] = [[0.0] * (m + 1) for _ in range(n + 1)]
    back: List[List[Tuple[str, Optional[Dict[str, Any]]]]] = [
        [("start", None)] * (m + 1) for _ in range(n + 1)
    ]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + del_cost
        back[i][0] = ("del", None)
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + ins_cost
        back[0][j] = ("ins", None)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub, meta = _sub_cost(expected[i - 1], actual[j - 1])
            kind = "match" if expected[i - 1] == actual[j - 1] else "sub"
            cand_sub = dp[i - 1][j - 1] + sub
            cand_del = dp[i - 1][j] + del_cost
            cand_ins = dp[i][j - 1] + ins_cost
            best = min(cand_sub, cand_del, cand_ins)
            dp[i][j] = best
            if best == cand_sub:
                back[i][j] = (kind, meta)
            elif best == cand_del:
                back[i][j] = ("del", None)
            else:
                back[i][j] = ("ins", None)

    # Backtrace
    ops: List[AlignmentOp] = []
    mistakes: List[Mistake] = []
    i, j = n, m
    while i > 0 or j > 0:
        kind, meta = back[i][j]
        if kind in ("match", "sub"):
            exp_tok = expected[i - 1]
            act_tok = actual[j - 1]
            cost = 0.0 if kind == "match" else (meta or {}).get("cost", _sub_cost(exp_tok, act_tok)[0])
            ops.append(AlignmentOp(type=kind, expected=exp_tok, actual=act_tok, cost=float(cost)))
            if kind == "sub" and meta and meta.get("english_speaker_error"):
                mistakes.append(
                    Mistake(
                        phoneme=exp_tok,
                        expected=exp_tok,
                        actual=act_tok,
                        hint=meta.get("description", f"expected /{exp_tok}/, got /{act_tok}/"),
                    )
                )
            i -= 1
            j -= 1
        elif kind == "del":
            exp_tok = expected[i - 1]
            ops.append(AlignmentOp(type="del", expected=exp_tok, actual=None, cost=del_cost))
            # Look up insertion-of-nothing pattern (expected=X, actual="") for english_speaker_error tag
            matrix = _state.get("similarity_matrix") or {}
            row = matrix.get((exp_tok, ""))
            if row and row.get("english_speaker_error"):
                mistakes.append(
                    Mistake(
                        phoneme=exp_tok,
                        expected=exp_tok,
                        actual="",
                        hint=row.get("description", f"missed /{exp_tok}/"),
                    )
                )
            i -= 1
        elif kind == "ins":
            act_tok = actual[j - 1]
            ops.append(AlignmentOp(type="ins", expected=None, actual=act_tok, cost=ins_cost))
            matrix = _state.get("similarity_matrix") or {}
            row = matrix.get(("", act_tok))
            if row and row.get("english_speaker_error"):
                mistakes.append(
                    Mistake(
                        phoneme=act_tok,
                        expected="",
                        actual=act_tok,
                        hint=row.get("description", f"inserted /{act_tok}/"),
                    )
                )
            j -= 1
        else:
            break

    ops.reverse()
    mistakes.reverse()
    distance = dp[n][m]
    denom = max(n, m, 1)
    score = max(0.0, 100.0 - 100.0 * distance / denom)
    return score, ops, mistakes


# ---------- Respelling (sounded-like) ----------


def _render_respelling(phonemes: List[str]) -> str:
    """Greedy longest-match render of phoneme list -> English-orthography respelling.

    No syllable / stress inference here — the actual user phonemes are not
    syllable-segmented. Good enough for v1 'sounded like' display.
    """
    table = _state.get("respelling_table") or []
    flat = "".join(phonemes)
    out: List[str] = []
    i = 0
    while i < len(flat):
        matched = None
        for ipa, respelling in table:
            if ipa and flat.startswith(ipa, i):
                matched = (ipa, respelling)
                break
        if matched:
            out.append(matched[1])
            i += len(matched[0])
        else:
            out.append(flat[i])
            i += 1
    return "".join(out)


# ---------- FAL STT (wizper) ----------


async def _wizper_stt(audio_bytes: bytes, lang: str) -> Optional[str]:
    """Best-effort STT via fal-ai/wizper. Returns transcript or None on any failure."""
    if not os.environ.get("FAL_KEY"):
        log.info("FAL_KEY not set; skipping wizper STT")
        return None
    try:
        import fal_client  # type: ignore
    except Exception as e:  # noqa: BLE001
        log.warning("fal_client import failed: %s", e)
        return None

    def _run() -> Optional[str]:
        try:
            # fal_client.upload accepts bytes + content_type
            url = fal_client.upload(audio_bytes, "audio/wav")
            result = fal_client.subscribe(
                "fal-ai/wizper",
                arguments={"audio_url": url, "language": lang},
            )
            if isinstance(result, dict):
                return result.get("text") or result.get("transcript")
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("wizper subscribe failed: %s", e)
            return None

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        log.warning("wizper task failed: %s", e)
        return None


# ---------- Endpoints ----------


@app.post("/align", response_model=AlignResponse)
async def align(req: AlignRequest) -> AlignResponse:
    if not _state["model_loaded"]:
        raise HTTPException(status_code=503, detail={"error": "model loading"})

    started = time.monotonic()
    audio_bytes = await _fetch_audio_bytes(req)

    # Run STT + decode in parallel; if STT fails we degrade gracefully.
    stt_task = asyncio.create_task(_wizper_stt(audio_bytes, req.lang))
    waveform = await asyncio.to_thread(_decode_to_16k_mono, audio_bytes)
    actual_phonemes = await asyncio.to_thread(_extract_phonemes, waveform)
    stt_transcript = await stt_task

    expected_phonemes = _tokenize_ipa(req.expected_ipa)

    score, ops, mistakes = _phoneme_align(expected_phonemes, actual_phonemes)
    sounded_like = _render_respelling(actual_phonemes)

    return AlignResponse(
        score=round(score, 2),
        expected_phonemes=expected_phonemes,
        actual_phonemes=actual_phonemes,
        alignment=ops,
        sounded_like_respelling=sounded_like,
        mistakes=mistakes,
        stt_transcript=stt_transcript,
        model_version=PHONEME_MODEL_ID,
        latency_ms=int((time.monotonic() - started) * 1000),
        degraded=stt_transcript is None,
    )


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=bool(_state["model_loaded"]),
        model_load_seconds=_state["model_load_seconds"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------- Static web bundle (M9 consolidation) ----------
#
# The web client (HTML/JS/CSS + data/*.json) is mounted at "/" so it is served
# from the SAME origin as /align. This eliminates the cross-origin call that
# was triggering Safari "Failed to fetch" CORS errors when the web bundle was
# hosted on a separate sprite (parrot-lab-web). Single sprite = no CORS.
#
# Mount LAST so /align and /healthz take precedence over static routes.
_WEB_DIR_CANDIDATES = [
    Path(__file__).parent / "web",          # serverless/web/ (docker image)
    Path(__file__).parent.parent / "web",   # repo-root web/ (local dev)
]
for _web_dir in _WEB_DIR_CANDIDATES:
    if _web_dir.exists() and (_web_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
        log.info("mounted web bundle at / from %s", _web_dir)
        break
else:
    log.warning("no web bundle found; / will 404. Tried: %s",
                [str(p) for p in _WEB_DIR_CANDIDATES])
