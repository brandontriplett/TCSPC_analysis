import unittest
from pathlib import Path

from tcspc.parsers import FilenameParser

from tests.support import (
    g2_name,
    lifetime_name,
    pl_name,
    saturation_name,
    spectrum_name,
    stability_name,
)


class FilenameParserTests(unittest.TestCase):
    def test_each_supported_type(self):
        cases = {
            "PL": pl_name(),
            "Lifetime": lifetime_name(),
            "g2": g2_name(),
            "Spectrum": spectrum_name(),
            "Stability": stability_name(),
            "Saturation": saturation_name(),
        }
        for expected_type, name in cases.items():
            with self.subTest(type=expected_type):
                meta = FilenameParser.parse(f"/data/{name}")
                self.assertIsNotNone(meta, msg=f"failed to parse {name}")
                self.assertEqual(meta.type, expected_type)
                self.assertEqual(meta.x, 10.0)
                self.assertEqual(meta.y, 20.0)

    def test_spectrum_fields(self):
        meta = FilenameParser.parse(spectrum_name())
        self.assertEqual(meta.power, 10.0)
        self.assertEqual(meta.nd, 0.5)
        self.assertEqual(meta.integration_time, 5.0)

    def test_lifetime_tac_gain(self):
        meta = FilenameParser.parse(lifetime_name())
        self.assertEqual(meta.tac_range, 50.0)
        self.assertEqual(meta.gain, 1.0)
        self.assertEqual(meta.filter, "None")

    def test_stability_without_int_is_ok(self):
        import math

        meta = FilenameParser.parse("Stability_X1.0_Y2.0_ND0_Pow1_FilterLP600.csv")
        self.assertIsNotNone(meta)
        self.assertTrue(math.isnan(meta.integration_time))

    def test_junk_names_return_none(self):
        for name in ("random.csv", "Spectrum_bad.csv", "notes.txt"):
            with self.subTest(name=name):
                self.assertIsNone(FilenameParser.parse(name))

    def test_filepath_preserved(self):
        path = Path("/tmp/data") / spectrum_name()
        meta = FilenameParser.parse(str(path))
        self.assertEqual(meta.filepath, str(path))


if __name__ == "__main__":
    unittest.main()
