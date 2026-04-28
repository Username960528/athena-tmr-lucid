import unittest

from muse_tmr.protocol.tmr_scheduler import CueDecision


class TestSchedulerContracts(unittest.TestCase):
    def test_cue_decision_records_block_reason(self):
        decision = CueDecision(should_play=False, reason_codes=("not_rem",))

        self.assertFalse(decision.should_play)
        self.assertEqual(decision.reason_codes, ("not_rem",))


if __name__ == "__main__":
    unittest.main()
