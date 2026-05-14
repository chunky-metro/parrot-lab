# evals/

Reliability + accuracy evaluation harness for parrot-lab.

## 50_phrase_sweep.py

Loads the canonical 50-phrase Spanish corpus and exercises the live
`/align` endpoint to surface failure modes across the FULL corpus.

### What it catches

- **alignment_failure**: HTTP 500/503/422, JSON shape errors
- **stt_missing**: degraded mode + no transcript on what should be clean audio
- **score_outlier**: score < 30 on a TTS-clean utterance
- **ipa_leak**: user-facing strings contain raw IPA (`ː ˈ ʉ ʌ æ ...`)
- **mistake_dup**: identical hint shown twice in mistakes list

### Modes

| Mode | What it does | Cost | When to use |
| :--- | :--- | :--- | :--- |
| `tts` (default) | macOS `say` Mónica voice → 16kHz wav → POST | ~$0.025/phrase wizper × 50 = ~$1.25 | full reliability sweep |
| `wizper` | 0.3s silent wav per phrase → POST | $0 (audio gate rejects) | verify gate fix, no FAL spend |
| `fixtures` | reads `serverless/tests/fixtures/<phrase_id>.wav` | depends on STT path | reproducible regression tests |

### Usage

```bash
# Smoke test — first 5 phrases only
python evals/50_phrase_sweep.py --mode tts --limit 5

# Full sweep (default mode, default URL)
python evals/50_phrase_sweep.py --mode tts

# Cost-free gate verification
python evals/50_phrase_sweep.py --mode wizper

# Local serverless under test
python evals/50_phrase_sweep.py --base-url http://localhost:8080
```

### Output

JSON report at `evals/reports/sweep-<ISO8601>.json` with per-phrase verdicts +
aggregate counts by category. Exit code:

- `0`: all phrases categorized `ok`
- `2`: at least one phrase in a non-`ok` category
- `1`: setup error (corpus missing, bad args)

Useful for CI gating: red the build if any phrase regresses.

### Cost discipline

Each `tts` mode run posts 50 wavs to wizper at ~$0.025/call → ~$1.25 per sweep.
Run sparingly. The `wizper` mode is FREE (the audio gate rejects 0.3s silent
wavs before STT fires) and is what you want during development of the
audio gate or scoring logic.

The audio cache (`evals/.audio-cache/`) is gitignored so re-runs don't
re-synthesize. Delete it when you change voice/quality.
