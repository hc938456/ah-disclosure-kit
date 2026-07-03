# C1 测试计划

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明 `ah-disclosure-kit` v1.0 的测试方式。

## 1. 单元测试

在 kit 根目录执行：

```powershell
python -m pytest -q
```

当前 v1.0 定稿前最后一次测试结果：

```text
44 passed
```

## 2. 基础命令测试

查看服务信息：

```powershell
python -m ah_disclosure.cli server-info
```

解析港股代码：

```powershell
python -m ah_disclosure.cli resolve --market H --symbol 00700
```

查询 A 股公司资料：

```powershell
ah-disclosure a profile --symbol 600519
```

## 3. 真实全流程测试

建议至少测试一只 A 股和一只港股。

A 股测试：

```powershell
ah-disclosure a report --symbol 600519 --year 2024 --download --ingest
ah-disclosure local search --query "收入确认"
```

港股测试：

```powershell
ah-disclosure h report --symbol 00700 --year 2024 --download --ingest
ah-disclosure local search --query "revenue recognition"
```

## 4. 重点验收项

- 只下载 PDF 时，不生成 `pages.jsonl`、`document.md`、`full_text.txt`。
- 下载并分析时，生成 `meta.json`、`pages.jsonl`、`quality_report.json` 和 SQLite FTS。
- 中文关键词检索在 SQLite FTS 无命中时，可以走子串兜底。
- 清理文档或公司数据时，文件系统和 SQLite 索引同步更新。
- Skill 中的规则与 docs 文档一致。
- 包版本、`VERSION` 文件和更新日志一致。

## 5. 网络测试说明

真实数据源测试依赖 CNINFO、HKEXnews、AKShare、东方财富等外部来源。网络不可用、接口限流或上游字段变化时，测试可能失败。

失败时应区分：

- 本地代码 bug。
- 上游网站不可访问。
- 数据源接口字段变化。
- 公司代码或年份无对应文件。

