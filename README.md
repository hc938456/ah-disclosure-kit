# ah-disclosure-kit

相关文档：[A0.文档索引](./docs/A0_DOC_INDEX.md) | [A1.安装使用](./docs/A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./docs/A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./docs/A3_WORKFLOW.md) | [A4.MCP函数](./docs/A4_MCP_TOOLS.md) | [B1.PDF Ingest](./docs/B1_PDF_INGEST.md) | [B2.公司数据](./docs/B2_COMPANY_DATA.md) | [B3.HKEX](./docs/B3_HKEX.md) | [B4.招股书](./docs/B4_PROSPECTUS.md) | [C1.测试计划](./docs/C1_TEST_PLAN.md) | [D1.开发计划](./docs/D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](./examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](./CHANGELOG.md)

`ah-disclosure-kit` 是一个面向 A 股和港股披露文件的本地 Python + MCP 工具包。它用于查询非交易类公司信息、下载原始公告 PDF、解析 PDF、建立本地检索索引，并为 AI 辅助财务分析提供可追溯的证据包。

**A/H-share disclosure documents, HKEXnews/CNINFO PDF ingest, local search, and MCP toolkit for AI-assisted financial analysis.**

本工具不是行情系统，也不是交易决策系统。它不覆盖实时行情、K 线、盘口、技术指标、短线情绪或择时信号。

英文关键词：`A-share`、`H-share`、`HKEXnews`、`CNINFO`、`prospectus`、`annual report`、`PDF ingest`、`local search`、`MCP server`、`EvidencePacket`

## 1. 一句话介绍

把 A 股、港股、招股书等分散披露文件，变成一个适合 `Claude Code`、`Codex`、`Kimi Code` 等工具使用的本地证据工作台。

## 2. 它解决什么问题

- 公开网站能下载文件，但很难把文件沉淀成可检索、可复用、可追溯的本地资产。
- 财务分析常见问题如收入确认、股权激励、IPO 前融资、主要投资方，往往需要在多份 PDF 之间来回跳转。
- 直接把整本年报或招股书交给大模型，token 成本高，也不利于稳定引用页码和证据来源。

## 3. 它适合什么场景

- A/H 股年报、公告、通函、招股书、募集说明书下载与整理。
- 面向财务分析、BP、投研、战略分析的本地披露资料沉淀。
- 为 AI 分析流程提供 `EvidencePacket`，只让模型读取相关页而不是整本 PDF。

## 4. 为什么不是“又一个下载器”

- 它不只下载 PDF，还会把文件组织成本地数据资产。
- 它不只抽文本，还会生成 `meta.json`、`pages.jsonl`、`quality_report.json` 和本地检索索引。
- 它不只做搜索，还会把问题路由到结构化数据、披露文件和证据页级别。
- 它不只服务人工阅读，也服务 `MCP` / AI 工作流。

## 5. v1.0 定位

```text
A/H 股公司披露文件与非交易类公司信息的本地数据工作台
```

核心能力：

- A 股结构化公司数据：通过 AKShare 获取。
- 港股结构化公司数据：通过 AKShare 获取。
- A 股原始公告和年报 PDF：通过 CNINFO 获取。
- 港股原始公告、年报、通函和业绩公告：通过 HKEXnews 获取。
- 招股书、上市文件和募集说明书：通过 CNINFO、HKEXnews、东方财富/AKShare 路径获取。
- PDF 本地解析：PyMuPDF 抽页文本，生成 `meta.json`、`pages.jsonl`、`quality_report.json`。
- 本地检索：SQLite FTS + 子串兜底检索。
- 大模型分析：只读取 EvidencePacket 中的相关页、表格或结构化数据，不默认读取整本文档。

## 6. 为什么已经能在线下载文件，还需要这个 kit

公开网站能解决“找到并下载文件”，但通常解决不了下面这些问题：

- 文件来源分散：A 股、港股、招股书、募集说明书往往分散在不同入口。
- 下载后不可复用：文件在浏览器里看过一次，之后很难沉淀成本地可检索资产。
- 大模型成本高：直接把整本年报或招股书喂给模型，token 成本高，也不利于追溯。
- 证据链不稳定：很多分析只能给总结，不能稳定回到“哪一页、哪一段、哪张表”。
- 跨文档复盘困难：收入确认、股权激励、IPO 前融资、机构投资者等问题，经常需要在不同文件之间跳转。

这个 kit 的价值不是“替代下载网站”，而是把“下载 -> 解析 -> 检索 -> 证据包 -> 复用”串成一个适合 AI 辅助分析和财务研究的本地工作台。

## 7. 适合谁

- 需要看 A/H 股披露文件的财务分析、BP、投研或战略同学。
- 需要让 AI 基于证据页而不是整本 PDF 回答问题的使用者。
- 需要沉淀本地披露文件资产，反复复用同一批年报、公告、招股书的人。

## 8. 支持的运行环境

当前版本的支持情况建议按下面理解：

| 环境 | 支持状态 | 说明 |
|------|----------|------|
| Python 3.11+ | 已支持 | `CLI`、`MCP server`、本地解析能力都依赖 Python。 |
| Windows 10/11 PowerShell | 已支持 | 当前文档、安装脚本和默认命令主要按 Windows 编写。 |
| macOS / Linux | 基本可用 | Python 包本身可安装，但安装说明和脚本还没有专门适配到同等完整度。 |
| Claude Code | 已支持 | 当前 README、示例命令和 MCP 注册流程直接面向 Claude Code。 |
| Codex / Codex for VS Code | 已支持 | 当前目录内已提供 `.codex` Skill 使用方式，文档中也已覆盖。 |
| Kimi Code CLI | 可接入 | 本项目的 MCP server 使用 `stdio` 方式启动；支持 `MCP` 的客户端可手工接入，但当前仓库未提供专门的一键配置脚本。 |
| 其他 MCP 客户端 | 可接入 | 只要客户端支持本地 `stdio MCP server`，通常都可以手工配置。 |

其中：

- `Claude Code` / `Codex`：属于当前文档直接覆盖的主要目标环境。
- `Kimi Code CLI`：属于协议层可接入，但当前仓库还没有专门写 Kimi 配置说明。

## 9. 快速开始

```powershell
python -m pip install -e ".[pdf]"
python -m ah_disclosure.cli --version
python -m ah_disclosure.cli server-info
```

如果你要把它接到支持 MCP 的客户端，再使用同一个启动命令：

```text
python -m ah_disclosure.mcp_server
```

## 10. 使用场景示例

- 下载腾讯、阿里、美团等公司的年报、公告、通函并建立本地索引。
- 整理收入确认、成本确认、坏账、递延收入等重要会计政策。
- 分析股权激励计划、股份支付费用和对利润的影响。
- 从招股书中提取 IPO 前融资历史、主要投资方、优先股和特殊权利安排。
- 让 AI 基于证据页而不是整本 PDF 回答问题。

## 11. 支持的客户端

当前更适合这样理解：

- `Claude Code`：开箱即用，文档和命令已覆盖。
- `Codex / Codex for VS Code`：已支持，适合通过 `.codex` Skill 和本地 MCP 一起使用。
- `Kimi Code`：协议兼容，可通过 MCP 手工接入。
- 其他支持 `stdio MCP` 的客户端：通常可手工接入。

## 12. Roadmap

- 增加面向 `Kimi Code` 的专门接入说明。
- 补充 `macOS / Linux` 一键安装脚本。
- 增加更多招股书、融资历史、股权激励相关示例问题模板。
- 继续完善 PDF 表格抽取、OCR 和向量检索的可选能力。

## 13. FAQ

### 13.1 这个 kit 会不会替代公开披露网站？

不会。它依赖公开披露网站作为数据来源，但重点是把下载、解析、检索和证据复用串成一个本地工作流。

### 13.2 我只想下载 PDF，不想做解析，可以吗？

可以。只要明确说“只下载 PDF”，工具默认不会继续做 ingest。

### 13.3 我是不是必须用 Claude Code？

不是。只要你的客户端支持本地 `stdio MCP server`，通常都可以接入；只是当前文档对 `Claude Code / Codex` 覆盖最完整。

## 14. 默认行为

只下载 PDF 时，工具只保存 PDF，并返回本地路径和来源 URL。

只有当用户要求“读取、分析、搜索、摘要、提取证据”时，才会继续执行 PDF ingest：

```text
PDF -> PyMuPDF 抽页文本 -> meta.json / pages.jsonl / quality_report.json -> SQLite FTS
```

默认不生成：

- `full_text.txt`
- `document.md`
- 向量索引

这些属于按需增强产物。

## 15. 安装

### 15.1 安装前提

开始安装前，建议先确认：

- 已安装 Python 3.11 或更高版本。
- `python` 命令在 PowerShell / Terminal 中可用。
- 本工具默认使用已有的全局 Python 或用户 Python 环境，不在 kit 目录中创建 `.venv`。
- `python -m pip install ...` 会安装 Python 包依赖，例如 AKShare、pandas、MCP、PyMuPDF。
- 如果机器没有 Python，本 kit 不会自动安装 Python 解释器。
- 可选 OCR 功能需要另行安装系统级 Tesseract OCR；仅安装 Python 包不等于安装 Tesseract。

### 15.2 一键安装 / 检查

Windows PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\INSTALL_AND_CHECK.ps1
```

脚本会做：

- 检查已有 Python 是否为 3.11+。
- 安装/更新 Python 包依赖，默认安装 `.[pdf]`。
- 创建默认数据目录。
- 复制 `ah-disclosure` Skill 到 `.codex\skills`。
- 如果当前环境存在 `claude` 命令，则注册 MCP server。
- 验证 `ah-disclosure-kit` 版本和 CLI 基础命令。

脚本不会做：

- 不安装 Python 解释器。
- 不安装 Tesseract OCR。
- 不创建项目 `.venv`。

如果只想检查安装，不注册 MCP：

```powershell
.\scripts\INSTALL_AND_CHECK.ps1 -SkipMcpRegistration
```

如果要检查 Tesseract 是否存在：

```powershell
.\scripts\INSTALL_AND_CHECK.ps1 -CheckTesseract
```

### 15.3 手工安装

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[pdf]"
```

完整可选依赖：

```powershell
python -m pip install -e ".[pdf,table,ocr,vector,dev]"
```

## 16. MCP 注册

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

注册后在 Claude Code 中执行：

```text
/mcp
```

确认 `ah-disclosure` 已连接。

如果你使用的是其他支持 MCP 的客户端，也可以复用同一个启动命令：

```text
python -m ah_disclosure.mcp_server
```

只要客户端支持本地 `stdio` MCP server，即可手工完成接入。

## 17. Skill 安装

把本目录下的：

```text
skills/ah-disclosure
```

复制到：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure
```

示例路径：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure
```

## 18. 数据目录

默认数据目录：

```text
./data/ah_disclosure
```

也可以通过环境变量指定：

```powershell
$env:AH_DISCLOSURE_DATA_DIR="C:\path\to\data\ah_disclosure"
```

## 19. 文档入口

建议阅读顺序：

1. `docs/A0_DOC_INDEX.md`
2. `docs/A1_INSTALLATION_AND_USAGE.md`
3. `docs/A3_WORKFLOW.md`
4. `docs/A4_MCP_TOOLS.md`
5. `docs/B1_PDF_INGEST.md`
6. `docs/C1_TEST_PLAN.md`

## 20. 致谢与来源

本项目基于开源 Python 生态构建，核心依赖包括：

- `AKShare`：A/H 股结构化公司数据与部分公开市场数据接口。
- `pandas`：结构化数据处理。
- `requests` / `httpx` / `beautifulsoup4` / `lxml`：公开网页与文件请求、解析。
- `mcp`：MCP server 能力封装。
- `PyMuPDF` / `pypdf` / `pdfplumber` / `camelot-py` / `pytesseract`：PDF 文本、表格与 OCR 处理。
- `ChromaDB` / `sentence-transformers`：可选向量索引能力。

本项目也使用了公开披露渠道作为数据来源，包括：

- `CNINFO`：A 股公告、年报、募集说明书等公开披露文件。
- `HKEXnews`：港股公告、年报、通函、上市文件等公开披露文件。
- `东方财富 / AKShare 可达公开路径`：部分招股书与发行文件检索入口。

项目整体的工作流设计、目录组织、MCP 工具封装、证据包约束、本地检索链路与 A/H 披露场景整合，属于在开源生态与公开数据源基础上的工程实现。当前仓库未声明基于某一个 GitHub 开源项目直接复制或二次封装；如后续明确参考具体项目，将在 README 或单独文档中补充致谢。

## 21. 开源发布建议

如果公开发布到 GitHub，建议仓库标题和简介尽量包含可搜索词，例如：

- 仓库标题：`ah-disclosure-kit`
- GitHub Description：`A/H-share disclosure documents, HKEXnews/CNINFO PDF ingest, local search, and MCP toolkit for AI-assisted financial analysis.`
- Topics 建议：`mcp`、`python`、`finance`、`hkex`、`cninfo`、`pdf`、`prospectus`、`annual-report`、`a-share`、`h-share`

## 22. 版本信息

当前版本：v1.0.0  
开发定稿时间：2026-07-03 15:44

