"""Tests for the M3 /align endpoint.

Two classes:
  - TestAlignSchema: runs against the live FastAPI app with TestClient. The
    model load happens in lifespan, so these are slow on first run (~30-45s
    cold) but fast thereafter (cached weights). Asserts the response shape
    is correct regardless of mock-vs-real.

  - TestAlignFunctional: gated behind GATE_FUNCTIONAL_TESTS env var. Hits
    /align with a real TTS-generated wav and asserts score > 0 and that the
    actual_phonemes list is non-empty. Skipped in CI by default; run locally
    after generating tests/fixtures/buenos_dias.wav.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    # TestClient runs lifespan on enter, so the model loads here once.
    with TestClient(app) as c:
        yield c


class TestAlignSchema:
    def test_healthz_ok(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert isinstance(body["model_loaded"], bool)
        assert "timestamp" in body and body["timestamp"]

    def test_align_400_when_no_audio(self, client):
        # No audio_url + no audio_b64 → 400
        r = client.post(
            "/align",
            json={
                "expected_text": "Hola",
                "expected_ipa": "ˈo.la",
                "lang": "es",
            },
        )
        # 400 only fires after model loaded; if model failed to load we'd see 503.
        assert r.status_code in (400, 503)

    def test_align_response_shape(self, client):
        """Use a tiny silent wav. We don't assert score, just shape."""
        # 1 second of silence at 16kHz mono, 16-bit PCM = ~32KB
        import io
        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 16000)
        b64 = base64.b64encode(buf.getvalue()).decode()

        r = client.post(
            "/align",
            json={
                "audio_b64": b64,
                "expected_text": "Buenos días",
                "expected_ipa": "ˈbwe.nos ˈði.as",
                "lang": "es",
            },
        )
        if r.status_code == 503:
            pytest.skip("model not loaded in this environment")
        assert r.status_code == 200, r.text
        body = r.json()
        # Required shape per AlignResponse
        for k in (
            "score",
            "expected_phonemes",
            "actual_phonemes",
            "alignment",
            "sounded_like_respelling",
            "mistakes",
            "model_version",
            "latency_ms",
        ):
            assert k in body, f"missing key {k}"
        assert isinstance(body["expected_phonemes"], list)
        assert isinstance(body["actual_phonemes"], list)
        assert isinstance(body["alignment"], list)
        assert isinstance(body["mistakes"], list)
        assert 0 <= body["score"] <= 100


@pytest.mark.skipif(
    not os.environ.get("GATE_FUNCTIONAL_TESTS"),
    reason="set GATE_FUNCTIONAL_TESTS=1 to run; needs sample audio",
)
class TestAlignFunctional:
    """Real-audio smoke test — requires tests/fixtures/buenos_dias.wav.

    Generate locally:
        say -o /tmp/sample.aiff "Buenos días"
        ffmpeg -y -i /tmp/sample.aiff -ar 16000 -ac 1 \\
          serverless/tests/fixtures/buenos_dias.wav
    """

    def test_buenos_dias_scores_above_zero(self, client):
        fixture = Path(__file__).parent / "fixtures" / "buenos_dias.wav"
        if not fixture.exists():
            pytest.skip(f"missing fixture {fixture}")
        b64 = base64.b64encode(fixture.read_bytes()).decode()
        r = client.post(
            "/align",
            json={
                "audio_b64": b64,
                "expected_text": "Buenos días",
                "expected_ipa": "ˈbwe.nos ˈði.as",
                "lang": "es",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["score"] > 0
        assert len(body["actual_phonemes"]) > 0
        assert body["sounded_like_respelling"]
