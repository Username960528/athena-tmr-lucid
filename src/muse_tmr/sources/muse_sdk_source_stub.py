"""Stub for a future optional official Muse SDK adapter.

No proprietary SDK files or copied SDK code may be committed to this repository.
"""


class MuseSdkSourceStub:
    def __init__(self, sdk_path: str) -> None:
        self.sdk_path = sdk_path

    def connect(self) -> None:
        raise RuntimeError(
            "Official Muse SDK support is optional. SDK must be downloaded "
            "separately and placed locally; do not commit."
        )
