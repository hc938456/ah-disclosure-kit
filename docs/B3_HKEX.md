# B3 HKEX

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明港股披露文件查询为什么需要 HKEX `stockId`，以及当前工具的边界。

## 1. 港股代码和 HKEX stockId

HKEXnews 的很多公告查询 URL 使用内部 `stockId`。

`stockId` 不是 5 位港股代码。

例如：

```text
港股代码：00700
HKEX stockId：需要通过 HKEX 查询或缓存解析
```

因此港股公告搜索通常需要：

```text
港股代码
-> resolve_hkex_stock_id_tool
-> 校验 Stock Code / Short Name
-> search_h_filings
-> download
```

## 2. 支持的港股披露文件

当前支持：

- 年报。
- 中报。
- 季度业绩公告。
- 业绩公告。
- 通函。
- 普通公告。
- 招股书。
- 上市文件。
- PHIP / 聆讯后资料集。

## 3. 不支持的能力

v1.0 不提供完整结构化的“某一年至今港股新增 IPO 公司列表”。

如果用户问：

```text
2026 年至今港股新增 IPO 公司 list
```

应先说明：

```text
ah-disclosure 当前工具不支持完整结构化的全年港股 IPO 新增列表。
```

如果用户允许，再使用外部网页或交易所页面人工整理，并明确这是外部来源，不是本地 ah-disclosure 结构化结果。

## 4. 招股书查询边界

港股招股书 / 上市文件查询是公司代码范围内的查询。

如果用户只给公司中文名或英文名，没有港股代码，应先询问港股代码，不要直接跑全市场扫描。

