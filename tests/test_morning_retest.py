import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from muse_tmr.cli.main import main
from muse_tmr.protocol import (
    NightPuzzleSession,
    PuzzleCatalog,
    PuzzleCueAssignment,
    PuzzleTask,
)
from muse_tmr.reports import (
    MorningRetest,
    MorningRetestResult,
    build_morning_retest,
    load_morning_retest,
)


class TestMorningRetest(unittest.TestCase):
    def test_retest_round_trips_json_and_counts_solved_results(self):
        retest = MorningRetest(
            retest_id="retest-001",
            session_id="night-001",
            reported_at_utc="2026-05-13T00:00:00+00:00",
            results=(
                MorningRetestResult("p1", "Answer 1", True, 12.0, 0.8),
                MorningRetestResult("p2", "wrong", False, 18.0, 0.4),
            ),
        )

        loaded = MorningRetest.from_dict(retest.to_dict())

        self.assertEqual(loaded.retest_id, "retest-001")
        self.assertEqual(loaded.solved_count, 1)
        self.assertEqual(loaded.unsolved_count, 1)
        self.assertEqual(loaded.mean_duration_seconds, 15.0)

    def test_build_retest_adds_blind_condition_and_cue_ids_for_analysis(self):
        session, catalog, assignment = _session_catalog_assignment()
        retest = build_morning_retest(
            session,
            (
                MorningRetestResult("p1", "Answer 1", True, 12.0, 0.9),
                MorningRetestResult("p2", "wrong", False, 24.0, 0.3),
            ),
            catalog=catalog,
            assignment=assignment,
        )

        self.assertEqual([result.puzzle_id for result in retest.results], ["p1", "p2"])
        self.assertEqual([result.blind_index for result in retest.results], [1, 2])
        self.assertEqual([result.cue_id for result in retest.results], ["cue-p1", "cue-p2"])
        self.assertEqual([result.cue_condition for result in retest.results], ["cued", "uncued"])
        self.assertTrue(retest.results[0].solved)
        self.assertFalse(retest.results[1].solved)

    def test_build_retest_requires_complete_session_results_by_default(self):
        session, catalog, assignment = _session_catalog_assignment()

        with self.assertRaises(ValueError):
            build_morning_retest(
                session,
                (MorningRetestResult("p1", "Answer 1", True, 12.0, 0.9),),
                catalog=catalog,
                assignment=assignment,
            )

    def test_build_retest_rejects_unknown_puzzle_results(self):
        session, catalog, assignment = _session_catalog_assignment()

        with self.assertRaises(ValueError):
            build_morning_retest(
                session,
                (
                    MorningRetestResult("p1", "Answer 1", True, 12.0, 0.9),
                    MorningRetestResult("p3", "Answer 3", False, 14.0, 0.4),
                ),
                catalog=catalog,
                assignment=assignment,
                require_complete=False,
            )

    def test_cli_records_complete_blind_retest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            session_path = tmp_path / "session.json"
            catalog_path = tmp_path / "catalog.json"
            assignment_path = tmp_path / "assignment.json"
            retest_path = tmp_path / "morning_retest.json"
            session, catalog, assignment = _session_catalog_assignment()
            session.save(session_path)
            catalog.save(catalog_path)
            assignment.save(assignment_path)

            with redirect_stdout(io.StringIO()):
                code = main([
                    "record-puzzle-retest",
                    str(session_path),
                    "--catalog",
                    str(catalog_path),
                    "--assignment",
                    str(assignment_path),
                    "--output",
                    str(retest_path),
                    "--result",
                    "p1=Answer 1",
                    "--result",
                    "p2=wrong",
                    "--solved",
                    "p1",
                    "--duration",
                    "p1=12",
                    "--duration",
                    "p2=24",
                    "--confidence",
                    "p1=0.9",
                    "--confidence",
                    "p2=0.3",
                ])

            retest = load_morning_retest(retest_path)
            payload = json.loads(retest_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(retest.solved_count, 1)
        self.assertEqual(retest.unsolved_count, 1)
        self.assertEqual([result.cue_condition for result in retest.results], ["cued", "uncued"])
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["result_count"], 2)


def _session_catalog_assignment():
    session = NightPuzzleSession(
        session_id="night-001",
        puzzle_ids=("p1", "p2"),
        puzzle_count=2,
    )
    catalog = PuzzleCatalog(
        puzzles=(
            PuzzleTask("p1", "Puzzle 1", "Answer 1", cue_id="cue-p1"),
            PuzzleTask("p2", "Puzzle 2", "Answer 2", cue_id="cue-p2"),
        )
    )
    assignment = PuzzleCueAssignment(
        session_id="night-001",
        cued_puzzle_ids=("p1",),
        uncued_puzzle_ids=("p2",),
        seed=17,
    )
    return session, catalog, assignment


if __name__ == "__main__":
    unittest.main()
