"""CLI entry point for the Muse REM-TMR project."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
from pathlib import Path
from typing import Optional, Sequence

from muse_tmr import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muse-tmr",
        description="Muse S Athena REM-TMR/TLR research tooling.",
    )
    parser.add_argument("--version", action="version", version=f"muse-tmr {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show project status and configured components.")

    discover_parser = subparsers.add_parser("discover", help="Discover Muse devices.")
    discover_parser.add_argument("--source", choices=("amused",), default="amused")
    discover_parser.add_argument("--name-filter", default="Muse")

    stream_parser = subparsers.add_parser("stream", help="Stream Muse frames from a source.")
    stream_parser.add_argument("--source", choices=("amused",), default="amused")
    stream_parser.add_argument("--address", help="Muse BLE address. If omitted, discovery is used.")
    stream_parser.add_argument("--name-filter", default="Muse")
    stream_parser.add_argument("--preset", default="p1034")
    stream_parser.add_argument("--duration-seconds", type=int, default=3600)
    stream_parser.add_argument("--quiet", action="store_true")

    record_parser = subparsers.add_parser("record", help="Record an overnight Muse session.")
    record_parser.add_argument("--source", choices=("amused",), default="amused")
    record_parser.add_argument("--address", help="Muse BLE address. If omitted, discovery is used.")
    record_parser.add_argument("--name-filter", default="Muse")
    record_parser.add_argument("--preset", default="p1034")
    record_parser.add_argument("--duration-hours", type=float, default=8.0)
    record_parser.add_argument("--duration-seconds", type=float)
    record_parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Recording directory. Relative paths resolve under the current working "
            "directory, or under the project checkout when launched via macOS Python.app."
        ),
    )
    record_parser.add_argument("--allow-short", action="store_true", help="Allow short smoke-test recordings.")
    record_parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "status":
        print("Muse REM-TMR project scaffold is installed.")
        return 0
    if args.command == "discover":
        return asyncio.run(_discover(args))
    if args.command == "stream":
        return asyncio.run(_stream(args))
    if args.command == "record":
        return asyncio.run(_record(args))

    parser.print_help()
    return 0


async def _discover(args: argparse.Namespace) -> int:
    source = _build_source(args, duration_seconds=0)
    devices = await source.discover()
    for device in devices:
        print(f"{device.name}\t{device.address}\trssi={device.rssi}")
    return 0 if devices else 1


async def _stream(args: argparse.Namespace) -> int:
    source = _build_source(args, duration_seconds=args.duration_seconds)
    metadata = await source.connect()
    frame_count = 0
    modality_counts = {}
    try:
        async for frame in source.stream():
            frame_count += 1
            for modality in frame.modalities():
                modality_counts[modality] = modality_counts.get(modality, 0) + 1
    finally:
        await source.stop()

    print(
        f"stream complete source={metadata.source_name} "
        f"device={metadata.device_name} frames={frame_count} modalities={modality_counts}"
    )
    return 0


async def _record(args: argparse.Namespace) -> int:
    from muse_tmr.data.recorder import OvernightRecorder, RecordingConfig

    duration_seconds = (
        args.duration_seconds
        if args.duration_seconds is not None
        else args.duration_hours * 3600
    )
    output_dir = _resolve_output_dir(args.output_dir) if args.output_dir else _default_recording_dir()
    source = _build_source(args, duration_seconds=0)
    recorder = OvernightRecorder(
        RecordingConfig(
            output_dir=output_dir,
            duration_seconds=duration_seconds,
            source_name=args.source,
            allow_short=args.allow_short,
        )
    )
    summary = await recorder.record(source)
    print(f"recording complete summary={summary.summary_path}")
    return 0


def _build_source(args: argparse.Namespace, duration_seconds: int):
    from muse_tmr.sources.amused_source import AmusedSource

    return AmusedSource(
        address=getattr(args, "address", None),
        name_filter=getattr(args, "name_filter", "Muse"),
        preset=getattr(args, "preset", "p1034"),
        duration_seconds=duration_seconds,
        verbose=not getattr(args, "quiet", False),
    )


def _default_recording_dir() -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return _default_path_base() / "data" / "recordings" / timestamp


def _resolve_output_dir(output_dir: Path) -> Path:
    output_dir = output_dir.expanduser()
    if output_dir.is_absolute():
        return output_dir
    return _default_path_base() / output_dir


def _default_path_base() -> Path:
    cwd = Path.cwd()
    if _is_writable_non_root(cwd):
        return cwd.resolve()

    project_root = _find_project_root(Path(__file__).resolve())
    if project_root is not None:
        return project_root

    return Path.home().resolve()


def _is_writable_non_root(path: Path) -> bool:
    if path.parent == path:
        return False
    return os.access(path, os.W_OK)


def _find_project_root(start: Path) -> Optional[Path]:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "muse_tmr").exists():
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
