"""Smoke tests for the M2.4 mock serverless surface."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_healthz_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is False
    assert "timestamp" in body and body["timestamp"]


def test_align_returns_mock_shape():
    payload = {
        "audio_url": "https://example/x.webm",
        "audio_b64": None,
        "expected_text": "Buenos días",
        "expected_ipa": "ˈbweno̞s ˈði.as",
        "lang": "es",
    }
    r = client.post("/align", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 75.0
    assert isinstance(body["expected_phonemes"], list) and body["expected_phonemes"]
    assert isinstance(body["actual_phonemes"], list)
    assert isinstance(body["alignment"], list) and body["alignment"]
    assert body["sounded_like_respelling"].startswith("MOCK: ")
    assert isinstance(body["mistakes"], list)
    # alignment ops conform to allowed types
    allowed_types = {"match", "sub", "ins", "del"}
    for op in body["alignment"]:
        assert op["type"] in allowed_types
