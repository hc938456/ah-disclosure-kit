# A2 Updating a Local Installation

Documentation navigation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This guide explains how to update the code, dependencies, Skill, and MCP server.

When using a GitHub release, switch to the target tag that has actually been published before installing. This prevents the local source version from diverging from the documentation version. Replace `<version>` below with a version that exists on the GitHub Releases page. Do not assume that a local version already has a corresponding tag before it is released:

```powershell
git fetch --tags
git checkout v<version>
python -m pip install -e ".[pdf,company-data,mcp]"
```

## 1. After Updating the Code

If only Python source files changed and the package is already installed in editable mode, reinstallation is generally unnecessary. Restart the MCP server to load the latest source code.

Run the editable-install command again only when package metadata, entry points, or dependencies changed.

## 2. After Updating Dependencies

If `pyproject.toml` or optional dependencies changed, reinstall:

```powershell
python -m pip install -e ".[all]"
```

## 3. After Updating the Skill

The following directory in the repository is the canonical source for the Skill:

```text
skills/ah-disclosure/
```

After an update, synchronize the entire directory rather than only `SKILL.md`; otherwise, the `agents/` and `references/` directories may drift. The user-level installation directory is:

```text
C:\Users\<username>\.agents\skills\ah-disclosure\
```

You may also install the Skill at the project level by synchronizing it to `.agents\skills\ah-disclosure\` under the project root. Running `scripts\INSTALL_AND_CHECK.ps1 -SkillInstallRoot "C:\target-project\.agents\skills"` removes the old destination first and then copies the canonical source in full, preventing deleted reference files from being left behind. Restart the current Claude Code or Codex session after synchronization.

## 4. After Updating the MCP Server

If only internal function logic changed, restarting the Claude Code or Codex session is usually sufficient.

You need to register the server again only if the MCP name or startup command changed:

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

## 5. After Changing the Data Directory

Restart the MCP session after changing `AH_DISCLOSURE_DATA_DIR`.

Source checkouts and wheel installations use different default data directories. Updating the installation method does not migrate existing data automatically. To continue using existing data, explicitly preserve the same `AH_DISCLOSURE_DATA_DIR`.

Do not manually delete files from `raw/` or `parsed/` while leaving SQLite unchanged. To remove an individual company or document, use:

- `cleanup_document_tool`
- `cleanup_company_tool`
- `reconcile_local_index_tool`

These tools keep PDFs, parsed artifacts, and the SQLite index consistent.

---
**Document created:** 2026-07-03 15:44

**Last modified:** 2026-07-23 17:36

**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
