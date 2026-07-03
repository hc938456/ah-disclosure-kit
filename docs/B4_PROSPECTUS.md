# B4 招股书与上市文件

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明招股书、上市文件、聆讯资料和募集说明书的查询路径。

## 1. A 股 IPO 阶段文件

A 股 IPO 审核、排队、辅导和招股书索引，优先通过 AKShare / 东方财富相关接口获取。

适用问题：

```text
某家公司 IPO 阶段是什么？
IPO 招股书在哪里？
保荐机构、会计师、律师是谁？
```

## 2. A 股已上市公司历史招股书

已上市公司的历史招股书、上市公告书、募集说明书，优先通过 CNINFO 查询。

常见关键词：

- 招股说明书。
- 上市公告书。
- 募集说明书。
- 可转换公司债券募集说明书。
- 配股说明书。
- 非公开发行。
- 向特定对象发行。

## 3. 港股招股书和上市文件

港股招股书、上市文件、PHIP、聆讯后资料集，优先通过 HKEXnews 查询。

注意：

- 查询通常需要港股代码或 HKEX `stockId`。
- 不建议只凭公司名称跑全市场扫描。
- 结果应返回来源 URL、本地 PDF 路径、发布日期和文件标题。

## 4. 下载和解析

只要求下载时：

```text
download_prospectus_tool
-> 保存 PDF
-> 返回路径和 URL
```

要求分析时：

```text
download_and_ingest_prospectus_tool
-> 下载 PDF
-> ingest
-> SQLite FTS
-> EvidencePacket
-> 大模型分析
```

