# M8 Pilot 3: Replay Cue Simulation

Pilot 3 validates the REM gate, arousal guard, and TMR scheduler on an existing
recording without playing real audio. It produces an inspectable cue plan and
scheduler event stream from replayed Muse frames.

## Goal

- Replay a completed recording through 30-second epochs and feature extraction.
- Run heuristic REM detection, `StableRemGate`, `ArousalGuard`, and
  `TmrCueScheduler`.
- Save a JSON report containing epochs, gate decisions, guard decisions,
  scheduler events, and `cue_plan`.
- Prove this step uses mocked audio only: `audio_playback_executed=false`.
- Confirm zero uncued puzzle `play` events.

This pilot is not sleep-time cueing. It does not call an audio backend and does not
test whether cues are audible or effective.

## Run

Use a previous no-audio recording, a puzzle catalog, a generated night puzzle
session, a cued/uncued assignment, and a cue library:

```bash
cd /path/to/athena-tmr-lucid

.venv/bin/python -m muse_tmr.cli.main simulate-replay-cues \
  data/recordings/<pilot-session> \
  --catalog data/protocol/puzzle_catalog.json \
  --session data/protocol/night-001_puzzles.json \
  --assignment data/protocol/night-001_assignment.json \
  --cue-library data/cues/starter.json \
  --output data/reports/pilot3_replay_cue_plan.json \
  --scheduler-events-output data/reports/pilot3_scheduler_events.jsonl
```

Optional replay and gate tuning flags:

```bash
  --start-seconds 1800 \
  --end-seconds 7200 \
  --epoch-seconds 30 \
  --stride-seconds 30 \
  --enter-threshold 0.70 \
  --exit-threshold 0.45 \
  --min-stable-seconds 60
```

## Validate

The command exits `0` only when:

- replay produced at least one epoch;
- no real audio playback was executed;
- scheduler events were generated for inspection;
- no uncued puzzle received a `play` scheduler event.

Inspect `data/reports/pilot3_replay_cue_plan.json`:

- `cue_plan`: scheduler `play` events only;
- `scheduler_events`: all `play`, `skip`, `pause`, and `stop` decisions;
- `epochs`: per-epoch prediction, gate, guard, and scheduler context;
- `metrics.uncued_puzzle_play_count`: must be `0`;
- `audio_backend`: must be `mock`;
- `audio_playback_executed`: must be `false`.

If `cue_plan` is empty but validation passes, the replay did not meet stable REM and
safety conditions during the selected time range. That is an acceptable Pilot 3
outcome; use scheduler `skip` reasons and gate decisions to understand why.

Keep generated reports under `data/reports/` local unless you intentionally sanitize
and share them.
