from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "ah-disclosure"

EXPECTED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/Analysis_Protocol.md",
    "references/Financial_Analysis.md",
    "references/Operations.md",
    "references/Troubleshooting.md",
}

REQUIRED_MCP_ENTRYPOINTS = {
    "server_info",
    "find_filing_source_tool",
    "download_report_tool",
    "download_and_ingest_report",
    "search_prospectus_tool",
    "download_prospectus_tool",
    "download_and_ingest_prospectus_tool",
    "ingest_pdf_tool",
    "get_company_profile_tool",
    "get_business_info_tool",
    "get_financial_statements_tool",
    "get_financial_indicators_tool",
    "get_dividends_tool",
    "get_shareholders_tool",
    "get_capital_actions_tool",
    "get_governance_esg_tool",
    "list_local_documents_tool",
    "get_document_meta_tool",
    "build_company_dossier_tool",
    "compare_structured_data_with_report_tool",
    "ensure_filing_evidence_tool",
    "get_evidence_packet_tool",
    "get_document_pages_tool",
    "prepare_llm_analysis_tool",
    "execute_llm_analysis_plan_tool",
    "continue_llm_analysis_tool",
    "verify_analysis_calculations_tool",
}


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_skill_has_only_expected_files() -> None:
    assert _relative_files(SKILL_ROOT) == EXPECTED_FILES


def test_skill_frontmatter_and_links_are_self_contained() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match is not None
    keys = {
        line.split(":", 1)[0].strip()
        for line in match.group(1).splitlines()
        if ":" in line
    }
    assert keys == {"name", "description"}
    assert "name: ah-disclosure" in match.group(1)

    for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = (SKILL_ROOT / link).resolve()
        assert target.is_relative_to(SKILL_ROOT.resolve())
        assert target.is_file()


def test_openai_metadata_declares_the_real_mcp_dependency() -> None:
    text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "A/H Disclosure Analysis"' in text
    assert "$ah-disclosure" in text
    assert 'type: "mcp"' in text
    assert 'value: "ah_disclosure"' in text
    assert 'transport: "stdio"' in text
    assert "allow_implicit_invocation: true" in text


def test_skill_tools_exist_in_mcp_server_source() -> None:
    source = (ROOT / "src" / "ah_disclosure" / "mcp_server.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert REQUIRED_MCP_ENTRYPOINTS <= functions


def test_distribution_and_installer_preserve_complete_skill() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include skills *.md *.yaml" in manifest

    installer = (ROOT / "scripts" / "INSTALL_AND_CHECK.ps1").read_text(encoding="utf-8")
    assert "SkillInstallRoot" in installer
    assert '"skills\\ah-disclosure"' in installer
    assert '".agents\\skills"' in installer
    assert '".codex\\skills"' not in installer
    assert "Copy-Item -Recurse" in installer


def test_skill_has_no_foreign_project_references() -> None:
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
    ).lower()
    forbidden = ("membership-revenue", "casc-accounting", "semantic-layer")
    assert not any(value in content for value in forbidden)
