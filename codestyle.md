# 代码规范

本项目参考以下公开规范：

- Python：PEP 8，遵循清晰命名、合理行宽、显式异常处理和模块职责分离。
- JavaScript：MDN JavaScript Guide，优先使用 `const`，异步请求统一处理错误和加载状态。
- HTML/CSS：Web Interface Guidelines，保证语义化结构、键盘焦点、移动端适配和减少动画支持。

## 项目约定

- 数据访问集中在 `src/storage.py`，分析逻辑集中在 `src/analysis.py`。
- API 只返回 JSON，不在前端复制数据库聚类逻辑。
- 论文唯一标识优先使用 DBLP key；本地 PDF 使用文件内容哈希；用户临时导入使用标题哈希。
- 所有外部数据源都记录来源、查询词和抓取时间。
- 生成的 SQLite、原始响应、缓存文件和 Python 字节码不提交到仓库。
