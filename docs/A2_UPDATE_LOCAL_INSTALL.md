# A2 本地更新安装

文档导航：[A0 文档索引](./A0_DOC_INDEX.md)

本文说明代码、依赖、Skill 和 MCP 的更新方式。

如果使用GitHub发布版本，先切换到实际已经发布的目标Tag再安装，避免本地源码版本与文档版本不一致。下面的`<version>`应替换为GitHub Releases页面中存在的版本号；发布前不要假定本地版本已经有对应Tag：

```powershell
git fetch --tags
git checkout v<version>
python -m pip install -e ".[pdf,company-data,mcp]"
```

## 1. 代码更新后

如果只是修改 Python 源码，且已经使用 editable 模式安装：

```powershell
python -m pip install -e ".[pdf,company-data,mcp]"
```

一般不需要重新安装，重启 MCP 会读取最新源码。

## 2. 依赖更新后

如果 `pyproject.toml` 或可选依赖发生变化，重新安装：

```powershell
python -m pip install -e ".[all]"
```

## 3. Skill 更新后

仓库中的下列目录是 Skill 的规范源：

```text
skills/ah-disclosure/
```

更新后必须同步整个目录，而不只是 `SKILL.md`，否则 `agents/` 和 `references/` 会漂移。用户级安装位置为：

```text
C:\Users\<用户名>\.codex\skills\ah-disclosure\
```

项目级安装也可以同步到项目根目录的 `.agents\skills\ah-disclosure\`。运行 `scripts\INSTALL_AND_CHECK.ps1 -SkillInstallRoot "C:\目标项目\.agents\skills"` 会先清理旧目标，再从规范源完整复制，避免遗留已删除的 reference 文件。同步后重启当前 Claude Code / Codex 会话。

## 4. MCP 更新后

如果只是改函数内部逻辑，通常只需要重启 Claude Code / Codex 会话。

如果 MCP 名称或启动命令改变，才需要重新注册：

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

## 5. 数据目录更新后

如果修改了 `AH_DISCLOSURE_DATA_DIR`，需要重新启动 MCP 会话。

源码checkout与wheel安装的默认数据目录不同。更新安装方式不会自动迁移已有数据；需要继续使用原数据时，应显式保持同一个`AH_DISCLOSURE_DATA_DIR`。

不要手工删除 `raw/` 或 `parsed/` 后忽略 SQLite。删除单个公司或文档时，应使用：

- `cleanup_document_tool`
- `cleanup_company_tool`
- `reconcile_local_index_tool`

这样可以让 PDF、解析产物和 SQLite 索引保持一致。

