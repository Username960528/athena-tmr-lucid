"""Low-volume audio playback interface for sleep cues."""


class AudioPlayer:
    """Placeholder audio player with conservative defaults."""

    def __init__(self, max_volume: float = 0.2) -> None:
        if not 0.0 <= max_volume <= 1.0:
            raise ValueError("max_volume must be between 0.0 and 1.0")
        self.max_volume = max_volume

    def play(self, cue_id: str) -> None:
        raise NotImplementedError("Audio playback is implemented in M4.")
