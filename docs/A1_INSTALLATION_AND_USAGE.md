# A1 安装与使用

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明 `ah-disclosure-kit` 的本地安装、MCP 注册和常用命令。

## 1. 环境要求

建议环境：

- Windows 10/11、macOS 或 Linux。
- Python 3.11 或更高版本。
- `python` 命令在 PowerShell / Terminal 中可用。
- 已安装 Claude Code / Codex。
- 可访问 A 股、港股披露文件来源网站。

注意：本 kit 不会自动安装 Python 解释器。如果当前机器没有 Python，需要先安装 Python，再执行后续 pip 安装命令。

## 2. 安装依赖

### 2.1 一键安装 / 检查

建议在 kit 根目录执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\INSTALL_AND_CHECK.ps1
```

脚本负责：

- 检查已有 Python 是否为 3.11+。
- 安装/更新 Python 包依赖，默认安装 `.[pdf]`。
- 创建默认数据目录。
- 复制 Skill 到 `.codex\skills\ah-disclosure`。
- 如果当前环境存在 `claude` 命令，则注册 MCP server。
- 验证 `ah-disclosure-kit` 版本和 CLI 基础命令。

脚本不负责：

- 不安装 Python 解释器。
- 不安装 Tesseract OCR。
- 不创建项目 `.venv`。

常用参数：

```powershell
.\scripts\INSTALL_AND_CHECK.ps1 -SkipMcpRegistration
.\scripts\INSTALL_AND_CHECK.ps1 -CheckTesseract
.\scripts\INSTALL_AND_CHECK.ps1 -Extras "pdf,table,ocr"
```

### 2.2 手工安装

在 kit 根目录执行：

```powershell
cd C:\path\to\ah-disclosure-kit
python -m pip install --upgrade pip
python -m pip install -e ".[pdf]"
```

如果需要开发、OCR、表格抽取和向量相关可选能力：

```powershell
python -m pip install -e ".[pdf,table,ocr,vector,dev]"
```

当前设计建议优先使用全局 Python，避免每个工具目录都复制一份 `.venv`，减小安装目录体积。

`python -m pip install -e ".[pdf]"` 会安装 Python 包依赖，例如 AKShare、pandas、MCP、PyMuPDF；但不会安装系统级工具。可选 OCR 功能需要另行安装 Tesseract OCR。

## 3. 数据目录

默认数据目录是当前运行目录下的：

```text
data/ah_disclosure
```

建议显式设置：

```powershell
$env:AH_DISCLOSURE_DATA_DIR="C:\path\to\data\ah_disclosure"
```

数据目录用于保存：

- 原始 PDF：`raw/`
- PDF 解析结果：`parsed/`
- SQLite 检索库：`index/ah_disclosure.sqlite`
- 缓存：`cache/`

## 4. 注册 MCP

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

注册完成后，在 Claude Code 中运行：

```text
/mcp
```

确认 `ah-disclosure` 在线。

## 5. 安装 Skill

复制：

```text
skills/ah-disclosure
```

到：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure
```

示例路径：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure
```

## 6. 常用 CLI 命令

查看服务信息：

```powershell
ah-disclosure server-info
```

查询 A 股公司资料：

```powershell
ah-disclosure a profile --symbol 600519
```

查询 A 股财务报表：

```powershell
ah-disclosure a financials --symbol 600519 --statement all
```

下载 A 股年报但不解析：

```powershell
ah-disclosure a report --symbol 600519 --year 2024 --download
```

下载并解析 A 股年报：

```powershell
ah-disclosure a report --symbol 600519 --year 2024 --download --ingest
```

查询港股公司资料：

```powershell
ah-disclosure h profile --symbol 00700
```

下载港股年报但不解析：

```powershell
ah-disclosure h report --symbol 00700 --hkex-stock-id <hkex_stock_id> --download
```

下载并解析港股年报：

```powershell
ah-disclosure h report --symbol 00700 --hkex-stock-id <hkex_stock_id> --download --ingest
```

检索本地已解析 PDF：

```powershell
ah-disclosure local search --query "revenue recognition"
```

## 7. 常用提问方式

只下载 PDF：

```text
使用 ah-disclosure 下载美团 2025 年年报，只下载 PDF，不要解析。
```

下载并分析：

```text
使用 ah-disclosure 下载美团 2025 年年报，并分析收入、净利润和分部利润。
```

检索已下载资料：

```text
使用 ah-disclosure 在本地已解析的腾讯 2024 年报中，查找收入类别和收入确认政策。
```

## 8. 默认行为提醒

只说“下载 PDF”时，工具不会默认抽文本、不会写 SQLite、不会生成 `pages.jsonl`。

只有当用户要求分析、阅读、检索、摘要或准备证据时，才会执行 ingest。

