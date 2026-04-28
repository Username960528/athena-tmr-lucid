"""Adapter boundary for the forked amused-py BLE source."""


class AmusedSource:
    """Placeholder adapter around the existing top-level amused-py modules."""

    strategy = "forked-source"

    def __init__(self) -> None:
        raise NotImplementedError("AmusedSource is implemented in M1.")
