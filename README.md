# VisionPulse 顶会热词统计平台

> 软件工程实践第二次作业：与 AI 结对编程
> 姓名：吴江彬　学号：102400329　版本：1.0.0

VisionPulse 面向计算机视觉论文调研，聚合 CVPR、ICCV、ECCV 论文数据，提供论文导入、论文管理、摘要查看、关键词关联、Top 10 热门方向、机器学习聚类和年度热词趋势分析。

## 项目链接

| 项目 | 地址 |
|---|---|
| 华为云 CodeArts | https://devcloud.cn-north-4.huaweicloud.com/codehub/project/a62810e0bb1b4bf8b73eeeee62deb600/codehub/3089096/repo |
| GitHub 镜像 | https://github.com/wujiangbin0604-cmyk/softwarearticlesys |
| Figma 原型 | https://www.figma.com/design/aWuwppm5d8j1Gqj7OE270T |
| 云服务器地址 | http://134.175.39.222:8000 |

华为云 CodeArts 是课程提交和版本管理的主仓库，GitHub 用于代码镜像和服务器压缩包更新。

## 课程要求对应关系

| 课程要求 | 项目实现 |
|---|---|
| 论文爬取/导入 | 单篇标题检索、批量标题导入、JSON 导入、摘要和原文链接 |
| 论文列表管理 | 新增、编辑、删除、精确查询和模糊查询 |
| Top 10 热门方向 | TF-IDF 特征和 K-Means 聚类 |
| 关键词图谱 | 关键词统计、关键词与论文关联 |
| 多年热词走势 | 按关键词、会议、年份统计并播放变化 |
| 专用原型工具 | Figma 页面、交互说明和发布链接 |
| AI 结对编程 | 需求分析、编码、调试、人工审查和运行验证 |
| 云端部署 | 华为云 CodeArts 管理代码，云服务器使用 Docker |

## 功能页面

- 首页 / 热门方向
- 热度走势对比
- 论文列表管理
- 论文爬取 / 导入
- 论文详情 / 关于
- 年度热词演变
- 分析报告下载

## 技术架构

~~~text
浏览器 prototype.html
        |
        v
Python app.py HTTP API
        |
        v
HybridPaperService
        |
        +-- PaperStore / SQLite
        +-- AnalysisEngine
              +-- TF-IDF
              +-- K-Means
              +-- 关键词关联
              +-- 年度趋势
~~~

前端使用 HTML、CSS 和 JavaScript，后端使用 Python HTTP 服务，数据库使用 SQLite，依赖通过 Docker 固化。

## 数据来源与统计口径

系统采用本地优先策略：先查询 SQLite 缓存，未命中时再请求公开元数据服务。论文元数据主要来自本地课程数据、OpenAlex 和 Crossref。摘要按需补全，外部接口限流或没有公开摘要时不会伪造摘要。

OpenAlex 的摘要可能以 abstract_inverted_index 返回，程序会重建为文本。趋势只统计同时具有会议名和年份的论文。

课程演示需要补齐会议字段时，可以配置 DEMO_VENUE_MAPPING=1。该模式只填充空会议字段，不覆盖已有数据。

## 机器学习亮点

- TF-IDF：英文停用词过滤、1-gram/2-gram、最多 4000 个特征。
- K-Means：根据数据量自动选择聚类数，最多 10 类，固定 random_state=42 和 n_init=10。
- 聚类中心的高权重词生成研究方向标签。
- 关键词按文档频率和 TF-IDF 权重统计。
- 趋势按 keyword、venue、year 聚合。

主要代码：

- app.py：API 路由和错误响应。
- src/storage.py：SQLite 存储和增删改查。
- src/hybrid_service.py：本地优先查询和摘要回退。
- src/analysis.py：TF-IDF、K-Means、关键词和趋势分析。
- prototype.html：页面交互、图谱、趋势播放和报告下载。

## 华为云部署

服务器目录为 /opt/visionpulse，容器对外提供 TCP 8000，数据持久化在 /opt/visionpulse/data。

首次部署：

~~~bash
cd /opt/visionpulse
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 visionpulse
~~~

.env 至少配置：

~~~env
IMPORT_TOKEN=请设置随机令牌
FRONTEND_ORIGIN=*
DEMO_VENUE_MAPPING=0
~~~

健康检查：

~~~bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/analytics/summary
curl http://127.0.0.1:8000/api/analytics/trends
~~~

云服务器安全组需要放行 TCP 8000，正式环境建议使用 Nginx 和 HTTPS。

## 1.0.0 发布规则

项目采用 dev 开发、main 发布的分支流程。

发布前执行：

~~~bash
git checkout dev
git pull origin dev
py -m unittest discover -s tests -v
git diff --check
git status
~~~

提交并推送：

~~~bash
git add .
git commit -m  release: prepare VisionPulse 1.0.0
git push origin dev
~~~

合并到 main 并创建标签：

~~~bash
git checkout main
git pull origin main
git merge --no-ff dev -m merge: release VisionPulse 1.0.0
git push origin main
git tag -a v1.0.0 -m VisionPulse 1.0.0
git push origin v1.0.0
~~~

1.0.0 发布前确认：

- dev 和 main 分支内容正确；
- v1.0.0 标签指向发布提交；
- 至少 15 次真实、合理的 commit；
- 不提交 .env、令牌、真实 SQLite、论文 PDF 和本地盘符路径；
- Docker 能启动，三个 API 健康检查可访问；
- 博客、Figma 链接、云服务器地址和截图已补齐。

## 测试

~~~bash
py -m unittest discover -s tests -v
~~~

重点覆盖空数据库分析、导入自动刷新、论文增删改、关键词关联、趋势过滤、本地优先搜索、摘要匹配和导入令牌校验。

## 安全规范

- 不提交 .env 和真实令牌。
- 不提交论文 PDF、真实数据库和本地盘符路径。
- 修改、删除和批量导入必须携带 X-Import-Token。
- 生产环境不要使用通配符跨域。
- 博客中区分真实数据、演示数据和外部接口失败情况。

## 作业材料清单

- 华为云 CodeArts 仓库链接
- v1.0.0 Release 或标签
- dev 到 main 的合并记录
- 至少 15 次真实 commit
- Figma 原型链接和交互截图
- 云服务器访问地址
- PSP 表格和 NABCD 分析
- 三组 AI 结对编程案例
- 至少 10 张功能截图或 GIF
- 约 300 行关键代码说明
- 测试结果和部署日志

## 相关文档

- 博客提交版.md
- 部署说明.md
- 混合采集说明.md
- 数据源调研.md
- Figma制作说明.md
- 原型交互说明.md
- codestyle.md

