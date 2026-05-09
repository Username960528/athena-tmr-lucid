import unittest

from muse_tmr.protocol.tmr_scheduler import CueDecision, arousal_guard_decision


class TestSchedulerContracts(unittest.TestCase):
    def test_cue_decision_records_block_reason(self):
        decision = CueDecision(should_play=False, reason_codes=("not_rem",))

        self.assertFalse(decision.should_play)
        self.assertEqual(decision.reason_codes, ("not_rem",))

    def test_arousal_guard_decision_blocks_when_reasons_exist(self):
        decision = arousal_guard_decision(("motion_arousal_proxy", "motion_arousal_proxy"))

        self.assertFalse(decision.should_play)
        self.assertEqual(decision.reason_codes, ("motion_arousal_proxy",))

    def test_arousal_guard_decision_allows_when_clear(self):
        decision = arousal_guard_decision(())

        self.assertTrue(decision.should_play)
        self.assertEqual(decision.reason_codes, ())


if __name__ == "__main__":
    unittest.main()
