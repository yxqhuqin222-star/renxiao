import unittest

from app import _table_aggregate


class TestAppAggregates(unittest.TestCase):
    def test_table_aggregate_uses_source_denominators(self):
        rows = [
            {
                "日期": "2026-08-01",
                "流转模式": "大神",
                "线路成本": 10.0,
                "单例子结算成本": 100.0,
                "单量": 10.0,
                "出勤": 2.0,
                "人效单量": 10.0,
                "AI接通数": 100.0,
            },
            {
                "日期": "2026-08-01",
                "流转模式": "爆量算法池",
                "线路成本": 20.0,
                "单例子结算成本": 40.0,
                "单量": 30.0,
                "出勤": 3.0,
                "人效单量": 30.0,
                "AI接通数": 300.0,
            },
        ]

        aggregate = _table_aggregate(rows)

        self.assertEqual("8.0", aggregate["efficiency"])
        self.assertEqual("55.0", aggregate["case_cost"])
        self.assertEqual("17.5", aggregate["line_cost"])
        self.assertEqual("10.00%", aggregate["rate"])
        self.assertEqual("40", aggregate["total_examples"])

    def test_table_aggregate_handles_empty_rows(self):
        self.assertEqual(
            {"efficiency": "-", "case_cost": "-", "line_cost": "-", "rate": "-", "total_examples": "-"},
            _table_aggregate([]),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
