from pathlib import Path
import tempfile
import unittest

from sanity import html_report, profile


class SanityTests(unittest.TestCase):
    def from_text(self, text, delimiter=","):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "data.csv")
            path.write_text(text, encoding="utf-8")
            return profile(path, delimiter)

    def test_demo_issues(self):
        report = profile("examples/support-tickets.csv")
        self.assertEqual((report["rows"], report["missing_cells"], report["duplicate_rows"]), (10, 2, 1))
        self.assertEqual(report["columns"][3]["kind"], "mixed")

    def test_bom_semicolon_and_numeric_range(self):
        report = self.from_text("\ufeffid;value\na;2.5\nb;-3\n", ";")
        self.assertEqual(report["columns"][1]["min"], "-3")
        self.assertEqual(report["columns"][1]["max"], "2.5")

    def test_missing_and_whitespace_duplicates(self):
        report = self.from_text("a,b\n x ,\nx,\n")
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertEqual(report["columns"][1]["missing_percent"], 100)

    def test_header_only(self):
        report = self.from_text("a,b\n")
        self.assertEqual(report["rows"], 0)
        self.assertIn("No data rows", report["warnings"])

    def test_bad_headers_and_ragged_rows(self):
        for text in ["", "a,a\n1,2", "a,\n1,2", "a,b\n1,2,3", "a,b\n1"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.from_text(text)

    def test_nonfinite_values_are_not_numeric(self):
        report = self.from_text("x\nNaN\nInfinity\n1\n")
        self.assertEqual(report["columns"][0]["kind"], "mixed")
        self.assertEqual(report["columns"][0]["numeric_count"], 1)

    def test_large_numbers_preserved(self):
        report = self.from_text("x\n1e400\n2e400\n")
        self.assertEqual(report["columns"][0]["min"], "1E+400")

    def test_quoted_newline_and_delimiter(self):
        report = self.from_text('name,description\na,"hello,\nworld"\n')
        self.assertEqual(report["rows"], 1)
        self.assertEqual(report["columns"][1]["top_values"][0]["value"], "hello,\nworld")

    def test_html_escapes_input(self):
        page = html_report(self.from_text('name\n<script>alert(1)</script>\n'))
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
