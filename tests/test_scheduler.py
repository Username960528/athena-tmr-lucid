import unittest

from muse_tmr.audio import VolumeCalibration
from muse_tmr.protocol.tmr_scheduler import (
    CueDecision,
    arousal_guard_decision,
    calibrated_cue_decision,
)


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

    def test_calibrated_cue_decision_uses_calibrated_max_volume(self):
        calibration = VolumeCalibration(
            device_name="Bedroom Headphones",
            detectable_volume=0.02,
            identifiable_volume=0.04,
            comfortable_volume=0.08,
        )

        decision = calibrated_cue_decision((), calibration=calibration, fallback_max_volume=0.20)

        self.assertTrue(decision.should_play)
        self.assertEqual(decision.max_volume, 0.08)
        self.assertEqual(decision.calibration_device_name, "Bedroom Headphones")

    def test_calibrated_cue_decision_blocks_without_calibration(self):
        decision = calibrated_cue_decision((), calibration=None, fallback_max_volume=0.20)

        self.assertFalse(decision.should_play)
        self.assertEqual(decision.max_volume, 0.20)
        self.assertEqual(decision.reason_codes, ("volume_calibration_missing",))

    def test_calibrated_cue_decision_keeps_arousal_block_reasons(self):
        calibration = VolumeCalibration("Bedroom", 0.02, 0.04, 0.08)

        decision = calibrated_cue_decision(
            ("motion_arousal_proxy", "motion_arousal_proxy"),
            calibration=calibration,
            fallback_max_volume=0.20,
        )

        self.assertFalse(decision.should_play)
        self.assertEqual(decision.max_volume, 0.08)
        self.assertEqual(decision.reason_codes, ("motion_arousal_proxy",))


if __name__ == "__main__":
    unittest.main()
