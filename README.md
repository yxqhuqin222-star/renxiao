# Renxiao Dashboard

人效数据看板，用 Flask 展示上传表计算后的成本、转化率、趋势图和明细表。

## 本地运行

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py

打开 http://127.0.0.1:8000/。

## 线上部署

项目已按 Vercel Python/Flask 入口适配：

- `app.py` 暴露顶层 `app = Flask(__name__)`
- `vercel.json` 将所有请求转给 Flask
- Vercel 环境下会把随仓库发布的 `data/dashboard.db` 复制到 `/tmp/renxiao-data/dashboard.db` 作为运行数据

注意：Vercel serverless 的 `/tmp` 不是长期持久数据库。线上页面可公开查看；如果要让多人长期上传并保存数据，应改接持久化数据库。
