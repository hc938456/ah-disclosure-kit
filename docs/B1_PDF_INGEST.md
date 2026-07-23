# B1 PDF Ingest

文档导航：[A0 文档索引](./A0_DOC_INDEX.md)

本文说明 PDF 下载后如何被处理，以及哪些产物是默认生成、哪些是按需生成。

## 1. 默认原则

只下载 PDF 时，不解析。

只有用户要求读取、分析、搜索、摘要、提取证据或后续问答时，才执行 PDF ingest。

## 2. 基础 ingest 链路

```text
PDF
-> 计算 md5 / sha256
-> 对比旧 meta.json 中的 sha256
-> hash 一致时复用 pages.jsonl，hash 不一致时重新解析
-> 生成 meta.json
-> PyMuPDF 按页抽文本
-> 生成 pages.jsonl
-> 生成 quality_report.json
-> 写入 SQLite document_pages 和 document_pages_fts
```

这些步骤都在本地 Python 中完成，不消耗大模型 token。

年报和招股书从官方来源下载时，先进入 `staging/downloads/`。工具使用一次按页抽取同时完成结构完整性、公司/股票代码和年度身份校验；通过后才移动到 `raw/`。如果用户同时要求分析，这批已抽取页面直接传给 ingest，避免完整性检查后再次解析整本 PDF。

校验通过后生成`validation_report.json`，并绑定文档ID、SHA-256、证券代码和文件类型。显式刷新官方来源时，如果URL对应的本地PDF内容未变化，将复用该记录；文件hash变化、身份不匹配或旧校验未通过时必须重新抽取和校验。

不完整候选会在 ingest 前从暂存区删除；无法可靠判断的扫描件或身份异常候选会保留在 `staging/review/`，等待 OCR 或人工复核。正式 `raw/` 目录中的既有文件不会因一次校验失败被自动删除。

## 3. 默认生成的产物

每份被解析的 PDF 默认生成：

- `meta.json`：文档元信息、来源、页数、hash、PDF 路径。
- `pages.jsonl`：按页抽取的文本，每行对应一页。
- `quality_report.json`：文本层质量、页字符数、低文本页判断。
- `validation_report.json`：年报或招股书的结构完整性、年度及公司身份校验结果；仅适用于经过高层来源校验流程的文件。
- SQLite FTS：统一全文检索索引。

`meta.json`、`pages.jsonl` 和 `quality_report.json` 使用临时文件加原子替换，避免中断后留下半成品。返回值中的 `cache_status` 会区分 `hit`、`miss`、`stale_hash_mismatch`、`stale_missing_hash`、`forced_overwrite` 和 `corrupt_cache`。

如果基础 ingest 已命中缓存，但本次新增要求表格、Markdown、全文文本或向量后端清单，Kit 会只生成缺失产物，不重复解析整份 PDF。返回值中的`cache_enhanced`和`enhancements_built`用于区分纯缓存命中与按需增强。

## 4. 默认不生成的产物

默认不生成：

- `full_text.txt`
- `document.md`
- embedding 向量索引（显式请求时只生成外部后端交接清单）
- 全量 OCR 结果

原因：

- `full_text.txt` 和 `document.md` 主要用于人工阅读，机器检索不需要。
- 全文 Markdown 会增加磁盘占用和处理时间。
- 大模型默认只需要相关页证据，不需要整本文档。

## 5. Markdown / TXT 什么时候生成

只有在以下情况生成：

- 用户明确要求导出 Markdown。
- 用户明确要求导出 TXT。
- 分析完成后，用户确认需要人工阅读便利文件。

## 6. OCR 什么时候触发

OCR 是本地能力，不需要联网，也不依赖 LLM。

默认 `ocr="auto"` 时，先提取 PDF 原生文本，再只对低文本且图像占比较高的疑似扫描页，或确实不可读的乱码页触发局部 OCR。

质量判断同时检查字符数量、可读词组、控制字符/乱码比例和页面图像占比。PDF 表格中用于分隔单元格的布局控制字符会先规范化为空格，不会仅因控制字符较多就把可读页面判为乱码。部分官方 PDF 会包含大量不可用的字体编码文本，看似“字符很多”但无法检索；分析模式下这类页面仍会触发 OCR。只下载模式不会因此执行大规模 OCR，以免显著拖慢下载。

自动 OCR 完成后会比较原生文本与 OCR 文本的质量。只有 OCR 结果明显更完整、更可读时才替换原生文本，避免 OCR 降低表格和数字的准确性；显式使用 `ocr="force"` 时仍按用户要求强制 OCR。

PyMuPDF单页失败时只对该页回退pypdf。`quality_report.json`中的`extraction_fallback_pages`记录成功回退页，`extraction_failed_pages`记录两种解析器均失败的页面。

强制 OCR 只适合：

- 扫描版 PDF。
- 图片型 PDF。
- PyMuPDF 抽取质量很差。
- 用户明确要求 OCR。

## 7. 向量化什么时候触发

当前版本默认不做 embedding 向量化。

默认检索路径是：

```text
SQLite FTS 关键词检索 + 中文/普通子串兜底检索
```

显式请求向量能力时，当前版本只生成`engine=manifest-only`的页面清单，不生成 embeddings，也不声称已经建立可检索的向量库。外部向量后端可以消费该清单；未来如内置 embedding，应作为补充召回，不替代页码可追溯的关键词检索。

## 8. 问答时如何读取

问答时不把整本 PDF 或全文 Markdown 交给大模型。

实际链路：

```text
用户问题
-> 生成关键词和同义词
-> SQLite FTS 检索
-> 必要时子串兜底
-> 读取命中页和相邻页
-> 组装 EvidencePacket
-> 大模型基于证据包回答
```

## 9. 本地缓存审计

`audit_local_pdf_cache_tool(scan_content=false)` 默认只检查文件 hash、逻辑文件名、索引引用和暂存遗留。设置 `scan_content=true` 后，还会对文件名可识别的年报和招股书执行正文结构校验。该工具始终只读，不自动删除；确认问题后再使用文档或公司清理工具。

正文审计会先核对PDF SHA-256、`pages.jsonl`和索引页数；三者一致时复用已解析页面，只有缓存缺失或不一致时才重新扫描PDF。结果中的`content_index_reused_count`和`content_pdf_scanned_count`分别显示两种路径的数量。

文件SHA计算使用最多4个工作线程，`hash_workers`返回本次实际使用数量；正文结构校验保持确定性的逐文档处理。

