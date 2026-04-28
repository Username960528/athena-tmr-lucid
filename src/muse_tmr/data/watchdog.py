"""Recording watchdog for no-data and modality dropout detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from muse_tmr.data.sample_types import MuseFrame


@dataclass(frozen=True)
class WatchdogEvent:
    event: str
    timestamp: float
    details: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "event": self.event,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class RecordingWatchdog:
    def __init__(
        self,
        no_data_timeout_seconds: float = 30.0,
        modality_timeout_seconds: float = 120.0,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
    ) -> None:
        self.no_data_timeout_seconds = no_data_timeout_seconds
        self.modality_timeout_seconds = modality_timeout_seconds
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.last_frame_at: Optional[float] = None
        self.last_modality_at: Dict[str, float] = {}
        self.dropped_modalities: set[str] = set()

    def observe_frame(self, frame: MuseFrame, now: float) -> List[WatchdogEvent]:
        events: List[WatchdogEvent] = []
        self.last_frame_at = now

        for modality in frame.modalities():
            self.last_modality_at[modality] = now
            if modality in self.dropped_modalities:
                self.dropped_modalities.remove(modality)
                events.append(
                    WatchdogEvent(
                        event="modality_restored",
                        timestamp=now,
                        details={"modality": modality},
                    )
                )

        for modality, last_seen in list(self.last_modality_at.items()):
            if modality in self.dropped_modalities:
                continue
            if now - last_seen > self.modality_timeout_seconds:
                self.dropped_modalities.add(modality)
                events.append(
                    WatchdogEvent(
                        event="modality_dropout",
                        timestamp=now,
                        details={"modality": modality, "seconds_since_seen": now - last_seen},
                    )
                )

        return events

    def no_data_event(self, now: float) -> Optional[WatchdogEvent]:
        if self.last_frame_at is None:
            return WatchdogEvent(
                event="no_data_timeout",
                timestamp=now,
                details={"seconds_since_frame": None},
            )
        seconds_since = now - self.last_frame_at
        if seconds_since >= self.no_data_timeout_seconds:
            return WatchdogEvent(
                event="no_data_timeout",
                timestamp=now,
                details={"seconds_since_frame": seconds_since},
            )
        return None

    def reconnect_backoff(self, attempt: int) -> float:
        return min(self.backoff_base_seconds * (2 ** max(0, attempt - 1)), self.backoff_max_seconds)

    def state(self) -> Dict[str, object]:
        return {
            "last_frame_at": self.last_frame_at,
            "last_modality_at": dict(self.last_modality_at),
            "dropped_modalities": tuple(sorted(self.dropped_modalities)),
        }
