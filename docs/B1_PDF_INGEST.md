# B1 PDF Ingest

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明 PDF 下载后如何被处理，以及哪些产物是默认生成、哪些是按需生成。

## 1. 默认原则

只下载 PDF 时，不解析。

只有用户要求读取、分析、搜索、摘要、提取证据或后续问答时，才执行 PDF ingest。

## 2. 基础 ingest 链路

```text
PDF
-> 计算 md5 / sha256
-> 生成 meta.json
-> PyMuPDF 按页抽文本
-> 生成 pages.jsonl
-> 生成 quality_report.json
-> 写入 SQLite document_pages 和 document_pages_fts
```

这些步骤都在本地 Python 中完成，不消耗大模型 token。

## 3. 默认生成的产物

每份被解析的 PDF 默认生成：

- `meta.json`：文档元信息、来源、页数、hash、PDF 路径。
- `pages.jsonl`：按页抽取的文本，每行对应一页。
- `quality_report.json`：文本层质量、页字符数、低文本页判断。
- SQLite FTS：统一全文检索索引。

## 4. 默认不生成的产物

默认不生成：

- `full_text.txt`
- `document.md`
- 向量索引
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

默认 `ocr="auto"` 时，只在低文本页或疑似扫描页触发局部 OCR。

强制 OCR 只适合：

- 扫描版 PDF。
- 图片型 PDF。
- PyMuPDF 抽取质量很差。
- 用户明确要求 OCR。

## 7. 向量化什么时候触发

v1.0 默认不做 embedding 向量化。

默认检索路径是：

```text
SQLite FTS 关键词检索 + 中文/普通子串兜底检索
```

未来如果启用 embedding，应作为补充召回，不替代页码可追溯的关键词检索。

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

