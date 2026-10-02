import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from tcspc.report import generate_pdf_report
from tcspc.batch import run_pipeline
from tests.support import write_g2, write_lifetime, write_pl, write_spectrum


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_writes_pdf_and_skips_junk(self):
        write_spectrum(self.folder)
        write_pl(self.folder)
        (self.folder / "readme.csv").write_text("nope\n")
        dest = self.folder / "out.pdf"
        result = generate_pdf_report(data_folder=self.folder, output_filename=dest)
        self.assertEqual(result, str(dest))
        self.assertTrue(dest.is_file())
        self.assertGreater(dest.stat().st_size, 0)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.out = self.folder / "summaries"

    def tearDown(self):
        self.tmp.cleanup()

    def test_batch_writes_summaries_using_full_histogram(self):
        write_lifetime(self.folder, n=30)
        write_g2(self.folder, n=40)
        written = run_pipeline(self.folder, output_dir=self.out)
        names = {p.name for p in written}
        self.assertIn("summary_lifetime.csv", names)
        self.assertIn("summary_g2.csv", names)
        # One row per input file — would be empty/wrong if iloc[0] crashed the fit path
        life_rows = (self.out / "summary_lifetime.csv").read_text().strip().splitlines()
        g2_rows = (self.out / "summary_g2.csv").read_text().strip().splitlines()
        self.assertEqual(len(life_rows) - 1, 1)
        self.assertEqual(len(g2_rows) - 1, 1)


if __name__ == "__main__":
    unittest.main()
