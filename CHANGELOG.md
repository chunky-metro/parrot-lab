# Changelog

All notable changes to parrot-lab. Newest first. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), with milestone codes (M2/M3/M9.X)
matching the implementation plan and Discord ship-messages.

## [Unreleased] — `feat/overnight-fixes-2026-05-09`

### Fixed (overnight 2026-05-09 lane)

- **STT ghost-recognition** (`da83b27`): wizper was hallucinating plausible
  transcripts on near-empty/cutoff audio (e.g. returning "Gracias." for
  silence). Added `_audio_quality_ok` gate (duration ≥ 0.5s AND RMS ≥ 0.005)
  that skips STT entirely on bad input. Client now shows "(recording too
  short or unclear — try again)" via the new low-score+degraded branch in
  `score.js` instead of a fabricated string.
- **STT numerals** (`da83b27`): wizper auto-normalized spoken Spanish
  numerals to digits ("cuatro" → "4"), surfacing as "you said: 4 5 6".
  Added `_despeakerize_numerals` post-processor that maps digits back to
  Spanish word forms when the expected text is digit-free. Lookup covers
  0-29, tens to 90, plus 100/1000 (corpus only goes to 20).
- **Mistakes-list duplication** (`da83b27`): the same hint was being
  emitted twice for phrases with repeated phonemes. Added dedup pass in
  `_phoneme_align` keyed by `(phoneme, expected, actual, hint)`.

### Added (overnight 2026-05-09 lane)

- **`evals/50_phrase_sweep.py`** (`1dbbab1`): reliability harness exercising
  the live `/align` across all 50 phrases. Three modes (tts / wizper /
  fixtures), JSON report output, exit code 2 if any non-ok verdict
  (CI-gateable). Catches ipa_leak / mistake_dup / score_outlier /
  stt_missing / alignment_failure regressions.
- **`serverless/tests/test_overnight_fixes.py`** (`da83b27`): 17 unit
  tests covering the new helpers — numeral despeakerization, audio gate,
  mistakes dedup, lookup completeness.
- **`CHANGELOG.md`** (this file).

### Changed

- HTML cache-bust bumped `v=m9g` → `v=m9h` so the new score.js fetches fresh.

### Discord context

Original bug reports: msg [1502382610452582533](https://discord.com/channels/1467324435269685422/1483979442421235774/1502382610452582533)
("Weirdness. The first one I definitely didn't say gracias…")

---

## M9.3 — 2026-05-08 (`0bfe570`)

### Fixed

- **IPA leak in "you said"** — wav2vec2 phoneme model was emitting raw IPA
  stress/length/separator markers (ː ˈ ˌ . – —) AND English-leaning
  phonemes (ʉ ʌ æ ɑ ɛ ɪ ʊ ə) that had no entry in the Spanish-only
  respelling table. User saw `tohndayːstʉstaytʌn–dayːstayrrlbænoh`.
  Two-part fix:
  - Server: strip stress/length/separator markers via `_NOISE_RE` before
    respelling render
  - Server: English-fallback table (ʉ→oo, ʌ→uh, æ→a, ʃ→sh, etc.) for the
    English-substitution case
  - Client: prefer wizper STT for "you said" line, fall back to phonetic
    respelling only when STT degrades

### Discord context

ship msg [1502380019727470672](https://discord.com/channels/1467324435269685422/1483979442421235774/1502380019727470672)

---

## M9f — 2026-05-08 (`86bcf05`)

### Changed

- Promote respelling to the headline visual element (large monospace
  amber). Demote Spanish text to a label-prefixed line ("spelled: …").

## M9e — 2026-05-08 (`b69e3a9`, `a596d88`, `94d9089`)

### Changed

- Label phrase lines (`IPA:`, `say it like:`, `means:`) so the respelling
  is identifiable at a glance.
- Respelling style v0.3 locked: spell-like-english-word, no hyphens, no
  caps. Reader-perception-driven. Per Matt's brief — "if an English
  reader can read it aloud and produce a passable approximation, it's
  good. Stop trying to be IPA-rigorous."
- Synced labeled phrase-lines into serverless build context.

## M9d — 2026-05-08 (`4a43b67`)

### Changed

- README reflects actual stack (vanilla HTML+JS+CSS + Python FastAPI; no
  longer Ruby).
- Add cache-bust headers in serverless middleware so iOS Safari/Chrome
  doesn't pin stale shell after deploy.

## M9c — 2026-05-08 (`4062a1a`)

### Changed

- Sync v0.2 respelling data into serverless build context for sprite
  redeploy. Previously `serverless/data/` lagged `data/`.

## M9b — 2026-05-08 (`c1dd9ec`)

### Changed

- Sync respelling table to v0.2 "spelled in English" style (intermediate
  before v0.3 finalization in M9e).

## M9.2 — 2026-05-08 (`c2e5f86`)

### Fixed

- `/align` 500 error: browser MediaRecorder produces webm/opus or mp4/aac
  which `librosa.load(BytesIO(...))` (which routes to libsndfile) cannot
  decode. Switch to ffmpeg subprocess (handles all formats).

## M9.1 — 2026-05-08 (`c3d8f53`)

### Fixed

- Kill CORS by consolidating into a single sprite (web bundle + /align
  served from same origin via FastAPI StaticFiles mount).
- Fix JSON contract mismatch in /align response shape.

## M9 — 2026-05-08 (`d1c9626`)

### Fixed

- Corpus-shape mismatch: server returned a flat array, client expected
  `{phrases: [...]}`. Picker silently fell back to 3 stub phrases instead
  of the real 50. Added shape normalization in `loadData()`.
- iOS audio filename: MediaRecorder needs an explicit filename for the
  upload Blob.

---

## M8 — 2026-05-08 (`d1c9626`) — DEMO-READY

### Changed

- Flip `USE_MOCK = false` in `web/js/api.js`. Web client now points at the
  live serverless `/align` endpoint. parrot-lab-web is demo-ready.

## Deploy — 2026-05-08 (`10b91ed`)

### Added

- parrot-lab-align live on sprites.dev: `https://parrot-lab-align-brxpk.sprites.app`

## M3 — 2026-05-08 (`a6544b9`)

### Added

- Real `/align` endpoint: Wav2Vec2-XLSR phoneme alignment
  (`facebook/wav2vec2-lv-60-espeak-cv-ft`) + fal-ai/wizper STT in parallel
  + Levenshtein scoring with similarity-matrix substitution costs +
  greedy-longest-match respelling render.

## M2.4 — 2026-05-08 (`7c28044`)

### Added

- Serverless FastAPI skeleton: mock `/align` + `/healthz`, Dockerfile,
  fly.toml stub.

## M2.3 — 2026-05-08 (`6228ae1`)

### Added

- `respelling_es.json` (~220 mappings, IPA → English-orthography respelling)
- `similarity_es.json` (phoneme confusion matrix with English-speaker-error
  tagging)

## M2.2 — 2026-05-08 (`69a1f1d`)

### Added

- `corpus_es.json`: 50 Spanish phrases (FSI 30 + Pimsleur 20).

## M2.1 — 2026-05-08 (`f4473d2`)

### Added

- Web client skeleton: HTML + JS + CSS, MediaRecorder for capture, mock
  `/align`, localStorage for streak/history.

## Initial commit — 2026-05-08 (`8a933a5`)

- parrot-lab scaffolding: web-first pronunciation practice, en→es v1.
