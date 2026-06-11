import unittest

from muse_tmr.data.ring_buffer import RingBuffer


class TestRingBuffer(unittest.TestCase):
    def test_rejects_non_positive_maxlen(self):
        with self.assertRaises(ValueError):
            RingBuffer(0)
        with self.assertRaises(ValueError):
            RingBuffer(-1)

    def test_append_keeps_insertion_order_within_capacity(self):
        buffer = RingBuffer(3)

        buffer.append(1)
        buffer.append(2)

        self.assertEqual(len(buffer), 2)
        self.assertEqual(list(buffer), [1, 2])

    def test_append_beyond_capacity_evicts_oldest_items(self):
        buffer = RingBuffer(3)

        for value in (1, 2, 3, 4, 5):
            buffer.append(value)

        self.assertEqual(len(buffer), 3)
        self.assertEqual(list(buffer), [3, 4, 5])

    def test_extend_appends_iterable_and_respects_capacity(self):
        buffer = RingBuffer(4)
        buffer.append(0)

        buffer.extend([1, 2, 3, 4])

        self.assertEqual(len(buffer), 4)
        self.assertEqual(list(buffer), [1, 2, 3, 4])

    def test_iteration_does_not_consume_items(self):
        buffer = RingBuffer(2)
        buffer.extend(["a", "b"])

        first_pass = list(buffer)
        second_pass = list(buffer)

        self.assertEqual(first_pass, ["a", "b"])
        self.assertEqual(second_pass, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
