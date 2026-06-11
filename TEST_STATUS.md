# Test Status

## Current Test Results
- **434 tests passing**, 3 skipped ✅
- **0 tests failing** 🎉
- **~89% line coverage** on the `muse_tmr` package

Skipped tests require an optional pandas Parquet engine (`pyarrow` or
`fastparquet`); install one to exercise the Parquet export paths.

## Coverage Overview
Well covered: REM detection (heuristic + personal classifier), the
`StableRemGate` and `ArousalGuard` safety gates, the TMR cue scheduler,
randomization, the staged pilots, audio playback safety branches
(volume caps, fades, backend fallbacks), the ring buffer, and the
acquisition sources' error/timeout paths.

Lower coverage worth improving:
- `data/watchdog.py` no-data timeout / reconnect logic
- Legacy root-level modules (`muse_sleep_parser`, `muse_integrated_parser`,
  `muse_stream_client`, `muse_discovery`) if they remain on the live path

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
