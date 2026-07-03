# D1 开发计划 v1.0

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

文件版本：v1.0  
开发定稿时间：2026-07-03 15:44  
项目名：`ah-disclosure-kit`  
Python 包名：`ah_disclosure`  
MCP server 名：`ah-disclosure`  
Skill 名：`ah-disclosure`  
CLI 命令：`ah-disclosure`

## 1. 项目定位

`ah-disclosure-kit` 是面向 A 股和港股的非交易类公司数据与披露文件工作台。

核心目标：

- 查询 A/H 股公司资料和结构化财务数据。
- 查询并下载 A 股、港股原始披露 PDF。
- 查询并下载招股书、上市文件、募集说明书。
- 对 PDF 做本地解析和检索。
- 为大模型提供可追溯、低 token 的 EvidencePacket。

明确不做：

- 实时行情。
- K 线和分时。
- 盘口。
- 技术指标。
- 短线情绪。
- 交易建议。

## 2. 数据源设计

| 场景 | 首选来源 | 说明 |
|---|---|---|
| A 股结构化公司数据 | AKShare | 公司资料、财务报表、财务指标、分红、股东等 |
| 港股结构化公司数据 | AKShare | 公司资料、财务报表、指标、分红等 |
| A 股原始公告 PDF | CNINFO | 年报、中报、季报、普通公告 |
| 港股原始公告 PDF | HKEXnews | 年报、中报、通函、业绩公告 |
| A 股 IPO / 招股书索引 | AKShare / 东方财富 | IPO 阶段信息、保荐机构等 |
| A 股历史招股书 / 募集说明书 | CNINFO | 已上市公司历史文件 |
| 港股招股书 / 上市文件 | HKEXnews | 需要港股代码或 HKEX stockId |

## 3. PDF 默认处理策略

只下载 PDF 时，不解析。

用户要求分析、读取、搜索、摘要或证据时，才执行 ingest。

默认 ingest 只生成：

- `meta.json`
- `pages.jsonl`
- `quality_report.json`
- SQLite FTS

默认不生成：

- `document.md`
- `full_text.txt`
- 向量索引
- 全量 OCR

## 4. 本地问答链路

```text
用户问题
-> 判断市场、公司、文件类型和任务类型
-> 使用结构化数据或披露文件路径
-> 如需 PDF 证据，先确认本地是否已有解析结果
-> SQLite FTS 检索关键词和同义词
-> 中文/普通子串兜底
-> 读取相关页和相邻页
-> 组装 EvidencePacket
-> 大模型只基于证据包回答
```

## 5. 命名规则

PDF、解析目录和 `document_id` 尽量使用稳定命名：

```text
MARKET_SYMBOL_YEAR_DOCUMENTTYPE_LANGUAGE_SHORTNAME
```

示例：

```text
A_600519_2024_annual_report_ZH_贵州茅台.pdf
H_00700_2024_annual_report_EN_TENCENT.pdf
H_03690_2026_q1_results_announcement_EN_MEITUAN-W.pdf
```

## 6. 数据目录

默认数据根目录：

```text
data/ah_disclosure
```

建议正式使用时通过环境变量固定：

```text
AH_DISCLOSURE_DATA_DIR
```

目录结构：

```text
raw/       原始 PDF
parsed/    PDF 解析产物
index/     SQLite 检索库
cache/     接口缓存
logs/      日志
```

## 7. 清理规则

不要手动删除单个 PDF 或解析目录后忽略 SQLite。

应使用：

- `cleanup_document_tool`
- `cleanup_company_tool`
- `reconcile_local_index_tool`

这样可以保证 `raw/`、`parsed/` 和 SQLite FTS 一致。

## 8. 已知边界

- 不支持完整结构化的“全年港股新增 IPO 公司列表”。
- 港股招股书查询以公司代码为范围，不做全市场慢扫描。
- 港股结构化数据的部分接口仍需要继续增强缓存、重试和字段标准化。
- OCR 已作为本地能力保留，但默认不全量触发。
- 向量化 embedding 默认未启用。

## 9. v1.0 验收状态

已完成：

- Python 包和 CLI。
- MCP server。
- Skill。
- A/H 股结构化数据路径。
- CNINFO A 股披露文件路径。
- HKEXnews 港股披露文件路径。
- 招股书和发行文件路径。
- PDF 下载、解析、SQLite FTS。
- 中文检索子串兜底。
- 清理和索引一致性工具。
- 中文文档体系。

最后单元测试结果：

```text
44 passed
```

## 10. 后续建议

v1.1 可以考虑：

- 港股结构化数据缓存和重试进一步增强。
- 表格抽取质量评估。
- 可选本地 embedding 补充召回。
- Windows 一键安装脚本。
- Docker 分发环境。
- 更完整的真实数据回归测试集。

