import unittest
import subprocess
from unittest.mock import patch

from app import (
    _daily_broadcast,
    _github_publish_blocker,
    _publish_env,
    _publish_readonly_snapshot,
    _table_aggregate,
    _table_daily_aggregates,
)


class TestAppAggregates(unittest.TestCase):
    def test_table_aggregate_uses_source_denominators(self):
        rows = [
            {
                "日期": "2026-08-01",
                "流转模式": "大神",
                "人效目标": 4.5,
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
                "人效目标": 9.0,
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
        self.assertEqual("7.2", aggregate["target"])
        self.assertEqual("55.0", aggregate["case_cost"])
        self.assertEqual("17.5", aggregate["line_cost"])
        self.assertEqual("10.00%", aggregate["rate"])
        self.assertEqual("40", aggregate["total_examples"])

    def test_table_aggregate_handles_empty_rows(self):
        self.assertEqual(
            {"efficiency": "-", "target": "-", "case_cost": "-", "line_cost": "-", "rate": "-", "total_examples": "-"},
            _table_aggregate([]),
        )

    def test_table_daily_aggregates_groups_by_date_desc(self):
        rows = [
            {
                "日期": "2026-08-01",
                "流转模式": "大神",
                "人效目标": 4.5,
                "线路成本": 10.0,
                "单例子结算成本": 100.0,
                "单量": 10.0,
                "出勤": 2.0,
                "人效单量": 10.0,
                "AI接通数": 100.0,
            },
            {
                "日期": "2026-08-02",
                "流转模式": "大神",
                "人效目标": 5.0,
                "线路成本": 20.0,
                "单例子结算成本": 120.0,
                "单量": 30.0,
                "出勤": 5.0,
                "人效单量": 30.0,
                "AI接通数": 300.0,
            },
            {
                "日期": "2026-08-01",
                "流转模式": "9.9池",
                "人效目标": 2.0,
                "线路成本": 30.0,
                "单例子结算成本": 60.0,
                "单量": 30.0,
                "出勤": 10.0,
                "人效单量": 30.0,
                "AI接通数": 300.0,
            },
        ]

        daily = _table_daily_aggregates(rows)

        self.assertEqual(["2026-08-02", "2026-08-01"], [row["date"] for row in daily])
        self.assertEqual("6.0", daily[0]["efficiency"])
        self.assertEqual("3.3", daily[1]["efficiency"])
        self.assertEqual("2.4", daily[1]["target"])
        self.assertEqual("40", daily[1]["total_examples"])

    def test_daily_broadcast_uses_latest_costs_and_deduped_efficiency(self):
        rows_by_date = {
            "2026-08-24": [
                {
                    "日期": "2026-08-24",
                    "流转模式": "9.9池",
                    "学部": "初中",
                    "人效目标": 2.0,
                    "线路成本": 99.64,
                    "单例子结算成本": 189.64,
                    "单量": 50.0,
                    "出勤": 33.0,
                    "人效单量": 89.0,
                    "AI接通数": 53972.0,
                },
                {
                    "日期": "2026-08-24",
                    "流转模式": "9.9池",
                    "学部": "高中",
                    "人效目标": 2.0,
                    "线路成本": 76.58,
                    "单例子结算成本": 166.58,
                    "单量": 32.0,
                    "出勤": 33.0,
                    "人效单量": 89.0,
                    "AI接通数": 25704.0,
                },
                {
                    "日期": "2026-08-24",
                    "流转模式": "爆量再植课",
                    "学部": "初中",
                    "人效目标": 6.7,
                    "线路成本": 22.58,
                    "单例子结算成本": 52.58,
                    "单量": 75.0,
                    "出勤": 24.0,
                    "人效单量": 231.0,
                    "AI接通数": 18267.0,
                },
                {
                    "日期": "2026-08-24",
                    "流转模式": "爆量再植课",
                    "学部": "高中",
                    "人效目标": 6.7,
                    "线路成本": 9.4,
                    "单例子结算成本": 39.4,
                    "单量": 145.0,
                    "出勤": 24.0,
                    "人效单量": 231.0,
                    "AI接通数": 13822.0,
                },
            ],
            "2026-08-23": [
                {
                    "日期": "2026-08-23",
                    "流转模式": "9.9池",
                    "学部": "初中",
                    "人效目标": 2.0,
                    "线路成本": 147.77,
                    "单例子结算成本": 237.77,
                    "单量": 43.0,
                    "出勤": 30.0,
                    "人效单量": 80.0,
                    "AI接通数": 10000.0,
                }
            ],
            "2026-08-17": [],
        }

        def fake_fetch_filtered(view="latest", **kwargs):
            return rows_by_date.get(view, [])

        with patch("app.fetch_filtered", side_effect=fake_fetch_filtered):
            broadcast = _daily_broadcast("2026-08-24", ["9.9池", "爆量再植课"])

        self.assertEqual("302", broadcast["overview"]["total_examples"])
        self.assertEqual("5.6", broadcast["overview"]["efficiency"])
        self.assertEqual(4, broadcast["row_count"])
        junior = next(group for group in broadcast["groups"] if group["xuebu"] == "初中")
        pool = next(row for row in junior["rows"] if row["mode"] == "9.9池")
        self.assertEqual("99.6", pool["line_cost"])
        self.assertEqual("-48.1", pool["line_vs_yesterday"])
        self.assertEqual("-", pool["line_vs_last_week"])


class TestReadonlyPublish(unittest.TestCase):
    def test_publish_env_uses_system_proxy_when_launch_agent_has_no_shell_proxy(self):
        with patch.dict("os.environ", {}, clear=True), patch(
            "app._system_https_proxy_url", return_value="http://127.0.0.1:21081"
        ), patch("app._proxy_is_reachable", return_value=True):
            env = _publish_env()

        self.assertEqual("http://127.0.0.1:21081", env["HTTPS_PROXY"])
        self.assertEqual("http://127.0.0.1:21081", env["HTTP_PROXY"])
        self.assertEqual("http://127.0.0.1:21081", env["ALL_PROXY"])

    def test_publish_env_preserves_existing_shell_proxy(self):
        with patch.dict("os.environ", {"HTTPS_PROXY": "http://127.0.0.1:9999"}, clear=True), patch(
            "app._system_https_proxy_url", return_value="http://127.0.0.1:21081"
        ), patch("app._proxy_is_reachable", return_value=True):
            env = _publish_env()

        self.assertEqual("http://127.0.0.1:9999", env["HTTPS_PROXY"])

    def test_github_publish_blocker_reports_missing_proxy_before_slow_push(self):
        with patch("app._publish_env", return_value={}), patch("app.socket.create_connection", side_effect=OSError):
            message = _github_publish_blocker()

        self.assertIn("没有检测到可用 GitHub 代理", message)

    def test_publish_skips_commit_when_snapshot_has_no_change(self):
        calls = []

        def fake_run(args, timeout=120):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("app._run_publish_step", side_effect=fake_run):
            ok, message = _publish_readonly_snapshot()

        self.assertTrue(ok)
        self.assertIn("无需发布", message)
        self.assertEqual(
            [
                ["git", "diff", "--quiet", "HEAD", "--", "docs/index.html"],
            ],
            calls[1:],
        )

    def test_publish_commits_and_pushes_only_readonly_snapshot(self):
        calls = []

        def fake_run(args, timeout=120):
            calls.append(args)
            if args == ["git", "diff", "--quiet", "HEAD", "--", "docs/index.html"]:
                return subprocess.CompletedProcess(args, 1, "", "")
            if args == ["git", "diff", "--cached", "--quiet", "--", "docs/index.html"]:
                return subprocess.CompletedProcess(args, 1, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("app._run_publish_step", side_effect=fake_run):
            ok, message = _publish_readonly_snapshot()

        self.assertTrue(ok)
        self.assertIn("已同步公开页", message)
        self.assertEqual(["git", "add", "docs/index.html"], calls[2])
        self.assertEqual(["git", "commit", "-m", "chore: update dashboard data"], calls[4])
        self.assertEqual(["git", "push", "origin", "main"], calls[5])


if __name__ == "__main__":
    unittest.main(verbosity=2)
