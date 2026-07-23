# A1 安装与使用

文档导航：[A0 文档索引](./A0_DOC_INDEX.md)

本文说明 `ah-disclosure-kit` 的本地安装、MCP 注册和常用命令。

## 1. 环境要求

建议环境：

- Windows 10/11、macOS 或 Linux。
- Python 3.11 或更高版本。
- `python` 命令在 PowerShell / Terminal 中可用。
- 已安装 Claude Code / Codex。
- 可访问 A 股、港股披露文件来源网站。

仓库CI覆盖Windows/Linux与Python 3.11、3.12、3.13、3.14。macOS可安装使用，但当前不在自动化矩阵内。

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
- 安装/更新 Python 包依赖，默认安装 `.[pdf,company-data,mcp]`。
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
.\scripts\INSTALL_AND_CHECK.ps1 -Extras "pdf,company-data,mcp,table,ocr"
```

### 2.2 手工安装

在 kit 根目录执行：

```powershell
cd C:\path\to\ah-disclosure-kit
python -m pip install --upgrade pip
python -m pip install -e ".[pdf,company-data,mcp]"
```

如果需要开发、OCR、表格抽取和向量相关可选能力：

```powershell
python -m pip install -e ".[all]"
```

当前设计建议优先使用全局 Python，避免每个工具目录都复制一份 `.venv`，减小安装目录体积。

默认一键安装及上述常规手工安装包含PDF解析、AKShare公司数据和MCP运行依赖。仅需来源查询和下载时，可使用`python -m pip install -e .`安装轻量核心；其他能力可按需选择`pdf`、`company-data`、`mcp`、`layout`、`table`、`ocr`、`vector`和`dev`。`layout`用于按版面生成增强Markdown，默认ingest不需要。Python的`ocr`依赖不会安装系统级Tesseract OCR，使用OCR仍需另行安装Tesseract。

## 3. 数据目录

源码checkout或editable安装时，默认数据目录固定按项目工作区解析，不随当前运行目录变化：

```text
data/ah_disclosure
```

当仓库位于某个工作区的`tools/ah-disclosure-kit`时，实际默认位置为该工作区的`data/ah_disclosure`；其他源码布局默认使用仓库内的`data/ah_disclosure`。

wheel安装时默认使用操作系统用户数据目录：Windows为`%LOCALAPPDATA%\ah-disclosure\data`，macOS为`~/Library/Application Support/ah-disclosure/data`，Linux为`${XDG_DATA_HOME:-~/.local/share}/ah-disclosure/data`。

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

将整个规范 Skill 目录复制：

```text
skills/ah-disclosure
```

到用户级目录：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure
```

示例路径：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure
```

也可以复制到项目根目录的 `.agents\skills\ah-disclosure`，仅对该项目生效。不要只复制 `SKILL.md`；`agents/` 和 `references/` 也是 Skill 的组成部分。

也可以让安装脚本直接同步到项目级 Skill 根目录：

```powershell
.\scripts\INSTALL_AND_CHECK.ps1 -SkillInstallRoot "C:\目标项目\.agents\skills"
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
ah-disclosure h report --symbol 00700 --download
```

下载并解析港股年报：

```powershell
ah-disclosure h report --symbol 00700 --download --ingest
```

港股`hkex_stock_id`通常由工具自动解析并永久缓存。只有需要指定候选映射或排查身份解析时，才传入`--hkex-stock-id`或使用`resolve --refresh-identity`重新核对。

检索本地已解析 PDF：

```powershell
ah-disclosure local search --query "revenue recognition"
```

批量下载、校验并解析年报或招股书：

```powershell
ah-disclosure batch prepare `
  --input examples\batch.example.csv `
  --output batch_result.json `
  --summary-only
```

输入支持UTF-8 CSV、JSON和JSONL。必填字段为`market`和`symbol`，可选字段为`company_name`、`document_type`、`report_year`、`language`和`hkex_stock_id`。`document_type`支持`annual_report`和`prospectus`。

常用批量参数：

- `--max-workers 2`：默认并发2，硬上限4。
- `--resume`：从输出文件对应的checkpoint继续。
- `--offline`：只使用本地PDF、来源缓存和索引。
- `--refresh-source`：重新核对官方文件来源。
- `--refresh-identity`：重新核对HKEX `stockId`永久映射。
- `--stop-on-error`：首个失败后停止，并自动按单线程执行。
- `--ocr auto|off|force`：控制批量ingest的OCR策略，默认`auto`。
- `--quiet-progress`：不在stderr输出逐项进度。
- `--summary-only`：完整结果仍写入`--output`文件，终端只显示总体统计和每项状态。

批量命令不会提取EvidencePacket，不执行分析、估值或写作；后续需要分析时再使用本地证据检索流程。完全重复的输入只执行一次，其余行复用结果；输出中的`effective_workers`是实际线程数而非请求上限。

年报输入省略`report_year`时，结果会在该字段回填实际选中的最新报告年度。

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

