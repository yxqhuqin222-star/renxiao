import unittest
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import openpyxl

from period_data import build_period_rows, period_ranges, select_period_data
from app import _table_aggregate, _period_trend, app
from config import settings as S


class TestPeriodData(unittest.TestCase):
    def test_period_selection_uses_mapping_and_keeps_unmatched_sources(self):
        ranges = period_ranges([
            {"学部": "高中", "期次": "寒_1", "进量日期": "2026-10-30", "target_time": "2026-11-05"},
            {"学部": "高中", "期次": "寒_1", "进量日期": "2026-10-30", "target_time": "2026-11-05"},
        ])
        tongshi = [
            {"日期": "2026-10-29", "学部": "高中", "流量期次": "寒1期", "模式": "大神"},
            {"日期": "2026-11-05", "学部": "高中", "流量期次": "寒1期", "模式": "大神"},
            {"日期": "2026-11-05", "学部": "-", "流量期次": "寒1期", "模式": "大神"},
        ]
        zhuanhua = [
            {"日期": "2026-10-30", "流转模式": "大神", "单量": 20, "出勤": 5},
            {"日期": "2026-11-06", "流转模式": "大神", "单量": 50, "出勤": 5},
        ]
        t, z = select_period_data(tongshi, zhuanhua, ranges, ["高中"], ["寒1期"], [])
        self.assertEqual([tongshi[1]], t)
        self.assertEqual([zhuanhua[0]], z)

    def test_conflicting_period_dates_are_rejected(self):
        rows = [
            {"学部": "高中", "期次": "秋_5", "进量日期": "2026-09-05", "target_time": "2026-09-11"},
            {"学部": "高中", "期次": "秋_5", "进量日期": "2026-09-03", "target_time": "2026-09-11"},
        ]
        with self.assertRaisesRegex(ValueError, "高中/秋5期"):
            period_ranges(rows)

    def test_period_aggregate_keeps_workforce_without_traffic_and_missing_cost(self):
        ranges = {("高中", "寒1期"): ("2026-10-30", "2026-11-05"),
                  ("初中", "寒1期"): ("2026-10-30", "2026-11-05")}
        tongshi = [
            {"日期": "2026-11-01", "模式": "大神", "学部": "高中", "流量期次": "寒1期", "例子数": 10, "AI接通数": 100, "话单分钟数": 100},
            {"日期": "2026-11-02", "模式": "大神", "学部": "高中", "流量期次": "寒1期", "例子数": 5, "AI接通数": 50, "话单分钟数": 20},
        ]
        zhuanhua = [
            {"日期": "2026-10-30", "流转模式": "大神", "单量": 10, "出勤": 5},
            {"日期": "2026-11-01", "流转模式": "大神", "单量": 30, "出勤": 5},
        ]
        rows, work = build_period_rows(tongshi, zhuanhua, [], ranges, [], ["寒1期"], [], rules=[])
        self.assertEqual(2, len(work))
        self.assertEqual("4.0", _table_aggregate(rows, work)["efficiency"])
        self.assertEqual("-", _table_aggregate(rows, work)["case_cost"])
        self.assertEqual(1, len(_period_trend(rows)))
        self.assertEqual(2, len(_period_trend(rows, rate=True)))

    def test_dashboard_and_download_use_full_period(self):
        ranges = {("高中", "寒1期"): ("2026-10-30", "2026-11-05")}
        traffic = [{"日期": "2026-11-02", "模式": "大神", "学部": "高中", "流量期次": "寒1期", "例子数": 10, "AI接通数": 100, "话单分钟数": 100}]
        work = [{"日期": "2026-10-30", "流转模式": "大神", "单量": 30, "出勤": 10},
                {"日期": "2026-11-02", "流转模式": "大神", "单量": 20, "出勤": 5}]
        with tempfile.TemporaryDirectory() as temp, patch.object(S, "DB_PATH", Path(temp) / "test.db"), patch.object(S, "SEED_DB_PATH", Path(temp) / "missing.db"), patch("app._period_sources", return_value=(ranges, traffic, work, [])):
            client = app.test_client()
            response = client.get("/", query_string={"table_period": "寒1期", "table_xuebu": "高中"})
            self.assertEqual(200, response.status_code)
            html = response.get_data(as_text=True)
            self.assertIn("所选期次完整日期", html)
            self.assertIn("2026-11-02", html)
            self.assertIn(">3.3<", html)
            download = client.get("/download", query_string={"table_period": "寒1期", "table_xuebu": "高中"})
            workbook = openpyxl.load_workbook(io.BytesIO(download.data), read_only=True)
            self.assertIn("流量期次", next(workbook.active.values))


if __name__ == "__main__":
    unittest.main()
