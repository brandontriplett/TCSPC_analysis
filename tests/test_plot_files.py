import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from tcspc.plotting import plot_paths
from tests.support import write_g2, write_spectrum


class PlotFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.out = self.folder / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_png_per_file(self):
        spec = write_spectrum(self.folder)
        g2 = write_g2(self.folder)
        saved, unmatched, errors, out_dir = plot_paths([spec, g2], out_dir=self.out)
        self.assertEqual(unmatched, [])
        self.assertEqual(errors, [])
        self.assertEqual(len(saved), 2)
        self.assertEqual(out_dir, self.out)
        self.assertTrue((self.out / f"{spec.stem}.png").is_file())
        self.assertTrue((self.out / f"{g2.stem}.png").is_file())

    def test_unparsed_file_is_skipped(self):
        junk = self.folder / "notes.csv"
        junk.write_text("1\t2\n")
        saved, unmatched, errors, _ = plot_paths([junk], out_dir=self.out)
        self.assertEqual(saved, [])
        self.assertEqual(errors, [])
        self.assertEqual(len(unmatched), 1)


if __name__ == "__main__":
    unittest.main()
