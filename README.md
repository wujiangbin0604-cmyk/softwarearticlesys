# VisionPulse 顶会热词统计平台

面向计算机视觉顶会论文的检索、管理与热词分析平台，研究范围限定为 CVPR、ICCV、ECCV。

## 当前功能

- 论文导入：支持本地 PDF 扫描、单篇题目导入和批量题目导入。
- 论文管理：标题精确查询、编号/会议/关键词模糊查询、详情、编辑和删除。
- 热门方向：对已入库论文使用 TF-IDF 向量化和 K-Means 无监督聚类，生成 Top 10 研究方向。
- 关键词图谱：按关键词统计论文数量，点击词条查看关联论文。
- 热度走势：按关键词、会议和年份统计论文数量，并以逐点动画展示；范围限定为 CVPR、ICCV、ECCV。
- 自动更新：定时扫描 `D:\百度网盘` 中已完成下载的 PDF，发现新论文后自动入库并刷新分析结果。

## 本地运行

```powershell
cd "E:\我的软件工程实践文件夹\顶会热词统计平台"
py -3 -m pip install -r requirements.txt
py -3 scripts\import_local_papers.py --root "D:\百度网盘"
py -3 app.py --no-online --port 8000
```

打开 `prototype.html` 即可查看页面。页面从 `http://127.0.0.1:8000` 读取实时分析结果；如果接口未启动，会保留演示数据并给出状态提示。

## 把本地论文迁移到 Render

Render 不能读取本机的 D:\百度网盘。先在本地导出 SQLite 中的完整论文元数据：

    py -3 scripts\export_papers.py --output C:\Temp\visionpulse-papers.json

在 Render 的 Environment 中新增 IMPORT_TOKEN，生成一段随机长字符串。然后在本地执行：

    py -3 scripts\upload_papers.py --input C:\Temp\visionpulse-papers.json --url https://softwarearticlesys.onrender.com --token "你的 IMPORT_TOKEN"

上传接口按批次写入完整元数据，导入后自动重新向量化和聚类。JSON 文件只用于迁移，不要提交到 GitHub。
## 数据与统计口径

- DBLP Search API：用于按论文题目进行公开书目检索和缓存。
- 本地 PDF：从文件名提取标题、会议和年份；当前导入脚本不绕过百度网盘未完成下载文件。
- 向量化：标题、摘要和关键词拼接后使用 TF-IDF，使用一元和二元词组。
- 聚类：K-Means，聚类数为 `min(10, max(2, round(sqrt(论文数))))`；单篇论文使用单簇降级策略。
- 热门方向：按簇内论文数量排序，簇标签由中心向量权重最高的词组组成。
- 热度：统计论文在指定年份、指定会议中出现的关键词论文数量，不把用户临时导入记录计入 CVPR/ICCV/ECCV 趋势。

## 项目结构

```text
app.py                         本地 HTTP API
prototype.html                 前端原型与交互页面
src/storage.py                 SQLite 持久化和分析触发
src/analysis.py                TF-IDF + K-Means 分析引擎
src/hybrid_service.py          本地优先查询与 DBLP 回退
scripts/import_local_papers.py 本地 PDF 批量导入
scripts/dblp_fetch.py          DBLP 公开 API 采集器
tests/                         单元测试
```

## 部署建议

GitHub Pages 可部署静态前端；Python API、SQLite、定时扫描和机器学习分析需要部署到云服务器或其他后端平台。部署前将前端的 API 地址改为后端 HTTPS 地址，不要提交真实数据库、PDF、网盘路径或密钥。

## AI 协作说明

AI 用于需求拆解、接口设计、代码草拟、调试建议和测试用例建议；关键实现经过人工检查，并通过 Python 单元测试、语法检查和接口回归验证。

## 华为云 CodeHub 提交

本项目的开发分支为 `dev`，论文系统代码、测试、脚本和部署文档均可提交到华为云 CodeHub；Figma 设计源文件不纳入代码推送。推送前应先运行：

```powershell
python -m unittest discover -s tests -v
```

然后确认工作区干净、提交信息描述实际改动，并推送到远程 `dev` 分支。数据库文件、PDF 原文、临时导出 JSON 和本地网盘路径不应提交。
