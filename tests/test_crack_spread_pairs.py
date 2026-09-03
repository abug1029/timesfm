import unittest
from config.crack_spread_pairs import get_crack_pair, CRACK_SPREAD_PAIRS


class TestCrackPair(unittest.TestCase):
    def test_ta_pair(self):
        self.assertEqual(get_crack_pair("ta"), ("px", 0.655))

    def test_case_insensitive(self):
        self.assertEqual(get_crack_pair("TA"), ("px", 0.655))

    def test_no_pair_returns_none(self):
        self.assertIsNone(get_crack_pair("ss"))

    def test_ta_in_dict(self):
        self.assertIn("ta", CRACK_SPREAD_PAIRS)
