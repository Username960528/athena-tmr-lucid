import unittest

from muse_tmr.protocol.randomization import split_cued_uncued


class TestRandomization(unittest.TestCase):
    def test_split_is_deterministic(self):
        first = split_cued_uncued(["a", "b", "c", "d"], seed=7)
        second = split_cued_uncued(["a", "b", "c", "d"], seed=7)

        self.assertEqual(first, second)
        self.assertEqual(len(first.cued), 2)
        self.assertEqual(len(first.uncued), 2)


if __name__ == "__main__":
    unittest.main()
