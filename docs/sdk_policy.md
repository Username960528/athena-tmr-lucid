# SDK And Private Data Policy

Official Muse SDK support, if added, must remain optional and local-only.

SDK must be downloaded separately and placed locally; do not commit.

Do not commit:

- official Muse SDK binaries, headers, frameworks, archives, installers, or copied docs
- closed-source vendor code
- keys, tokens, `.env`, certificates, or private credentials
- private overnight recordings
- personal sleep reports, dream reports, calibration files, or device identifiers
- private cue audio

Allowed:

- open-source code
- adapter interfaces and stubs
- synthetic fixtures
- explicitly reviewed small public test fixtures

Run the guardrail script before publishing SDK-adjacent or data-adjacent changes:

```bash
python scripts/check_forbidden_files.py
```
