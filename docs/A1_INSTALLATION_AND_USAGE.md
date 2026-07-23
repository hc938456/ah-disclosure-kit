# A1 Installation and Usage

Documentation navigation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This guide explains how to install `ah-disclosure-kit` locally, register its MCP server, and use its common commands.

## 1. Requirements

Recommended environment:

- Windows 10/11, macOS, or Linux.
- Python 3.11 or later.
- The `python` command is available in PowerShell or a terminal.
- Claude Code or Codex is installed.
- The machine can access websites that publish A-share and H-share disclosure documents.

The repository CI covers Windows and Linux with Python 3.11, 3.12, 3.13, and 3.14. macOS installations are supported, but macOS is not currently included in the automated test matrix.

Note: This Kit does not install the Python interpreter automatically. If Python is not installed on the machine, install it before running the pip commands below.

## 2. Install Dependencies

### 2.1 One-Step Installation and Validation

Run the following commands from the Kit root directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\INSTALL_AND_CHECK.ps1
```

The script:

- Verifies that the installed Python version is 3.11 or later.
- Installs or updates Python package dependencies; the default extras are `.[pdf,company-data,mcp]`.
- Creates the default data directory.
- Replaces any existing destination with the same name and copies the Skill to the user-level `.agents\skills\ah-disclosure` directory.
- Registers the MCP server when the `claude` command is available in the current environment.
- Validates the `ah-disclosure-kit` version and basic CLI commands.

The script does not:

- Install the Python interpreter.
- Install Tesseract OCR.
- Create a project `.venv`.

The script upgrades `pip` in the environment associated with the current `python` command and installs the Kit in editable mode. To isolate it from other Python tools, create and activate a `.venv` before running the script. If no virtual environment is active, the script modifies the environment referenced by the current `python` command.

Common options:

```powershell
.\scripts\INSTALL_AND_CHECK.ps1 -SkipMcpRegistration
.\scripts\INSTALL_AND_CHECK.ps1 -CheckTesseract
.\scripts\INSTALL_AND_CHECK.ps1 -Extras "pdf,company-data,mcp,table,ocr"
```

### 2.2 Manual Installation

Run the following commands from the Kit root directory:

```powershell
cd C:\path\to\ah-disclosure-kit
python -m pip install --upgrade pip
python -m pip install -e ".[pdf,company-data,mcp]"
```

To install development, OCR, table extraction, and vector-related optional features:

```powershell
python -m pip install -e ".[all]"
```

The user determines which Python environment receives the installation. For a long-running MCP server, use a dedicated, persistent `.venv` to reduce dependency conflicts with other tools. If you choose a global or user-level Python environment, first confirm that upgrading `pip` and installing dependencies will not affect existing projects.

The default one-step installation and the standard manual installation above include PDF parsing, AKShare company data, and MCP runtime dependencies. If you only need source discovery and downloads, use `python -m pip install -e .` to install the lightweight core. Other capabilities are available through the `pdf`, `company-data`, `mcp`, `layout`, `table`, `ocr`, `vector`, and `dev` extras. The `layout` extra generates enhanced Markdown based on page layout and is not required for standard ingest. The Python `ocr` dependencies do not install the system-level Tesseract OCR application; install Tesseract separately before using OCR.

## 3. Data Directory

For a source checkout or editable installation, the default data directory is resolved from the project workspace and does not depend on the current working directory:

```text
data/ah_disclosure
```

When the repository is located at `tools/ah-disclosure-kit` inside a workspace, the actual default location is `data/ah_disclosure` under that workspace. For other source layouts, the default is `data/ah_disclosure` inside the repository.

For a wheel installation, the default is the operating system's user data directory: `%LOCALAPPDATA%\ah-disclosure\data` on Windows, `~/Library/Application Support/ah-disclosure/data` on macOS, and `${XDG_DATA_HOME:-~/.local/share}/ah-disclosure/data` on Linux.

Setting the location explicitly is recommended:

```powershell
$env:AH_DISCLOSURE_DATA_DIR="C:\path\to\data\ah_disclosure"
```

The data directory stores:

- Original PDFs: `raw/`
- PDF parsing results: `parsed/`
- SQLite search database: `index/ah_disclosure.sqlite`
- Cache: `cache/`

## 4. Register the MCP Server

Codex uses the following configuration in `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.ah_disclosure]
command = 'C:\path\to\python.exe'
args = ["-m", "ah_disclosure.mcp_server"]
startup_timeout_sec = 120
```

Set `command` to the absolute path of the Python interpreter used to install the Kit. Retrieve it with `python -c "import sys; print(sys.executable)"`. After restarting Codex, run `codex mcp list` and use `/mcp` in interfaces that support command menus to confirm that `ah_disclosure` is connected.

For Claude Code, use:

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

After registration, run the following command in Claude Code:

```text
/mcp
```

Confirm that `ah-disclosure` is online.

## 5. Install the Skill

Copy the entire canonical Skill directory:

```text
skills/ah-disclosure
```

to the user-level directory:

```text
C:\Users\<username>\.agents\skills\ah-disclosure
```

You can instead copy it to `.agents\skills\ah-disclosure` under a project root to make it available only to that project. Do not copy only `SKILL.md`; the `agents/` and `references/` directories are also part of the Skill.

The installation script can also synchronize the Skill directly to a project-level Skill root:

```powershell
.\scripts\INSTALL_AND_CHECK.ps1 -SkillInstallRoot "C:\target-project\.agents\skills"
```

After restarting Codex, confirm on the Skills page or in an interface that supports `/skills` that `ah-disclosure` has been discovered. You can also verify it explicitly in a new task by invoking `$ah-disclosure`.

## 6. Common CLI Commands

Display server information:

```powershell
ah-disclosure server-info
```

Query an A-share company profile:

```powershell
ah-disclosure a profile --symbol 600519
```

Query A-share financial statements:

```powershell
ah-disclosure a financials --symbol 600519 --statement all
```

Download an A-share annual report without ingesting it:

```powershell
ah-disclosure a report --symbol 600519 --year 2024 --download
```

Download and ingest an A-share annual report:

```powershell
ah-disclosure a report --symbol 600519 --year 2024 --download --ingest
```

Query an H-share company profile:

```powershell
ah-disclosure h profile --symbol 00700
```

Download an H-share annual report without ingesting it:

```powershell
ah-disclosure h report --symbol 00700 --download
```

Download and ingest an H-share annual report:

```powershell
ah-disclosure h report --symbol 00700 --download --ingest
```

The tool normally resolves and permanently caches the H-share `hkex_stock_id` automatically. Pass `--hkex-stock-id` only when you need to specify a candidate mapping or troubleshoot identity resolution, or use `resolve --refresh-identity` to verify the mapping again.

Search locally ingested PDFs:

```powershell
ah-disclosure local search --query "revenue recognition"
```

Batch-download, validate, and ingest annual reports or prospectuses:

```powershell
ah-disclosure batch prepare `
  --input examples\batch.example.csv `
  --output batch_result.json `
  --summary-only
```

Inputs may be UTF-8 CSV, JSON, or JSONL files. The required fields are `market` and `symbol`. Optional fields are `company_name`, `document_type`, `report_year`, `language`, and `hkex_stock_id`. Supported `document_type` values are `annual_report` and `prospectus`.

Common batch options:

- `--max-workers 2`: Uses two concurrent workers by default, with a hard limit of four.
- `--resume`: Resumes from the checkpoint associated with the output file.
- `--offline`: Uses only local PDFs, source caches, and indexes.
- `--refresh-source`: Checks the official document source again.
- `--refresh-identity`: Revalidates the permanent HKEX `stockId` mapping.
- `--stop-on-error`: Stops after the first failure and automatically switches to single-threaded execution.
- `--ocr auto|off|force`: Controls the OCR policy for batch ingest; the default is `auto`.
- `--quiet-progress`: Suppresses per-item progress messages on stderr.
- `--summary-only`: Still writes complete results to the `--output` file, but displays only aggregate statistics and per-item status in the terminal.

The batch command does not extract an EvidencePacket or perform analysis, valuation, or writing. Use the local evidence retrieval workflow later when analysis is required. Exact duplicate inputs are processed once, and all duplicate rows reuse that result. The `effective_workers` field in the output reports the actual thread count rather than the requested limit.

When `report_year` is omitted for an annual report, the result populates that field with the year of the latest report selected.

## 7. Common Prompt Patterns

Download a PDF only:

```text
Use ah-disclosure to download Meituan's 2025 annual report. Download the PDF only and do not ingest it.
```

Download and analyze:

```text
Use ah-disclosure to download Meituan's 2025 annual report and analyze its revenue, net profit, and segment profit.
```

Search previously downloaded materials:

```text
Use ah-disclosure to search the locally ingested Tencent 2024 annual report for revenue categories and revenue recognition policies.
```

## 8. Default Behavior

When a user asks only to "download the PDF," the tool does not extract text, write to SQLite, or generate `pages.jsonl` by default.

Ingest runs only when the user asks to analyze, read, search, summarize, or prepare evidence.

---
**Document created:** 2026-07-03 15:44

**Last modified:** 2026-07-23 17:36

**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
