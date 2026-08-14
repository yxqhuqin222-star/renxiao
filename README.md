# Renxiao Dashboard

人效数据看板，用 Flask 展示上传表计算后的成本、转化率、趋势图和明细表。

## 本地运行

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py

打开 http://127.0.0.1:8000/。

## 发布范围

本项目不部署到 Vercel。

当前只维护两类发布目标：

- 本地 Flask 服务：用于上传、重新计算、下载和完整交互。
- GitHub / GitHub Pages：用于保存代码和公开查看静态前端快照。

### GitHub Pages 静态前端

执行下面命令可以导出当前首页快照到 `docs/index.html`，用于 GitHub Pages：

    .venv/bin/python scripts/export_static.py

静态页适合公开查看前端仪表盘；上传、下载和重新计算仍需要 Flask 服务。
