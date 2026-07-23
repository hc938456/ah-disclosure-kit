# A0 Claude Code 命令示例

文档导航：[A0 文档索引](../docs/A0_DOC_INDEX.md)

## 1. 注册 MCP

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

## 2. 常用提示词

只下载 PDF：

```text
使用 ah-disclosure 下载腾讯 2024 年年报，只下载 PDF，不要解析。
```

下载并分析：

```text
使用 ah-disclosure 下载美团 2025 年年报和 2026 Q1 业绩公告，并分析收入、净利润、分部表现和管理层解释。
```

整理重要会计政策：

```text
使用 ah-disclosure 下载并分析腾讯 2024 年年报，整理收入确认、成本确认、金融资产减值、研发费用资本化、所得税和合并报表范围等重要会计政策，并按“政策内容 + 对财务分析的影响”输出。
```

分析股权激励：

```text
使用 ah-disclosure 下载并分析美团最近一期年报，整理公司的股权激励情况，包括股权激励计划类型、授予对象、授予数量、行权价格、归属安排、当期股份支付费用及其对利润的影响。
```

分析招股书中的 IPO 前融资：

```text
使用 ah-disclosure 下载并分析公司的招股书，整理 IPO 前融资历史，包括各轮融资时间、投资方、融资金额、主要入股价格、优先股或特殊权利安排，以及上市前主要机构投资者情况。
```

分析招股书中的主要投资方：

```text
使用 ah-disclosure 下载并分析公司的招股书，整理上市前主要股东和机构投资者，说明持股比例、进入时间、是否为核心战略投资者，以及这些投资方对公司治理和后续退出节奏的潜在影响。
```

查询结构化数据：

```text
使用 ah-disclosure 直接查结构化数据，不用查 PDF。告诉我腾讯 2025 年收入和净利润。
```

检索本地 PDF：

```text
使用 ah-disclosure 在本地已解析的美团年报中查找 revenue recognition、customer incentives 和 selling and marketing expenses 相关页。
```

要求证据：

```text
使用 ah-disclosure 返回 EvidencePacket，并基于证据页回答。请列出来源文件、页码和本地 PDF 路径。
```

批量准备但暂不分析：

```text
使用 ah-disclosure batch prepare，按我提供的公司名单批量完成代码确认、来源定位、下载、校验和ingest；不要提取EvidencePacket，不要分析、估值或写作。完成后汇总每条任务状态和各阶段耗时。
```

