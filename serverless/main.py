"""
parrot-lab serverless: phoneme alignment FastAPI app.

M2.4 scaffold: mock /align + /healthz only. Real Wav2Vec2 + fal-ai/wizper
wiring lands in M3 (see runbooks/plans/parrot-lab-impl-plan.md §3).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


app = FastAPI(title="parrot-lab align", version="0.0.1-m2.4-mock")

# v1: wide-open CORS. Tighten to the static-bundle origin in M7 once the
# parrot.chunky.digital (or sprite-equivalent) domain is locked.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Request / response shapes ----------


class AlignRequest(BaseModel):
    audio_url: str
    audio_b64: Optional[str] = None
    expected_text: str
    expected_ipa: str
    lang: str


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
    model_version: str = Field(default="mock-m2.4")


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    timestamp: str


# ---------- Mock implementation ----------


def _mock_phonemes(expected_text: str) -> List[str]:
    """Return a deterministic phoneme list keyed off the expected text length.

    Replaced in M3 by the actual Wav2Vec2-XLSR phoneme head.
    """
    base = ["b", "w", "e", "n", "a", "s", "t", "a", "ɾ", "ð", "e", "s"]
    # Trim or pad to roughly track expected_text length so the mock isn't
    # constant for every input (helps front-end devs eyeball variations).
    target_len = max(4, min(len(expected_text), len(base)))
    return base[:target_len]


def _mock_alignment(expected: List[str], actual: List[str]) -> List[AlignmentOp]:
    ops: List[AlignmentOp] = []
    pair_count = min(len(expected), len(actual))
    for exp, act in zip(expected[:pair_count], actual[:pair_count]):
        ops.append(AlignmentOp(type="match", expected=exp, actual=act, cost=0.0))
    # Tail: drop one to simulate a deletion so consumers see a non-trivial shape.
    if len(expected) > pair_count:
        ops.append(
            AlignmentOp(type="del", expected=expected[pair_count], actual=None, cost=1.0)
        )
    return ops


@app.post("/align", response_model=AlignResponse)
def align(req: AlignRequest) -> AlignResponse:
    expected = _mock_phonemes(req.expected_text)
    actual = expected[:-1] if len(expected) > 1 else expected
    sounded_like = "MOCK: " + req.expected_text[:6]

    mistakes: List[Mistake] = []
    if len(expected) > len(actual):
        dropped = expected[-1]
        mistakes.append(
            Mistake(
                phoneme=dropped,
                expected=dropped,
                actual="",
                hint=f"missed final '{dropped}' (mock hint)",
            )
        )

    return AlignResponse(
        score=75.0,
        expected_phonemes=expected,
        actual_phonemes=actual,
        alignment=_mock_alignment(expected, actual),
        sounded_like_respelling=sounded_like,
        mistakes=mistakes,
    )


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=False,  # M3 will flip this once Wav2Vec2 is loaded at lifespan startup
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
