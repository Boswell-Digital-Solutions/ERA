from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENERATED_AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md")


def sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_scalar(raw: str) -> str:
    value = raw.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def parse_yaml_subset(text: str) -> dict[str, Any]:
    source_lines = text.replace("\r\n", "\n").split("\n")
    lines: list[tuple[int, int, str]] = []
    for line_number, raw in enumerate(source_lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((line_number, len(raw) - len(raw.lstrip(" ")), stripped))

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[str]]] = [(-1, root)]

    def next_child_is_list(index: int, indent: int) -> bool:
        for _line_number, next_indent, content in lines[index + 1 :]:
            if next_indent <= indent:
                return False
            return content.startswith("- ")
        return False

    for index, (line_number, indent, content) in enumerate(lines):
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"Invalid list item at repo.manifest.yaml:{line_number}")
            parent.append(parse_scalar(content[2:]))
            continue

        if isinstance(parent, list):
            raise ValueError(f"Nested list maps are unsupported at repo.manifest.yaml:{line_number}")

        if ":" not in content:
            raise ValueError(f"Invalid manifest line {line_number}: {content}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            raise ValueError(f"Invalid empty manifest key at line {line_number}")

        if value:
            parent[key] = parse_scalar(value)
            continue

        child: dict[str, Any] | list[str] = [] if next_child_is_list(index, indent) else {}
        parent[key] = child
        stack.append((indent, child))

    return root


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"repo.manifest.yaml is missing object: {label}")
    return value


def require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"repo.manifest.yaml is missing string: {label}")
    return value


def require_str_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"repo.manifest.yaml is missing string list: {label}")
    return value


def optional_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


def load_manifest(root: Path) -> tuple[dict[str, Any], str, str]:
    manifest_text = (root / "repo.manifest.yaml").read_text(encoding="utf-8")
    parsed = parse_yaml_subset(manifest_text)
    repo = require_dict(parsed.get("repo"), "repo")
    identity = require_dict(parsed.get("identity"), "identity")
    policy = require_dict(parsed.get("agent_edit_policy"), "agent_edit_policy")
    verification = parsed.get("verification")
    verification_dict = require_dict(verification, "verification") if verification is not None else {}

    manifest = {
        "schema_version": require_str(parsed.get("schema_version"), "schema_version"),
        "repo": {
            "full_name": require_str(repo.get("full_name"), "repo.full_name"),
            "local_name": require_str(repo.get("local_name"), "repo.local_name"),
            "package_name": require_str(repo.get("package_name"), "repo.package_name"),
            "default_branch": require_str(repo.get("default_branch"), "repo.default_branch"),
            "repo_class": require_str(repo.get("repo_class"), "repo.repo_class"),
        },
        "identity": {
            "product_name": require_str(identity.get("product_name"), "identity.product_name"),
            "one_line": require_str(identity.get("one_line"), "identity.one_line"),
            "authority_role": require_str(identity.get("authority_role"), "identity.authority_role"),
        },
        "owns": require_str_list(parsed.get("owns"), "owns"),
        "does_not_own": require_str_list(parsed.get("does_not_own"), "does_not_own"),
        "upstream_authorities": parsed.get("upstream_authorities") or {},
        "downstream_consumers": optional_str_list(parsed.get("downstream_consumers")),
        "canonical_files": require_str_list(parsed.get("canonical_files"), "canonical_files"),
        "generated_files": require_str_list(parsed.get("generated_files"), "generated_files"),
        "agent_edit_policy": {
            "may_edit": require_str_list(policy.get("may_edit"), "agent_edit_policy.may_edit"),
            "must_not_edit_directly": require_str_list(
                policy.get("must_not_edit_directly"),
                "agent_edit_policy.must_not_edit_directly",
            ),
            "must_regenerate": require_str_list(
                policy.get("must_regenerate"),
                "agent_edit_policy.must_regenerate",
            ),
        },
        "verification": {
            "required_identity_checks": optional_str_list(
                verification_dict.get("required_identity_checks")
            ),
            "test_commands": optional_str_list(verification_dict.get("test_commands")),
            "build_commands": optional_str_list(verification_dict.get("build_commands")),
            "safety_rules": optional_str_list(verification_dict.get("safety_rules")),
            "llm_rules": optional_str_list(verification_dict.get("llm_rules")),
        },
    }
    return manifest, manifest_text, sha256(manifest_text)


def run_git(root: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()


def normalize_remote_full_name(remote_url: str) -> str:
    remote = remote_url.strip()
    if remote.endswith(".git"):
        remote = remote[:-4]
    scp_like = re.match(r"^git@[^:]+:(.+)$", remote)
    if scp_like:
        return scp_like.group(1).lower()
    github_like = re.search(r"github\.com[:/](.+)$", remote)
    if github_like:
        return github_like.group(1).lower()
    return remote.lower()


def extract_readme_title(readme: str) -> str:
    html_title = re.search(r"<h1[^>]*>(.*?)</h1>", readme, flags=re.I | re.S)
    if html_title:
        return re.sub(r"<[^>]+>", "", html_title.group(1)).strip()
    markdown_title = re.search(r"^#(?!#)\s+(.+)$", readme, flags=re.M)
    return markdown_title.group(1).strip() if markdown_title else ""


def project_name(root: Path) -> tuple[str | None, str | None]:
    package_json = root / "package.json"
    if package_json.exists():
        return json.loads(package_json.read_text(encoding="utf-8")).get("name"), "package.json"

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return data.get("project", {}).get("name"), "pyproject.toml"

    cargo = root / "Cargo.toml"
    if cargo.exists():
        data = tomllib.loads(cargo.read_text(encoding="utf-8"))
        return data.get("package", {}).get("name"), "Cargo.toml"

    return None, None


def list_section(items: list[str]) -> str:
    if not items:
        return "- None declared\n"
    return "".join(f"- {item}\n" for item in items)


def authority_section(authorities: dict[str, Any]) -> str:
    if not authorities:
        return "- None declared\n"
    lines: list[str] = []
    for name, value in authorities.items():
        if isinstance(value, dict):
            lines.append(f"- {name}: {value.get('owns', 'authority declared in repo.manifest.yaml')}")
        else:
            lines.append(f"- {name}: {value}")
    return "\n".join(lines) + "\n"


def render_agent_instruction(file_name: str, manifest: dict[str, Any], manifest_hash: str) -> str:
    repo = manifest["repo"]
    identity = manifest["identity"]
    policy = manifest["agent_edit_policy"]
    verification = manifest["verification"]
    return f"""<!--
GENERATED FILE - DO NOT EDIT DIRECTLY

Source: repo.manifest.yaml
Generated by: scripts/generate_agent_instructions.py
Manifest hash: {manifest_hash}
Receipt: receipts/repo-context/latest.json
-->

# {file_name} - {identity["product_name"]} Agent Instructions

## Repo Identity

- Full name: {repo["full_name"]}
- Local name: {repo["local_name"]}
- Package name: {repo["package_name"]}
- Default branch: {repo["default_branch"]}
- Repo class: {repo["repo_class"]}
- Product: {identity["product_name"]}
- Authority role: {identity["authority_role"]}
- Summary: {identity["one_line"]}

## Owns

{list_section(manifest["owns"])}
## Does Not Own

{list_section(manifest["does_not_own"])}
## Upstream Authorities

{authority_section(manifest["upstream_authorities"])}
## Downstream Consumers

{list_section(manifest["downstream_consumers"])}
## Canonical Files

{list_section(manifest["canonical_files"])}
## Generated Files

{list_section(manifest["generated_files"])}
## Agent Edit Policy

Agents may edit:

{list_section(policy["may_edit"])}
Agents must not edit these files directly:

{list_section(policy["must_not_edit_directly"])}
Regenerate these files after manifest changes:

{list_section(policy["must_regenerate"])}
## Verification Commands

Context and drift:

- python3 scripts/generate_agent_instructions.py
- python3 scripts/check_agent_instruction_drift.py
- python3 scripts/verify_repo_context.py

Tests:

{list_section(verification["test_commands"])}
Builds:

{list_section(verification["build_commands"])}
## Safety Rules

{list_section(verification["safety_rules"])}
## Repo-Specific LLM Rules

{list_section(verification["llm_rules"])}
## Required Preflight Before Cross-Repo Work

- Confirm the target repo path and git remote before reading architectural meaning from files.
- Confirm the repo class and authority role from repo.manifest.yaml.
- List the files you plan to read and edit.
- Do not mutate upstream authority repos unless the work order explicitly allows it.
- Run python3 scripts/verify_repo_context.py before claiming this repo is agent-governed.
"""


def expected_instructions(root: Path) -> dict[str, str]:
    manifest, _manifest_text, manifest_hash = load_manifest(root)
    generated = set(manifest["generated_files"])
    return {
        file_name: render_agent_instruction(file_name, manifest, manifest_hash)
        for file_name in GENERATED_AGENT_FILES
        if file_name in generated
    }


def generate(root: Path) -> None:
    expected = expected_instructions(root)
    for file_name, contents in expected.items():
        (root / file_name).write_text(contents, encoding="utf-8")
    print(f"Generated {len(expected)} agent instruction files from repo.manifest.yaml")


def drift(root: Path) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for file_name, expected in expected_instructions(root).items():
        target = root / file_name
        if not target.exists():
            results.append((file_name, "missing"))
        elif target.read_text(encoding="utf-8") != expected:
            results.append((file_name, "stale"))
    return results


def check_drift(root: Path) -> int:
    results = drift(root)
    if not results:
        print("Generated agent instructions match repo.manifest.yaml")
        return 0
    for file_name, reason in results:
        print(f"{reason.upper()}: {file_name}", file=sys.stderr)
    return 1


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256(path.read_text(encoding="utf-8"))


def verify(root: Path) -> int:
    manifest, _manifest_text, manifest_hash = load_manifest(root)
    repo = manifest["repo"]
    identity = manifest["identity"]
    checks: list[dict[str, str]] = []
    warnings: list[str] = []

    def add_check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"id": check_id, "status": "passed" if passed else "failed", "detail": detail})

    remote = run_git(root, ["remote", "get-url", "origin"])
    add_check(
        "repository_full_name",
        normalize_remote_full_name(remote) == repo["full_name"].lower(),
        f"origin is {remote}; expected {repo['full_name']}",
    )

    local_name = root.name
    add_check(
        "local_directory_name",
        local_name == repo["local_name"],
        f"directory is {local_name}; expected {repo['local_name']}",
    )

    detected_project_name, project_source = project_name(root)
    if detected_project_name is None:
        warnings.append("No package.json, pyproject.toml, or Cargo.toml found; package_name is manifest-only.")
        add_check(
            "package_name",
            bool(repo["package_name"]),
            f"manifest package name is {repo['package_name']}",
        )
    else:
        add_check(
            "package_name",
            detected_project_name == repo["package_name"],
            f"{project_source} name is {detected_project_name}; expected {repo['package_name']}",
        )

    readme_title = extract_readme_title((root / "README.md").read_text(encoding="utf-8"))
    add_check(
        "README title",
        readme_title == identity["product_name"],
        f"README title is {readme_title or '<missing>'}; expected {identity['product_name']}",
    )

    current_branch = run_git(root, ["branch", "--show-current"])
    add_check(
        "default_branch",
        current_branch == repo["default_branch"],
        f"current branch is {current_branch}; expected {repo['default_branch']}",
    )

    for file_name in manifest["canonical_files"]:
        exists = (root / file_name).exists()
        add_check(
            f"canonical_file:{file_name}",
            exists,
            f"{file_name} {'exists' if exists else 'is missing'}",
        )

    drift_results = drift(root)
    add_check(
        "generated_instruction_hashes_match",
        not drift_results,
        "generated instruction files match repo.manifest.yaml"
        if not drift_results
        else "generated instruction drift: " + ", ".join(item[0] for item in drift_results),
    )

    generated_files = {
        file_name: file_hash(root / file_name) for file_name in manifest["generated_files"]
    }
    status = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    receipt = {
        "schema_version": "RepoContextVerificationReceipt.v1",
        "timestamp": timestamp,
        "repo_full_name": repo["full_name"],
        "repo_class": repo["repo_class"],
        "authority_role": identity["authority_role"],
        "local_path": str(root),
        "git_remote": remote,
        "default_branch": repo["default_branch"],
        "current_branch": current_branch,
        "package_name": detected_project_name or repo["package_name"],
        "package_source": project_source or "repo.manifest.yaml",
        "readme_title": readme_title,
        "manifest_hash": manifest_hash,
        "generated_files": generated_files,
        "checks": checks,
        "status": status,
        "warnings": warnings,
    }

    receipt_dir = root / "receipts" / "repo-context"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    timestamped = receipt_dir / f"{stamp}.json"
    latest = receipt_dir / "latest.json"
    receipt_text = json.dumps(receipt, indent=2) + "\n"
    timestamped.write_text(receipt_text, encoding="utf-8")
    latest.write_text(receipt_text, encoding="utf-8")

    if status == "passed":
        print(f"Repo context verification passed: {timestamped.relative_to(root)}")
        for warning in warnings:
            print(f"WARNING: {warning}")
        return 0

    print(f"Repo context verification failed: {timestamped.relative_to(root)}", file=sys.stderr)
    for check in checks:
        if check["status"] == "failed":
            print(f"FAILED {check['id']}: {check['detail']}", file=sys.stderr)
    return 1


def main(action: str) -> int:
    root = Path.cwd()
    if action == "generate":
        generate(root)
        return 0
    if action == "check-drift":
        return check_drift(root)
    if action == "verify":
        return verify(root)
    raise ValueError(f"Unknown action: {action}")
