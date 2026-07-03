# 更新日志

相关文档：[A0.文档索引](./docs/A0_DOC_INDEX.md) | [A1.安装使用](./docs/A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./docs/A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./docs/A3_WORKFLOW.md) | [A4.MCP函数](./docs/A4_MCP_TOOLS.md) | [B1.PDF Ingest](./docs/B1_PDF_INGEST.md) | [B2.公司数据](./docs/B2_COMPANY_DATA.md) | [B3.HKEX](./docs/B3_HKEX.md) | [B4.招股书](./docs/B4_PROSPECTUS.md) | [C1.测试计划](./docs/C1_TEST_PLAN.md) | [D1.开发计划](./docs/D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](./examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](./CHANGELOG.md)

## v1.0.0

定稿时间：2026-07-03 15:44

本版本是面向公开使用场景整理的第一版稳定版本。

主要内容：

- 确定项目名称为 `ah-disclosure-kit`。
- 确定 Skill 名称为 `ah-disclosure`。
- 确定 MCP server 名称为 `ah-disclosure`。
- 支持 A 股、港股非交易类公司数据查询。
- 支持 A 股 CNINFO 原始公告和年报 PDF 下载。
- 支持港股 HKEXnews 原始公告、年报、通函和业绩公告 PDF 下载。
- 支持 A 股和港股招股书、上市文件、募集说明书查询与下载。
- 支持 PDF 本地解析，生成 `meta.json`、`pages.jsonl`、`quality_report.json`。
- 支持 SQLite FTS 全文检索，并增加中文关键词子串兜底检索。
- 支持 EvidencePacket 工作流，避免把整本 PDF 或全文 Markdown 直接交给大模型。
- 明确默认下载 PDF 不自动解析，只有用户要求读取、分析、搜索时才执行 ingest。
- 明确默认不生成 `document.md` 和 `full_text.txt`。
- OCR 保持本地、按需、低文本质量触发，不默认全量 OCR。
- 向量化 embedding 不默认启用。
- 清理文档体系，全部 Markdown 正文改为中文，并按类别编号。

## v0.1.0

内部开发草稿版本。

主要内容：

- 初始化 Python 包、CLI、MCP server 和 Skill。
- 接入 AKShare、CNINFO、HKEXnews、东方财富 IPO 相关路径。
- 建立 PDF ingest、SQLite FTS、本地检索和测试骨架。

