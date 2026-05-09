#!/usr/bin/env python3
"""parrot-lab — 50-phrase reliability sweep eval harness.

Loads the canonical Spanish corpus (`data/corpus_es.json`, 50 entries) and
exercises the live `/align` endpoint to surface failure modes across the
full corpus instead of the 1-2 phrases a manual run touches.

Failure categories (output buckets):
  - alignment_failure: HTTP error, 503 model loading, 5xx, JSON shape error
  - stt_missing:      `degraded=true` AND no `stt_transcript` (audio gate
                       rejected the input or wizper failed)
  - score_outlier:    score < 30 on a SUPPOSEDLY-clean utterance OR
                       score == 0 (suggests phoneme pipeline collapse)
  - ipa_leak:         user-facing strings (`stt_transcript`,
                       `sounded_like_respelling`, mistake hints) contain
                       known-leaky IPA chars (ː ˈ ˌ ʉ ʌ æ ɑ ɛ ɪ ʊ ə ɜ ʃ ʒ ɲ)
  - mistake_dup:      mistakes list contains identical (phoneme, hint) pairs
  - ok:               score ≥ 30 AND no leak AND no dup

Audio source:
  - --mode tts:    use macOS `say` to render each phrase to a wav fixture
                    (default; offline, free, ~120s for 50 phrases)
  - --mode wizper: skip TTS, post a tiny silent wav per phrase. Cheaper
                    but only exercises the audio-gate + STT-degraded paths.
                    Useful for verifying the audio-gate fix without burning
                    wizper budget.
  - --mode fixtures: read pre-existing wavs from `tests/fixtures/<phrase_id>.wav`
                    (skip the phrase if missing).

Output:
  - JSON report at `evals/reports/sweep-<timestamp>.json`
  - Console summary table

Run:
  python evals/50_phrase_sweep.py --mode tts --limit 5  # smoke test
  python evals/50_phrase_sweep.py --mode tts            # full sweep
  python evals/50_phrase_sweep.py --mode wizper         # gate-only sweep
  python evals/50_phrase_sweep.py --base-url http://localhost:8080  # local
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import urllib.error
import urllib.request


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "data" / "corpus_es.json"
DEFAULT_BASE_URL = "https://parrot-lab-align-brxpk.sprites.app"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"

# IPA chars that should never appear in user-facing strings post-M9.3 fix
LEAKY_IPA_CHARS = set("ːˈˌʉʌæɑɛɪʊəɜʃʒɲ.|–—")

# Score floor for "this should have at least sort of worked" — TTS audio is
# clean and on-topic so anything below this is a phoneme pipeline issue.
MIN_OK_SCORE = 30.0


# ---------- Audio sources ----------


def synthesize_say(phrase_text: str, out_wav: Path) -> bool:
    """Use macOS `say` + `ffmpeg` to render TTS to 16kHz mono wav.

    Returns False on any failure (caller should treat as `alignment_failure`).
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    aiff_path = out_wav.with_suffix(".aiff")
    try:
        subprocess.run(
            ["say", "-v", "Mónica", "-o", str(aiff_path), phrase_text],
            check=True,
            capture_output=True,
            timeout=20,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel", "error",
                "-i", str(aiff_path),
                "-ar", "16000",
                "-ac", "1",
                str(out_wav),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
    finally:
        if aiff_path.exists():
            aiff_path.unlink()


def synthesize_silent(out_wav: Path, duration_s: float = 0.3) -> bool:
    """Write a short silent wav (deliberately below the 0.5s audio gate
    floor — used to verify the gate rejects bad input).
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    samples = int(16000 * duration_s)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * samples)
    return True


def load_fixture(phrase_id: str) -> Optional[Path]:
    fixture = REPO_ROOT / "serverless" / "tests" / "fixtures" / f"{phrase_id}.wav"
    return fixture if fixture.exists() else None


# ---------- API client ----------


def post_align(base_url: str, audio_path: Path, phrase: Dict[str, Any], timeout: float = 60.0) -> Tuple[int, Dict[str, Any]]:
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
    body = json.dumps({
        "audio_b64": audio_b64,
        "expected_text": phrase["text"],
        "expected_ipa": phrase["ipa"],
        "lang": "es",
    }).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/align",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = {"detail": str(e)}
        return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


# ---------- Per-phrase classification ----------


def classify(phrase: Dict[str, Any], status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Return a verdict dict: {category, reasons, summary fields}."""
    out = {
        "phrase_id": phrase["id"],
        "text": phrase["text"],
        "category": "ok",
        "reasons": [],
        "score": None,
        "stt_transcript": None,
        "sounded_like": None,
        "degraded": None,
        "n_mistakes": 0,
        "http_status": status,
    }

    if status >= 500 or status == 0:
        out["category"] = "alignment_failure"
        out["reasons"].append(f"http_{status}: {body.get('error') or body.get('detail') or 'unknown'}")
        return out
    if status >= 400:
        out["category"] = "alignment_failure"
        out["reasons"].append(f"http_{status}: {body.get('detail') or 'client error'}")
        return out

    out["score"] = body.get("score")
    out["stt_transcript"] = body.get("stt_transcript")
    out["sounded_like"] = body.get("sounded_like_respelling")
    out["degraded"] = body.get("degraded")
    mistakes = body.get("mistakes") or []
    out["n_mistakes"] = len(mistakes)

    # IPA leak detection
    leak_strings = []
    for label, val in (
        ("stt_transcript", out["stt_transcript"]),
        ("sounded_like", out["sounded_like"]),
    ):
        if val and any(ch in LEAKY_IPA_CHARS for ch in val):
            leak_strings.append(f"{label}: {val!r}")
    for m in mistakes:
        hint = m.get("hint") or ""
        if any(ch in LEAKY_IPA_CHARS for ch in hint):
            leak_strings.append(f"mistake.hint: {hint!r}")
    if leak_strings:
        out["category"] = "ipa_leak"
        out["reasons"].extend(leak_strings)

    # Mistake duplication
    mistake_keys = [(m.get("phoneme"), m.get("expected"), m.get("actual"), m.get("hint")) for m in mistakes]
    if len(mistake_keys) != len(set(mistake_keys)):
        out["category"] = "mistake_dup"
        dup_set = {k for k in mistake_keys if mistake_keys.count(k) > 1}
        out["reasons"].append(f"duplicate mistakes: {sorted(dup_set)}")

    # STT missing on what should be clean TTS audio
    if out["degraded"] and not out["stt_transcript"]:
        if out["category"] == "ok":
            out["category"] = "stt_missing"
        out["reasons"].append("stt degraded + no transcript")

    # Score outlier
    if out["score"] is not None and out["score"] < MIN_OK_SCORE:
        if out["category"] == "ok":
            out["category"] = "score_outlier"
        out["reasons"].append(f"score {out['score']} < {MIN_OK_SCORE}")

    return out


# ---------- Driver ----------


def run_sweep(
    base_url: str,
    mode: str,
    limit: Optional[int],
    audio_cache_dir: Path,
) -> Dict[str, Any]:
    corpus = json.loads(CORPUS_PATH.read_text())
    if limit:
        corpus = corpus[:limit]

    results: List[Dict[str, Any]] = []
    started = time.time()
    audio_cache_dir.mkdir(parents=True, exist_ok=True)

    for i, phrase in enumerate(corpus, 1):
        pid = phrase["id"]
        wav_path = audio_cache_dir / f"{pid}.wav"

        # Resolve audio source
        if mode == "tts":
            if not wav_path.exists():
                if not synthesize_say(phrase["text"], wav_path):
                    results.append({
                        "phrase_id": pid, "text": phrase["text"],
                        "category": "alignment_failure",
                        "reasons": ["tts synthesis failed"],
                        "score": None, "stt_transcript": None,
                        "sounded_like": None, "degraded": None, "n_mistakes": 0,
                        "http_status": -1,
                    })
                    print(f"[{i}/{len(corpus)}] {pid}: TTS-FAIL", flush=True)
                    continue
        elif mode == "wizper":
            synthesize_silent(wav_path)  # short silent input — exercises gate
        elif mode == "fixtures":
            fix = load_fixture(pid)
            if fix is None:
                results.append({
                    "phrase_id": pid, "text": phrase["text"],
                    "category": "alignment_failure",
                    "reasons": [f"fixture missing: tests/fixtures/{pid}.wav"],
                    "score": None, "stt_transcript": None,
                    "sounded_like": None, "degraded": None, "n_mistakes": 0,
                    "http_status": -1,
                })
                print(f"[{i}/{len(corpus)}] {pid}: NO-FIXTURE", flush=True)
                continue
            wav_path = fix
        else:
            raise SystemExit(f"unknown mode: {mode!r}")

        status, body = post_align(base_url, wav_path, phrase)
        verdict = classify(phrase, status, body)
        results.append(verdict)
        score_str = f"{verdict['score']:5.1f}" if isinstance(verdict["score"], (int, float)) else "  - "
        print(
            f"[{i}/{len(corpus)}] {pid}: {verdict['category']:20s} "
            f"score={score_str} stt={verdict['stt_transcript']!r}",
            flush=True,
        )

    elapsed = time.time() - started

    # Aggregate
    by_category: Dict[str, int] = {}
    for r in results:
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1

    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "mode": mode,
        "n_phrases": len(corpus),
        "elapsed_seconds": round(elapsed, 1),
        "by_category": by_category,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"align endpoint base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--mode", choices=("tts", "wizper", "fixtures"), default="tts",
                        help="audio source — tts (macOS say), wizper (silent gate-test), or fixtures")
    parser.add_argument("--limit", type=int, default=None,
                        help="only run the first N phrases (smoke test)")
    parser.add_argument("--audio-cache", type=Path, default=REPO_ROOT / "evals" / ".audio-cache",
                        help="where to cache TTS-generated wavs")
    parser.add_argument("--report-out", type=Path, default=None,
                        help="JSON report path (default: evals/reports/sweep-<ts>.json)")
    args = parser.parse_args()

    if not CORPUS_PATH.exists():
        print(f"ERROR: corpus not found at {CORPUS_PATH}", file=sys.stderr)
        return 1

    report = run_sweep(args.base_url, args.mode, args.limit, args.audio_cache)

    report_path = args.report_out or (
        REPORTS_DIR / f"sweep-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Console summary
    print()
    print("=" * 60)
    print(f"sweep complete in {report['elapsed_seconds']}s")
    print(f"phrases:   {report['n_phrases']}")
    print(f"mode:      {report['mode']}")
    print(f"base_url:  {report['base_url']}")
    print(f"report:    {report_path}")
    print()
    print("by category:")
    for cat, n in sorted(report["by_category"].items(), key=lambda kv: -kv[1]):
        print(f"  {cat:20s} {n}")

    # Exit non-zero if anything was not "ok" — useful for CI gating
    if report["by_category"].get("ok", 0) < report["n_phrases"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
