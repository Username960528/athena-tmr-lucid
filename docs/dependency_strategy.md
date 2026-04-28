# amused-py Dependency Strategy

Decision: use a forked-source strategy for now.

This repository was created from `Amused-EEG/amused-py` and keeps the Muse BLE/data-source implementation in the repository while the REM-TMR layer is built. Do not add `amused-py` as a submodule or PyPI dependency yet.

Pinned upstream baseline:

- remote: `https://github.com/Amused-EEG/amused-py`
- ref: `bce20f98ddc7fa2efe3219d1b5d2f7554a55eb97`

## Rationale

- The current code already contains the Athena BLE protocol implementation.
- Local changes need to coordinate closely with recording, replay, and test fixtures.
- A submodule would add workflow complexity before the project has stable adapter boundaries.
- A PyPI dependency would make it harder to patch protocol-level behavior quickly.

## Sync Plan

1. Keep the `upstream` remote pointed at `Amused-EEG/amused-py`.
2. Periodically run `git fetch upstream --prune`.
3. Review upstream changes before merging or cherry-picking.
4. Port small protocol fixes intentionally with tests.
5. Avoid broad upstream merges during active feature work.

## Contribution Policy

Contribute general Muse BLE fixes upstream when they are not specific to REM-TMR/TLR. Keep REM detection, cue scheduling, reports, validation, and sleep-protocol code in this repository.
