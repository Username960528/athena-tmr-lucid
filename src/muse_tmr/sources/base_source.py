"""Base source contract for Muse frame producers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Mapping

from muse_tmr.data.sample_types import MuseFrame


@dataclass(frozen=True)
class MuseSourceMetadata:
    source_name: str
    device_name: str
    device_id: str
    capabilities: Mapping[str, bool]


class BaseMuseSource(ABC):
    @abstractmethod
    async def connect(self) -> MuseSourceMetadata:
        """Connect to the source and return device metadata."""

    @abstractmethod
    async def stream(self) -> AsyncIterator[MuseFrame]:
        """Yield Muse frames until stopped."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop streaming and release resources."""
