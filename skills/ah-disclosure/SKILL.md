---
name: ah-disclosure
description: 用于 A/H 股非交易类公司信息、披露文件、招股书、年报、HKEXnews 文件、PDF 本地解析和本地证据检索。
---

# ah-disclosure Skill

相关文档：[A0.文档索引](../../docs/A0_DOC_INDEX.md) | [A1.安装使用](../../docs/A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](../../docs/A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](../../docs/A3_WORKFLOW.md) | [A4.MCP函数](../../docs/A4_MCP_TOOLS.md) | [B1.PDF Ingest](../../docs/B1_PDF_INGEST.md) | [B2.公司数据](../../docs/B2_COMPANY_DATA.md) | [B3.HKEX](../../docs/B3_HKEX.md) | [B4.招股书](../../docs/B4_PROSPECTUS.md) | [C1.测试计划](../../docs/C1_TEST_PLAN.md) | [D1.开发计划](../../docs/D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../../CHANGELOG.md)

## 1. 核心规则

1. 处理 A/H 股披露文件和公司数据时，优先使用 `ah-disclosure` MCP 工具，不优先使用 WebSearch。
2. 结构化公司数据优先使用 AKShare-backed 工具。
3. A 股原始公告、年报、中报、季报优先使用 CNINFO。
4. 港股原始公告、年报、通函、业绩公告优先使用 HKEXnews。
5. 招股书、上市文件、PHIP、募集说明书使用 Prospectus 相关工具。
6. 如果用户只要求下载 PDF，只下载 PDF，并返回本地 PDF 路径和来源 URL。
7. PDF 下载后，只有当用户要求读取、分析、搜索、摘要或准备后续证据检索时，才调用 `ingest_pdf_tool`。
8. 默认 PDF ingest 只生成核心机器可读产物：`meta.json`、`pages.jsonl`、`quality_report.json` 和 SQLite FTS。默认不生成 `full_text.txt` 或 `document.md`。
9. 只有当用户要求人工阅读导出、复核全文，或分析完成后确认需要便利文件时，才生成 `full_text.txt` 或 `document.md`。
10. OCR 是本地、按需、质量触发能力。默认 `ocr="auto"` 只处理低文本页；只有 PDF 是扫描件、图片型、抽取质量差，或用户明确要求 OCR 时，才使用 `ocr="force"` 和 `overwrite=true`。
11. 文档产物使用稳定命名：`MARKET_SYMBOL_YEAR_DOCUMENTTYPE_LANGUAGE_SHORTNAME`。英文文件使用 `EN`，中文文件使用 `ZH`；港股简称优先使用交易所英文简称，A 股简称优先使用中文简称。
12. 不要手工删除 raw/parsed PDF 产物后忽略 SQLite。清理时使用 `cleanup_document_tool`、`cleanup_company_tool` 或 `reconcile_local_index_tool`。
13. 默认不要把完整 `document.md` 或 `full_text.txt` 交给大模型。
14. 分析前应构建或请求 EvidencePacket，只分析相关页、表格和结构化数据。
15. 输出时尽量给出来源、URL、本地路径、页码和接口名。
16. 对会计政策、披露文件分析、年报解释类问题，不要只依赖单一关键词。必须使用多路径检索：用户原语种关键词、英文会计/业务同义词、固定会计章节、相邻页扩展，以及会计政策、MD&A、附注和表格之间的交叉验证。
17. 如果证据检索不完整，应明确说明，不要把弱推断当成已确认的披露事实。
18. 当前工具不提供完整结构化的全年港股 IPO / 新上市公司列表。遇到“2026 年至今港股新增 IPO 公司 list”这类问题，应先说明 `ah-disclosure` 不支持该本地能力；如再使用 WebSearch 或外部来源，必须明确它不是本地 `ah-disclosure` 结果。
19. 港股招股书 / 上市文件搜索以公司代码为范围。如果用户只给中文或英文公司名，没有港股代码或 hkex_stock_id，应先询问港股代码，不要进行慢速全市场扫描。

## 2. 证据检索策略

会计政策或披露解释问题，优先使用 `get_evidence_packet_tool`，并设置 `strategy="accounting_policy"`。

财务分析、FP&A、预算、预测、经营驱动、利润桥问题，优先使用 `strategy="financial_analysis"`。

如果问题类型不明确，使用 `strategy="auto"`，由工具根据问题选择检索策略。

### 2.1 accounting_policy 策略

1. 根据用户问题生成多组关键词，包括原语种关键词和英文会计/业务同义词。
2. 搜索固定章节，例如 `revenue recognition`、`expenses by nature`、`segment information`、`management discussion and analysis`、`significant accounting policies`、`critical accounting estimates`。
3. 扩展命中页的相邻页，因为定义和表格经常跨页。
4. 尽量用至少两类证据交叉验证，例如会计政策、MD&A、附注或表格。
5. 只返回有限证据，不默认把整本报告交给大模型。

### 2.2 financial_analysis 策略

1. 优先检索 MD&A、收入分部、收入类别、分部信息、收入成本、销售及营销费用、费用性质、经营利润/亏损和 KPI 驱动页。
2. 对管理层解释和财务报表金额进行交叉验证。
3. 除非用户问收入确认或列报政策，否则会计政策证据作为次要证据。

## 3. 建议工作流

```text
识别市场和任务
-> route_query_tool
-> 结构化数据 provider 或披露文件 provider
-> 必要时下载 PDF
-> 只有用户要求读取、分析、搜索或准备证据时才 ingest PDF
-> get_evidence_packet_tool
-> 只分析证据包
```

