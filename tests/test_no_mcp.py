"""CodePilot itself never connects to MCP servers. MCP is a developer tool for Claude Code in this repo (.mcp.json)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_product_code_does_not_use_mcp():
    pattern = re.compile(r"^\s*(?:import|from)\s+(?:mcp|fastmcp|langchain_mcp\w*)\b|mcpServers|mcp_servers|stdio_client", re.M)
    hits = [str(p.relative_to(ROOT)) for p in (ROOT / "codepilot").rglob("*.py") if pattern.search(p.read_text())]
    assert not hits, f"CodePilot must not connect to MCP servers: {hits}"


def test_no_mcp_dependency_is_declared():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    deps = [*project["dependencies"], *(d for group in project["optional-dependencies"].values() for d in group)]
    assert not [d for d in deps if "mcp" in d.lower()], deps


def test_mcp_config_is_not_shipped_in_the_package():
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
    assert not [g for globs in package_data.values() for g in globs if "mcp" in g.lower()]
