import unittest

from muse_tmr.data.sample_types import EEGSample, MuseFrame


class TestSampleTypes(unittest.TestCase):
    def test_frame_reports_present_modalities(self):
        eeg = EEGSample(timestamp=1.0, channels_uv={"TP9": 0.1})
        frame = MuseFrame(timestamp=1.0, eeg=eeg, source="test")

        self.assertEqual(frame.modalities(), ("eeg",))


if __name__ == "__main__":
    unittest.main()
