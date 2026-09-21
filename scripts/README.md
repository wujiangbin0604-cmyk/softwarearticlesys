# DBLP 论文元数据采集器

dblp_fetch.py 使用 DBLP 官方出版物 Search API：

https://dblp.org/search/publ/api

程序只请求公开书目元数据，不绕过验证码或访问控制。它使用 JSON 格式、分页参数 h / f、描述性 User-Agent 和请求间隔。摘要与作者关键词不保证由 DBLP Search API 返回，因此输出中的 abstract 和 keywords 默认是空值，后续需要从会议官网或论文页面做合规补全。

## 最小测试

powershell
py -3 scripts/dblp_fetch.py --query "venue:CVPR year:2025" --limit-per-query 3 --output data/dblp_cvpr_2025_sample.json

## 下载三大顶会近年数据

powershell
py -3 scripts/dblp_fetch.py --venue CVPR ICCV ECCV --year 2022 2023 2024 2025 --limit-per-query 1000 --sleep 1 --output data/dblp_cvpr_iccv_eccv.json --raw-output data/dblp_raw_responses.json --sqlite data/visionpulse.sqlite3

limit-per-query 最大为 1000，这是 DBLP API 单次返回上限。程序会对每个“会议 + 年份”查询分页，并按 DBLP key、DOI 或标题去重。

## 输出字段

- title：论文题目
- authors：作者列表
- venue、year、paper_type
- doi、dblp_url、dblp_key
- electronic_edition：电子版链接
- abstract、keywords：预留给后续论文内容补全

数据来源和采集时间会写入 JSON 顶层字段，博客中需要据此说明 DBLP 数据来源。