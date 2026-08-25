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

### GitHub Pages 静态前端（只读看板）

执行下面命令可以导出当前首页的**只读快照**到 `docs/index.html`，用于 GitHub Pages 公网访问：

    .venv/bin/python scripts/export_readonly.py

该脚本会剥离上传表单、下载链接和后端请求，只保留查看功能（趋势图、筛选、结果表、汇总和每日播报）。筛选在浏览器本地执行；上传、下载和重新计算仍需要本地 Flask 服务。重新发布时直接运行此命令并推送 `docs/` 即可。
