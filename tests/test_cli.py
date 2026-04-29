import unittest

from muse_tmr.cli.main import build_parser
from muse_tmr.sources.amused_source import AmusedSource


class TestCli(unittest.TestCase):
    def test_stream_command_parses_amused_source(self):
        args = build_parser().parse_args([
            "stream",
            "--source",
            "amused",
            "--duration-seconds",
            "3600",
        ])

        self.assertEqual(args.command, "stream")
        self.assertEqual(args.source, "amused")
        self.assertEqual(args.duration_seconds, 3600)

    def test_record_command_parses_overnight_duration(self):
        args = build_parser().parse_args([
            "record",
            "--source",
            "amused",
            "--duration-hours",
            "8",
        ])

        self.assertEqual(args.command, "record")
        self.assertEqual(args.duration_hours, 8.0)

    def test_amused_source_import_does_not_cycle(self):
        self.assertEqual(AmusedSource.strategy, "forked-source")


if __name__ == "__main__":
    unittest.main()
