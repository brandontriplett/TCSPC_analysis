import tempfile
import unittest
from pathlib import Path

from tcspc.grouping import parse_folder, unique_emitters, metas_at, match_pl, round_coord
from tcspc.measurements import PLMapMeasurement
from tcspc.parsers import FilenameParser

from tests.support import write_pl, write_spectrum


class GroupingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_folder_reports_unmatched(self):
        write_spectrum(self.folder)
        (self.folder / "notes.csv").write_text("not a measurement\n")
        metas, unmatched = parse_folder(self.folder)
        self.assertEqual(len(metas), 1)
        self.assertEqual(len(unmatched), 1)
        self.assertTrue(unmatched[0].endswith("notes.csv"))

    def test_unique_emitters_rounds_and_dedupes(self):
        write_spectrum(self.folder, x="10.0", y="20.0")
        write_spectrum(self.folder, x="10.04", y="20.0")  # same bin as 10.0
        # second file would overwrite if same name — use parse_files via distinct names
        # 10.04 still produces Spectrum_X10.04_... which is a different filename
        metas, unmatched = parse_folder(self.folder)
        self.assertEqual(unmatched, [])
        emitters = unique_emitters(metas)
        self.assertEqual(emitters, [(10.0, 20.0)])

    def test_unique_emitters_keeps_distinct_points(self):
        write_spectrum(self.folder, x="10.0", y="20.0")
        write_spectrum(self.folder, x="11.0", y="20.0")
        metas, _ = parse_folder(self.folder)
        self.assertEqual(unique_emitters(metas), [(10.0, 20.0), (11.0, 20.0)])

    def test_metas_at_filters_by_type_and_coord(self):
        write_spectrum(self.folder, x="10.0", y="20.0")
        write_spectrum(self.folder, x="11.0", y="20.0")
        metas, _ = parse_folder(self.folder)
        found = metas_at(metas, 10.0, 20.0, "Spectrum")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].x, 10.0)

    def test_match_pl_picks_tile_containing_point(self):
        write_pl(self.folder, x="10.0", y="20.0")  # size 20 → extent 0–20, 10–30
        meta = FilenameParser.parse(str(next(self.folder.glob("PL_*.csv"))))
        pl = PLMapMeasurement(meta)
        self.assertIsNotNone(match_pl([pl], 10.0, 20.0))
        self.assertIsNone(match_pl([pl], 100.0, 100.0))

    def test_round_coord(self):
        self.assertEqual(round_coord(10.04), 10.0)
        self.assertEqual(round_coord(10.0), 10.0)


if __name__ == "__main__":
    unittest.main()
