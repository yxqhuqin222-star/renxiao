"""Data dashboard settings: paths, headers, and cost rules."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_DATA_DIR = BASE_DIR / "data"
IS_VERCEL = bool(os.environ.get("VERCEL"))
DATA_DIR = Path("/tmp/renxiao-data") if IS_VERCEL else SEED_DATA_DIR
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "dashboard.db"
SEED_DB_PATH = SEED_DATA_DIR / "dashboard.db"
OUTPUT_DIR = BASE_DIR / "output"
FIXED_TONGSHI_PATH = UPLOAD_DIR / "tongshi_demo.xlsx"
FIXED_ZHUANHUA_PATH = UPLOAD_DIR / "zhuanhua_demo.xlsx"

RESULT_HEADERS = [
    "日期",
    "流转模式",
    "学部",
    "人效",
    "单量",
    "线路成本",
    "单例子结算成本",
    "接通转化率",
]

TONGSHI_REQUIRED = {"日期", "模式", "学部", "AI接通数", "例子数", "话单分钟数"}
ZHUANHUA_REQUIRED = {"日期", "流转模式", "单量", "出勤"}

LABOR_COST_RULES = {
    "爆量算法池": 30.0,
    "爆量再植课": 30.0,
    "爆量未加微": 28.0,
    "9.9池": 90.0,
    "爆量本地化": 50.0,
}
LINE_ONLY_COST_MODES = set()
DSHEN_LABOR_NUMERATOR = 395.0
DSHEN_LABOR_EXTRA = 7.0
LINE_COST_UNIT = 0.085
COST_DECIMALS = 4

XUBU_ORDER = {"小学": 1, "初中": 2, "高中": 3}
XUBU_WHITELIST = list(XUBU_ORDER.keys())
MODE_ORDER = {"大神": 1, "9.9池": 2, "爆量算法池": 3, "爆量再植课": 4, "爆量未加微": 5, "爆量本地化": 6}

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
HOST = "0.0.0.0"
PORT = 8000
