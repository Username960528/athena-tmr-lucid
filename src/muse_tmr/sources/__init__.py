"""Muse data source adapters."""

from muse_tmr.sources.base_source import BaseMuseSource, MuseDeviceInfo, MuseSourceMetadata
from muse_tmr.sources.brainflow_source import (
    BrainFlowDependencyError,
    BrainFlowSource,
    BrainFlowSourceConfig,
)
from muse_tmr.sources.muse_sdk_source_stub import (
    MuseSdkSourceConfig,
    MuseSdkSourceStub,
    MuseSdkUnavailableError,
)
from muse_tmr.sources.openmuse_lsl_source import (
    OpenMuseLslConfig,
    OpenMuseLslDependencyError,
    OpenMuseLslSource,
)

__all__ = [
    "BaseMuseSource",
    "BrainFlowDependencyError",
    "BrainFlowSource",
    "BrainFlowSourceConfig",
    "MuseDeviceInfo",
    "MuseSourceMetadata",
    "MuseSdkSourceConfig",
    "MuseSdkSourceStub",
    "MuseSdkUnavailableError",
    "OpenMuseLslConfig",
    "OpenMuseLslDependencyError",
    "OpenMuseLslSource",
]
