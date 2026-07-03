# A2 本地更新安装

相关文档：[README](../README.md) | [A0.文档索引](./A0_DOC_INDEX.md) | [A1.安装使用](./A1_INSTALLATION_AND_USAGE.md) | [A2.本地更新](./A2_UPDATE_LOCAL_INSTALL.md) | [A3.工作流](./A3_WORKFLOW.md) | [A4.MCP函数](./A4_MCP_TOOLS.md) | [B1.PDF Ingest](./B1_PDF_INGEST.md) | [B2.公司数据](./B2_COMPANY_DATA.md) | [B3.HKEX](./B3_HKEX.md) | [B4.招股书](./B4_PROSPECTUS.md) | [C1.测试计划](./C1_TEST_PLAN.md) | [D1.开发计划](./D1_DEVELOPMENT_PLAN_V1_0.md) | [命令示例](../examples/A0_CLAUDE_CODE_COMMANDS.md) | [更新日志](../CHANGELOG.md)

本文说明代码、依赖、Skill 和 MCP 的更新方式。

## 1. 代码更新后

如果只是修改 Python 源码，且已经使用 editable 模式安装：

```powershell
python -m pip install -e ".[pdf]"
```

一般不需要重新安装，重启 MCP 会读取最新源码。

## 2. 依赖更新后

如果 `pyproject.toml` 或可选依赖发生变化，重新安装：

```powershell
python -m pip install -e ".[pdf,table,ocr,vector,dev]"
```

## 3. Skill 更新后

如果修改了：

```text
skills/ah-disclosure/SKILL.md
```

需要同步到：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure\SKILL.md
```

同步后重启当前 Claude Code / Codex 会话，确保新规则生效。

## 4. MCP 更新后

如果只是改函数内部逻辑，通常只需要重启 Claude Code / Codex 会话。

如果 MCP 名称或启动命令改变，才需要重新注册：

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

## 5. 数据目录更新后

如果修改了 `AH_DISCLOSURE_DATA_DIR`，需要重新启动 MCP 会话。

不要手工删除 `raw/` 或 `parsed/` 后忽略 SQLite。删除单个公司或文档时，应使用：

- `cleanup_document_tool`
- `cleanup_company_tool`
- `reconcile_local_index_tool`

这样可以让 PDF、解析产物和 SQLite 索引保持一致。

