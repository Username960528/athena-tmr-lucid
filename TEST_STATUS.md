# Test Status

## Current Test Results
- **380 tests passing**, 3 skipped ✅
- **0 tests failing** 🎉
- **~86% line coverage** on the `muse_tmr` package

Skipped tests require an optional pandas Parquet engine (`pyarrow` or
`fastparquet`); install one to exercise the Parquet export paths.

## Coverage Overview
Well covered: REM detection (heuristic + personal classifier), the
`StableRemGate` and `ArousalGuard` safety gates, the TMR cue scheduler,
randomization, and the staged pilots.

Lower coverage worth improving:
- Acquisition sources with hardware-facing reconnect/error paths
  (`openmuse_lsl_source`, `brainflow_source`, `amused_source`)
- `data/ring_buffer.py` (currently untested)
- `audio/audio_player.py` fallback and volume-cap branches
- `data/watchdog.py` no-data timeout / reconnect logic

## Running Tests

### Full suite under pytest (matches CI):
```bash
pip install -e ".[dev]"
python -m pytest tests/
```

### With coverage:
```bash
python -m pytest tests/ --cov=muse_tmr --cov-report=term-missing
```

### Legacy unittest runner (no install required):
```bash
PYTHONPATH=src python run_tests.py --all
```

### Specific test file:
```bash
python -m pytest tests/test_rem_gate.py -v
```

## Notes
- A repository-root `conftest.py` puts `src/` on `sys.path` so `pytest` works
  from a checkout without an editable install.
- CI (`.github/workflows/guardrails.yml`) runs the full suite with coverage on
  every push and pull request.
