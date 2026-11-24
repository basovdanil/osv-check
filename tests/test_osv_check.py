import csv
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osv_check  # noqa: E402

CLEAN = [
    ["50", "Касса", "активный", 1000, 0, 500, 200, 1300, 0],
    ["60", "Расчёты с поставщиками", "пассивный", 0, 1000, 200, 500, 0, 1300],
]
HEADER = list(osv_check.COLUMNS)


def write_csv(rows, header=HEADER):
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8", newline="")
    with handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return handle.name


def run(rows):
    return osv_check.check([dict(zip(HEADER, row)) for row in rows])


class CheckTests(unittest.TestCase):
    def test_clean_ledger_has_no_findings(self):
        findings, totals = run(CLEAN)
        self.assertEqual(findings, [])
        self.assertEqual(totals["close_debit"], 1300)
        self.assertEqual(totals["close_credit"], 1300)

    def test_credit_balance_on_active_account_is_red(self):
        rows = [row[:] for row in CLEAN]
        rows[0][7], rows[0][8] = 0, 1300
        rows[0][5], rows[0][6] = 200, 500
        findings, _ = run(rows)
        self.assertIn({"code": "red_balance", "account": "50", "value": 1300}, findings)

    def test_debit_balance_on_passive_account_is_red(self):
        rows = [row[:] for row in CLEAN]
        rows[1][7], rows[1][8] = 1300, 0
        rows[1][5], rows[1][6] = 500, 200
        findings, _ = run(rows)
        self.assertIn({"code": "red_balance", "account": "60", "value": 1300}, findings)

    def test_broken_row_arithmetic(self):
        rows = [row[:] for row in CLEAN]
        rows[0][7] = 1500
        findings, _ = run(rows)
        self.assertIn({"code": "row_mismatch", "account": "50", "value": 200}, findings)

    def test_negative_turnover(self):
        rows = [row[:] for row in CLEAN]
        rows[0][6] = -50
        rows[0][7] = 1450
        findings, _ = run(rows)
        self.assertIn({"code": "negative_turnover", "account": "50", "value": -50}, findings)

    def test_unbalanced_totals(self):
        rows = [row[:] for row in CLEAN]
        rows[1][6] = 300
        rows[1][8] = 1100
        findings, _ = run(rows)
        self.assertIn({"code": "totals_turn", "account": "", "value": 200}, findings)
        self.assertIn({"code": "totals_close", "account": "", "value": 200}, findings)

    def test_unknown_account_type_is_reported(self):
        rows = [row[:] for row in CLEAN]
        rows[0][2] = "смешанный"
        findings, _ = run(rows)
        self.assertIn({"code": "unknown_type", "account": "50", "value": 0.0}, findings)


class ParseTests(unittest.TestCase):
    def test_number_formats_from_1c(self):
        cases = {
            "1 234 567,89": 1234567.89,
            "1\u00a0234\u00a0567,89": 1234567.89,
            "(1 000)": -1000.0,
            "": 0.0,
            "—": 0.0,
            "-12,5": -12.5,
            42: 42.0,
        }
        for raw, expected in cases.items():
            self.assertEqual(osv_check.parse_num(raw), expected, raw)

    def test_garbage_raises(self):
        with self.assertRaises(osv_check.BadFile):
            osv_check.parse_num("нет данных")


class CliTests(unittest.TestCase):
    def test_missing_column_returns_3(self):
        path = write_csv([["50", "Касса", "активный", 1, 0, 0, 0, 1, 0]],
                         header=HEADER[:-1])
        self.assertEqual(osv_check.main([path]), 3)
        os.unlink(path)

    def test_clean_file_returns_0(self):
        path = write_csv(CLEAN)
        self.assertEqual(osv_check.main([path]), 0)
        os.unlink(path)

    def test_findings_return_4(self):
        rows = [row[:] for row in CLEAN]
        rows[0][7] = 1500
        path = write_csv(rows)
        self.assertEqual(osv_check.main([path]), 4)
        os.unlink(path)

    def test_expect_match_returns_0(self):
        rows = [row[:] for row in CLEAN]
        rows[0][7] = 1500
        path = write_csv(rows)
        expected = os.path.join(os.path.dirname(path), "expected.json")
        with open(expected, "w", encoding="utf-8") as handle:
            json.dump([["row_mismatch", "50", 200.0], ["totals_close", "", 200.0]], handle)
        self.assertEqual(osv_check.main([path, "--expect", expected]), 0)
        os.unlink(expected)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
