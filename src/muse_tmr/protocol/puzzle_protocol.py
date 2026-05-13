"""Pre-sleep puzzle session records and helpers."""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

PUZZLE_PROTOCOL_SCHEMA_VERSION = 1
DEFAULT_NIGHT_PUZZLE_COUNT = 4


@dataclass(frozen=True)
class PuzzleTask:
    puzzle_id: str
    prompt: str
    solution: str
    cue_id: str = ""
    known: bool = False
    solved: bool = False
    retired: bool = False
    source: str = "manual"
    tags: Tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "puzzle_id", _required_str(self.puzzle_id, "puzzle_id"))
        object.__setattr__(self, "prompt", _required_str(self.prompt, "prompt"))
        object.__setattr__(self, "solution", _required_str(self.solution, "solution"))
        object.__setattr__(self, "cue_id", self.cue_id.strip() or self.puzzle_id)
        object.__setattr__(self, "source", self.source.strip() or "manual")
        object.__setattr__(self, "tags", tuple(tag.strip() for tag in self.tags if tag.strip()))
        if not self.cue_id.strip():
            raise ValueError("cue_id must not be empty")

    @property
    def is_eligible_baseline(self) -> bool:
        return not self.retired and not self.known and not self.solved

    def to_dict(self) -> Dict[str, object]:
        return {
            "puzzle_id": self.puzzle_id,
            "prompt": self.prompt,
            "solution": self.solution,
            "cue_id": self.cue_id,
            "known": self.known,
            "solved": self.solved,
            "retired": self.retired,
            "source": self.source,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "PuzzleTask":
        return cls(
            puzzle_id=str(payload.get("puzzle_id", payload.get("id", ""))),
            prompt=str(payload.get("prompt", payload.get("question", ""))),
            solution=str(payload.get("solution", payload.get("answer", ""))),
            cue_id=str(payload.get("cue_id", "")),
            known=_boolish(payload.get("known", False)),
            solved=_boolish(payload.get("solved", False)),
            retired=_boolish(payload.get("retired", False)),
            source=str(payload.get("source", "manual")),
            tags=_parse_tags(payload.get("tags", ())),
            metadata=dict(payload.get("metadata", {}) or {}),
        )


@dataclass(frozen=True)
class PuzzleAttempt:
    puzzle_id: str
    response: str
    duration_seconds: float
    solved: bool
    known_after: bool = False
    started_at_utc: str = ""
    ended_at_utc: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "puzzle_id", _required_str(self.puzzle_id, "puzzle_id"))
        object.__setattr__(self, "response", str(self.response))
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")
        if not self.started_at_utc:
            object.__setattr__(self, "started_at_utc", _utc_now())
        if not self.ended_at_utc:
            object.__setattr__(self, "ended_at_utc", self.started_at_utc)

    def to_dict(self) -> Dict[str, object]:
        return {
            "puzzle_id": self.puzzle_id,
            "response": self.response,
            "duration_seconds": self.duration_seconds,
            "solved": self.solved,
            "known_after": self.known_after,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "PuzzleAttempt":
        return cls(
            puzzle_id=str(payload["puzzle_id"]),
            response=str(payload.get("response", "")),
            duration_seconds=float(payload.get("duration_seconds", 0.0)),
            solved=_boolish(payload.get("solved", False)),
            known_after=_boolish(payload.get("known_after", False)),
            started_at_utc=str(payload.get("started_at_utc", "")),
            ended_at_utc=str(payload.get("ended_at_utc", "")),
            notes=str(payload.get("notes", "")),
        )


@dataclass(frozen=True)
class AssociationResult:
    puzzle_id: str
    cue_id: str
    response: str
    expected_solution: str
    matched: bool
    checked_at_utc: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "puzzle_id", _required_str(self.puzzle_id, "puzzle_id"))
        object.__setattr__(self, "cue_id", _required_str(self.cue_id, "cue_id"))
        object.__setattr__(self, "response", str(self.response))
        object.__setattr__(self, "expected_solution", str(self.expected_solution))
        if not self.checked_at_utc:
            object.__setattr__(self, "checked_at_utc", _utc_now())

    def to_dict(self) -> Dict[str, object]:
        return {
            "puzzle_id": self.puzzle_id,
            "cue_id": self.cue_id,
            "response": self.response,
            "expected_solution": self.expected_solution,
            "matched": self.matched,
            "checked_at_utc": self.checked_at_utc,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "AssociationResult":
        return cls(
            puzzle_id=str(payload["puzzle_id"]),
            cue_id=str(payload["cue_id"]),
            response=str(payload.get("response", "")),
            expected_solution=str(payload.get("expected_solution", "")),
            matched=_boolish(payload.get("matched", False)),
            checked_at_utc=str(payload.get("checked_at_utc", "")),
            notes=str(payload.get("notes", "")),
        )


@dataclass(frozen=True)
class NightPuzzleSession:
    session_id: str
    puzzle_ids: Tuple[str, ...]
    generated_at_utc: str = ""
    puzzle_count: int = DEFAULT_NIGHT_PUZZLE_COUNT
    selection_seed: Optional[int] = None
    association_results: Tuple[AssociationResult, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    schema_version: int = PUZZLE_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _required_str(self.session_id, "session_id"))
        object.__setattr__(self, "puzzle_ids", tuple(self.puzzle_ids))
        object.__setattr__(self, "association_results", tuple(self.association_results))
        if not self.generated_at_utc:
            object.__setattr__(self, "generated_at_utc", _utc_now())
        if self.puzzle_count <= 0:
            raise ValueError("puzzle_count must be positive")
        if len(set(self.puzzle_ids)) != len(self.puzzle_ids):
            raise ValueError("night puzzle session cannot contain duplicate puzzle IDs")
        if len(self.puzzle_ids) != self.puzzle_count:
            raise ValueError("puzzle_count must match puzzle_ids length")

    def with_association_result(self, result: AssociationResult) -> "NightPuzzleSession":
        if result.puzzle_id not in self.puzzle_ids:
            raise ValueError(f"association puzzle is not in this session: {result.puzzle_id}")
        kept = tuple(
            existing
            for existing in self.association_results
            if existing.puzzle_id != result.puzzle_id
        )
        return NightPuzzleSession(
            session_id=self.session_id,
            puzzle_ids=self.puzzle_ids,
            generated_at_utc=self.generated_at_utc,
            puzzle_count=self.puzzle_count,
            selection_seed=self.selection_seed,
            association_results=kept + (result,),
            metadata=self.metadata,
            schema_version=self.schema_version,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "generated_at_utc": self.generated_at_utc,
            "puzzle_count": self.puzzle_count,
            "selection_seed": self.selection_seed,
            "puzzle_ids": list(self.puzzle_ids),
            "association_results": [
                result.to_dict() for result in self.association_results
            ],
            "metadata": dict(self.metadata),
        }

    def save(self, output_path: Path) -> Path:
        output_path = output_path.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return output_path

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "NightPuzzleSession":
        return cls(
            schema_version=int(payload.get("schema_version", PUZZLE_PROTOCOL_SCHEMA_VERSION)),
            session_id=str(payload["session_id"]),
            generated_at_utc=str(payload.get("generated_at_utc", "")),
            puzzle_count=int(payload.get("puzzle_count", len(payload.get("puzzle_ids", ())))),
            selection_seed=_optional_int(payload.get("selection_seed")),
            puzzle_ids=tuple(str(item) for item in payload.get("puzzle_ids", ())),
            association_results=tuple(
                AssociationResult.from_dict(item)
                for item in payload.get("association_results", ())
            ),
            metadata=dict(payload.get("metadata", {}) or {}),
        )

    @classmethod
    def load(cls, input_path: Path) -> "NightPuzzleSession":
        return cls.from_dict(json.loads(input_path.expanduser().read_text(encoding="utf-8")))


@dataclass(frozen=True)
class PuzzleCatalog:
    puzzles: Tuple[PuzzleTask, ...] = ()
    attempts: Tuple[PuzzleAttempt, ...] = ()
    schema_version: int = PUZZLE_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "puzzles", tuple(self.puzzles))
        object.__setattr__(self, "attempts", tuple(self.attempts))
        puzzle_ids = [puzzle.puzzle_id for puzzle in self.puzzles]
        if len(set(puzzle_ids)) != len(puzzle_ids):
            raise ValueError("puzzle IDs must be unique")

    @property
    def puzzle_count(self) -> int:
        return len(self.puzzles)

    def puzzle_by_id(self) -> Dict[str, PuzzleTask]:
        return {puzzle.puzzle_id: puzzle for puzzle in self.puzzles}

    def get_puzzle(self, puzzle_id: str) -> PuzzleTask:
        try:
            return self.puzzle_by_id()[puzzle_id]
        except KeyError:
            raise KeyError(f"unknown puzzle_id: {puzzle_id}")

    def solved_puzzle_ids(self) -> Tuple[str, ...]:
        solved = {puzzle.puzzle_id for puzzle in self.puzzles if puzzle.solved}
        solved.update(attempt.puzzle_id for attempt in self.attempts if attempt.solved)
        return tuple(sorted(solved))

    def known_puzzle_ids(self) -> Tuple[str, ...]:
        known = {puzzle.puzzle_id for puzzle in self.puzzles if puzzle.known}
        known.update(attempt.puzzle_id for attempt in self.attempts if attempt.known_after)
        return tuple(sorted(known))

    def eligible_unsolved_puzzles(self, *, include_known: bool = False) -> Tuple[PuzzleTask, ...]:
        solved = set(self.solved_puzzle_ids())
        known = set(self.known_puzzle_ids())
        return tuple(
            puzzle
            for puzzle in self.puzzles
            if not puzzle.retired
            and puzzle.puzzle_id not in solved
            and (include_known or puzzle.puzzle_id not in known)
        )

    def with_puzzle(self, puzzle: PuzzleTask) -> "PuzzleCatalog":
        kept = tuple(
            existing for existing in self.puzzles if existing.puzzle_id != puzzle.puzzle_id
        )
        return PuzzleCatalog(
            puzzles=kept + (puzzle,),
            attempts=self.attempts,
            schema_version=self.schema_version,
        )

    def with_attempt(self, attempt: PuzzleAttempt) -> "PuzzleCatalog":
        self.get_puzzle(attempt.puzzle_id)
        return PuzzleCatalog(
            puzzles=self.puzzles,
            attempts=self.attempts + (attempt,),
            schema_version=self.schema_version,
        )

    def check_association(
        self,
        puzzle_id: str,
        response: str,
        *,
        checked_at_utc: str = "",
        notes: str = "",
    ) -> AssociationResult:
        puzzle = self.get_puzzle(puzzle_id)
        matched = _normalize_answer(response) == _normalize_answer(puzzle.solution)
        return AssociationResult(
            puzzle_id=puzzle.puzzle_id,
            cue_id=puzzle.cue_id,
            response=response,
            expected_solution=puzzle.solution,
            matched=matched,
            checked_at_utc=checked_at_utc,
            notes=notes,
        )

    def generate_night_session(
        self,
        *,
        session_id: str,
        puzzle_count: int = DEFAULT_NIGHT_PUZZLE_COUNT,
        selection_seed: Optional[int] = None,
        include_known: bool = False,
    ) -> NightPuzzleSession:
        eligible = list(self.eligible_unsolved_puzzles(include_known=include_known))
        if len(eligible) < puzzle_count:
            raise ValueError(
                f"not enough eligible unsolved puzzles: need {puzzle_count}, have {len(eligible)}"
            )
        if selection_seed is not None:
            random.Random(selection_seed).shuffle(eligible)
        selected = tuple(puzzle.puzzle_id for puzzle in eligible[:puzzle_count])
        return NightPuzzleSession(
            session_id=session_id,
            puzzle_ids=selected,
            puzzle_count=puzzle_count,
            selection_seed=selection_seed,
            metadata={
                "eligible_count": len(eligible),
                "include_known": include_known,
            },
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "puzzles": [puzzle.to_dict() for puzzle in self.puzzles],
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }

    def save(self, output_path: Path) -> Path:
        output_path = output_path.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return output_path

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "PuzzleCatalog":
        return cls(
            schema_version=int(payload.get("schema_version", PUZZLE_PROTOCOL_SCHEMA_VERSION)),
            puzzles=tuple(
                PuzzleTask.from_dict(item)
                for item in payload.get("puzzles", ())
            ),
            attempts=tuple(
                PuzzleAttempt.from_dict(item)
                for item in payload.get("attempts", ())
            ),
        )

    @classmethod
    def load(cls, input_path: Path) -> "PuzzleCatalog":
        return cls.from_dict(json.loads(input_path.expanduser().read_text(encoding="utf-8")))


def import_puzzle_file(input_path: Path) -> PuzzleCatalog:
    input_path = input_path.expanduser()
    if input_path.suffix.lower() == ".csv":
        with input_path.open("r", encoding="utf-8", newline="") as handle:
            return puzzle_catalog_from_rows(csv.DictReader(handle))

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping) and "schema_version" in payload and "puzzles" in payload:
        return PuzzleCatalog.from_dict(payload)
    if isinstance(payload, Mapping):
        rows = payload.get("puzzles", ())
    else:
        rows = payload
    return puzzle_catalog_from_rows(rows)


def puzzle_catalog_from_rows(rows: Iterable[Mapping[str, object]]) -> PuzzleCatalog:
    return PuzzleCatalog(puzzles=tuple(PuzzleTask.from_dict(row) for row in rows))


def load_puzzle_catalog(input_path: Path) -> PuzzleCatalog:
    return PuzzleCatalog.load(input_path)


def load_night_puzzle_session(input_path: Path) -> NightPuzzleSession:
    return NightPuzzleSession.load(input_path)


def _parse_tags(value: object) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        if not value.strip():
            return ()
        return tuple(
            tag.strip()
            for tag in re.split(r"[,;]", value)
            if tag.strip()
        )
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"", "0", "false", "f", "no", "n", "off"}:
        return False
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    raise ValueError(f"invalid boolean value: {value}")


def _optional_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _required_str(value: object, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _normalize_answer(value: object) -> str:
    return " ".join(str(value).strip().casefold().split())


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
