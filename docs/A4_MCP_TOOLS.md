# A4 MCP 函数清单

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明 `ah-disclosure` MCP server 暴露的主要函数，以及每类函数的用途。

## 1. 基础信息

- `server_info`：返回服务版本、数据目录、运行环境信息。
- `list_capabilities`：列出当前工具支持的能力边界。
- `route_query_tool`：根据用户问题判断应该走结构化数据、披露文件、本地文档还是混合路径。

## 2. 公司识别

- `resolve_company_tool`：统一识别 A 股、港股或 A+H 公司。
- `resolve_a_symbol_tool`：识别 A 股代码和公司名称。
- `resolve_h_symbol_tool`：识别港股代码和公司名称。
- `resolve_hkex_stock_id_tool`：解析港股 HKEXnews 内部 `stockId`，并缓存结果。

## 3. 披露文件查询

- `search_filings`：按市场、公司、类别、关键词查询披露文件。
- `search_annual_report`：查询年报。
- `search_interim_report`：查询半年报 / 中报。
- `search_quarterly_report`：查询季报或季度业绩公告。

## 4. 披露文件下载与解析

- `download_and_ingest_filing`：下载指定披露文件，可通过 `ingest=true` 决定是否解析。
- `download_and_ingest_report`：查询并下载 A/H 股年报，可通过 `ingest` 控制是否生成解析产物。
- `download_report_tool`：只下载年报 PDF，不生成 `pages.jsonl`、`document.md`、`full_text.txt` 或 SQLite 索引。
- `ingest_pdf_tool`：对已有 PDF 执行本地解析，生成核心机器可读产物和 SQLite FTS。

## 5. 招股书和发行文件

- `search_prospectus_tool`：查询招股书、上市文件、聆讯后资料集、PHIP 等。
- `search_offering_documents`：查询募集说明书、可转债、配股、增发等发行文件。
- `download_and_ingest_prospectus_tool`：下载招股书或发行文件，可选择是否解析。
- `download_prospectus_tool`：只下载招股书或发行文件 PDF，不生成解析产物。

## 6. 结构化公司数据

- `get_company_profile_tool`：公司资料。
- `get_business_info_tool`：主营业务、主营构成或业务分部信息。
- `get_financial_statements_tool`：资产负债表、利润表、现金流量表。
- `get_financial_indicators_tool`：财务指标。
- `get_dividends_tool`：分红派息。
- `get_shareholders_tool`：股东、股本、持股相关数据。
- `get_capital_actions_tool`：股本变动、回购、融资等资本动作。
- `get_governance_esg_tool`：治理、ESG 或相关扩展数据。

## 7. 本地文档检索

- `list_local_documents_tool`：列出本地已解析文档。
- `search_local_document_text_tool`：在 SQLite FTS / 子串兜底中检索本地文档页。
- `get_document_pages_tool`：读取指定文档的指定页文本。
- `get_document_meta_tool`：读取指定文档的元数据。
- `get_evidence_packet_tool`：根据问题返回裁剪后的证据包，供大模型分析。

## 8. 清理和一致性维护

- `cleanup_document_tool`：清理单个文档的 PDF、解析产物和 SQLite 索引。
- `cleanup_company_tool`：清理某个公司的相关本地数据。
- `reconcile_local_index_tool`：对齐文件系统和 SQLite 索引，修复手动删除造成的不一致。

## 9. 公司画像和交叉验证

- `build_company_dossier_tool`：构建公司画像，综合结构化数据和披露文件。
- `compare_structured_data_with_report_tool`：把 AKShare 结构化数据与年报原文表格或披露内容做交叉验证。

## 10. 默认 PDF 产物

执行 ingest 时，默认只生成：

- `meta.json`
- `pages.jsonl`
- `quality_report.json`
- SQLite FTS

默认不生成：

- `document.md`
- `full_text.txt`
- 向量索引

