import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from muse_tmr.cli.main import build_parser, main
from muse_tmr.protocol import (
    AssociationResult,
    NightPuzzleSession,
    PuzzleAttempt,
    PuzzleCatalog,
    PuzzleTask,
    import_puzzle_file,
    load_night_puzzle_session,
    load_puzzle_catalog,
    puzzle_catalog_from_rows,
)


def _puzzle(index, **overrides):
    values = {
        "puzzle_id": f"p{index}",
        "prompt": f"Puzzle {index}",
        "solution": f"Answer {index}",
        "cue_id": f"cue-{index}",
    }
    values.update(overrides)
    return PuzzleTask(**values)


class TestPuzzleProtocol(unittest.TestCase):
    def test_catalog_imports_rows_and_parses_flags(self):
        catalog = puzzle_catalog_from_rows([
            {
                "puzzle_id": "p1",
                "prompt": "Puzzle 1",
                "solution": "Answer 1",
                "cue_id": "cue-1",
                "known": "false",
                "solved": "0",
                "retired": "no",
                "tags": "logic, spatial",
            },
            {
                "puzzle_id": "p2",
                "prompt": "Puzzle 2",
                "solution": "Answer 2",
                "known": "yes",
            },
        ])

        self.assertEqual(catalog.puzzle_count, 2)
        self.assertEqual(catalog.get_puzzle("p1").tags, ("logic", "spatial"))
        self.assertEqual(catalog.get_puzzle("p2").cue_id, "p2")
        self.assertEqual(catalog.known_puzzle_ids(), ("p2",))

    def test_duplicate_puzzle_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            PuzzleCatalog(puzzles=(_puzzle(1), _puzzle(1)))

    def test_eligible_unsolved_filters_solved_known_retired_and_attempts(self):
        catalog = PuzzleCatalog(
            puzzles=(
                _puzzle(1),
                _puzzle(2, solved=True),
                _puzzle(3, known=True),
                _puzzle(4, retired=True),
                _puzzle(5),
            )
        ).with_attempt(
            PuzzleAttempt("p5", "Answer 5", duration_seconds=12.0, solved=True)
        )

        eligible = catalog.eligible_unsolved_puzzles()

        self.assertEqual([puzzle.puzzle_id for puzzle in eligible], ["p1"])

    def test_generates_four_unsolved_tasks_with_seed(self):
        catalog = PuzzleCatalog(
            puzzles=(
                _puzzle(1),
                _puzzle(2),
                _puzzle(3),
                _puzzle(4),
                _puzzle(5, solved=True),
                _puzzle(6, known=True),
                _puzzle(7),
            )
        )

        first = catalog.generate_night_session(
            session_id="night-001",
            puzzle_count=4,
            selection_seed=17,
        )
        second = catalog.generate_night_session(
            session_id="night-001",
            puzzle_count=4,
            selection_seed=17,
        )

        self.assertEqual(first.puzzle_ids, second.puzzle_ids)
        self.assertEqual(first.selection_seed, second.selection_seed)
        self.assertEqual(len(first.puzzle_ids), 4)
        self.assertNotIn("p5", first.puzzle_ids)
        self.assertNotIn("p6", first.puzzle_ids)
        self.assertEqual(first.metadata["eligible_count"], 5)

    def test_generation_requires_enough_unsolved_tasks(self):
        catalog = PuzzleCatalog(puzzles=(_puzzle(1), _puzzle(2, solved=True)))

        with self.assertRaises(ValueError):
            catalog.generate_night_session(session_id="night-001", puzzle_count=4)

    def test_association_checks_are_normalized_and_saved_on_session(self):
        catalog = PuzzleCatalog(puzzles=(_puzzle(1, solution="Blue Key"),))
        session = NightPuzzleSession(session_id="night-001", puzzle_ids=("p1",), puzzle_count=1)

        result = catalog.check_association("p1", "  blue   key ")
        updated = session.with_association_result(result)

        self.assertTrue(result.matched)
        self.assertEqual(result.cue_id, "cue-1")
        self.assertEqual(updated.association_results, (result,))

        replacement = AssociationResult("p1", "cue-1", "wrong", "Blue Key", matched=False)
        replaced = updated.with_association_result(replacement)
        self.assertEqual(replaced.association_results, (replacement,))

    def test_catalog_and_session_round_trip_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.json"
            session_path = Path(tmp) / "session.json"
            catalog = PuzzleCatalog(puzzles=(_puzzle(1), _puzzle(2)))
            session = NightPuzzleSession(session_id="night-001", puzzle_ids=("p1",), puzzle_count=1)

            catalog.save(catalog_path)
            session.save(session_path)

            loaded_catalog = load_puzzle_catalog(catalog_path)
            loaded_session = load_night_puzzle_session(session_path)

        self.assertEqual(loaded_catalog.puzzles, catalog.puzzles)
        self.assertEqual(loaded_session.session_id, "night-001")
        self.assertEqual(loaded_session.puzzle_ids, ("p1",))

    def test_import_puzzle_file_accepts_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "puzzles.csv"
            csv_path.write_text(
                "puzzle_id,prompt,solution,cue_id,known,solved,tags\n"
                "p1,Puzzle 1,Answer 1,cue-1,false,false,logic\n",
                encoding="utf-8",
            )

            catalog = import_puzzle_file(csv_path)

        self.assertEqual(catalog.puzzle_count, 1)
        self.assertEqual(catalog.get_puzzle("p1").cue_id, "cue-1")


class TestPuzzleProtocolCli(unittest.TestCase):
    def test_puzzle_commands_parse_paths(self):
        import_args = build_parser().parse_args([
            "import-puzzles",
            "puzzles.csv",
            "--output",
            "data/protocol/catalog.json",
        ])
        generate_args = build_parser().parse_args([
            "generate-puzzle-session",
            "data/protocol/catalog.json",
            "--output",
            "data/protocol/session.json",
            "--session-id",
            "night-001",
            "--count",
            "4",
            "--seed",
            "17",
        ])

        self.assertEqual(import_args.command, "import-puzzles")
        self.assertEqual(import_args.input, Path("puzzles.csv"))
        self.assertEqual(generate_args.command, "generate-puzzle-session")
        self.assertEqual(generate_args.count, 4)
        self.assertEqual(generate_args.seed, 17)

    def test_cli_generates_four_unsolved_tasks_and_records_associations(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "source.json"
            catalog_path = tmp_path / "catalog.json"
            session_path = tmp_path / "session.json"
            source_path.write_text(
                json.dumps([
                    _puzzle(1).to_dict(),
                    _puzzle(2).to_dict(),
                    _puzzle(3).to_dict(),
                    _puzzle(4).to_dict(),
                    _puzzle(5).to_dict(),
                    _puzzle(6, known=True).to_dict(),
                    _puzzle(7, retired=True).to_dict(),
                ]),
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                import_code = main([
                    "import-puzzles",
                    str(source_path),
                    "--output",
                    str(catalog_path),
                ])
                attempt_code = main([
                    "record-puzzle-attempt",
                    str(catalog_path),
                    "--puzzle-id",
                    "p5",
                    "--response",
                    "Answer 5",
                    "--duration-seconds",
                    "45",
                    "--solved",
                ])
                generate_code = main([
                    "generate-puzzle-session",
                    str(catalog_path),
                    "--output",
                    str(session_path),
                    "--session-id",
                    "night-001",
                    "--count",
                    "4",
                    "--seed",
                    "9",
                ])

                session = load_night_puzzle_session(session_path)
                association_codes = [
                    main([
                        "record-association-check",
                        str(session_path),
                        "--catalog",
                        str(catalog_path),
                        "--puzzle-id",
                        puzzle_id,
                        "--response",
                        f"Answer {puzzle_id[1:]}",
                    ])
                    for puzzle_id in session.puzzle_ids
                ]
                updated = load_night_puzzle_session(session_path)

        self.assertEqual(import_code, 0)
        self.assertEqual(attempt_code, 0)
        self.assertEqual(generate_code, 0)
        self.assertEqual(association_codes, [0, 0, 0, 0])
        self.assertEqual(len(updated.puzzle_ids), 4)
        self.assertNotIn("p5", updated.puzzle_ids)
        self.assertEqual(len(updated.association_results), 4)
        self.assertTrue(all(result.matched for result in updated.association_results))


if __name__ == "__main__":
    unittest.main()
