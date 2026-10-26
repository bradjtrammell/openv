#!/usr/bin/env python3
"""Explain exact OpenV Windows runtime build failures without weakening audits.

Reads the already-generated build report. Never stages DLLs, invents licenses,
marks GTA V gameplay ready, or reclassifies imports as Windows system DLLs.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

PROVISIONED = frozenset({"mono-2.0-sgen.dll", "avutil-56.dll", "swresample-3.dll"})
GAME_OWNED = frozenset({"steam_api64.dll"})


def read_report(path: Path):
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(obj, dict):
            raise ValueError("report root is not a JSON object")
        return obj
    except (OSError, ValueError, UnicodeError) as exc:
        return {"status": "unavailable", "error": type(exc).__name__}


def explain(audit: dict, stage: dict) -> dict:
    problems: list[str] = []
    files: dict[str, list[str]] = {}
    imported = audit.get("unresolved_imports", [])
    if not isinstance(imported, list):
        imported = []
    for item in imported:
        if not isinstance(item, dict) or not isinstance(item.get("dlls"), list):
            continue
        parent = item.get("path", "?")
        if not isinstance(parent, str):
            parent = "?"
        for dll in item["dlls"]:
            if isinstance(dll, str) and dll.lower().endswith(".dll"):
                files.setdefault(dll.lower(), []).append(parent)
    for field in ("missing_open_runtime", "missing_cef_runtime", "missing_required"):
        value = audit.get(field, [])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    files.setdefault(item.lower(), [])
    # A report from a skipped audit must not be mistaken for a complete build.
    if audit.get("status") == "unavailable":
        problems.append("Runtime audit report was not produced; inspect the earlier build, UI and staging steps.")
    elif audit.get("status") != "static_inventory_pass":
        problems.append("The full runtime dependency audit did not pass.")
    if stage.get("status") == "not_configured":
        problems.append("Mono/FFmpeg provisioning was skipped: OPENV_RUNTIME_DEPENDENCIES_MANIFEST is not configured.")
    elif stage.get("status") == "failed":
        problems.append("Mono/FFmpeg staging failed; inspect open-runtime-provenance.json for details.")
    if files:
        problems.append("Unresolved runtime files: " + ", ".join(sorted(files)))
    extras = audit.get("binary_errors", [])
    if isinstance(extras, list) and extras:
        problems.append("One or more PE binaries failed integrity/architecture validation.")
    if "ui_error" in audit:
        problems.append("The first-party UI archive validation failed.")
    if audit.get("staging_integrity", {}).get("status") == "mismatch":
        problems.append("The staged runtime differs from the audited build; review missing, unexpected and altered files.")
    remedy: list[str] = []
    missing = set(files)
    if missing & PROVISIONED or stage.get("status") == "not_configured":
        remedy.append("Stage compatible AMD64 Mono and FFmpeg from approved redistributable sources, with real license files and verified SHA-256 hashes, using tools/stage_open_runtime.py and the pinned manifest schema. Do not substitute newer ABI DLL names.")
    if missing & GAME_OWNED:
        remedy.append("steam_api64.dll is a Steam/platform dependency. Verify resolution against a legitimately installed GTA V/Steam environment during the real Windows launch test; do not copy a random DLL, bypass ownership checks, or silently whitelist this import.")
    other = missing - PROVISIONED - GAME_OWNED
    if other:
        remedy.append("Resolve remaining imports by rebuilding/staging the correct first-party or third-party runtime; never add missing third-party imports to WINDOWS_DLLS.")
    if not problems:
        problems.append("No failure identified in supplied reports; inspect earlier job steps and build-report artifacts.")
    return {"status": "blocked" if problems else "unknown",
            "audit_status": audit.get("status", "unknown"),
            "open_runtime_stage": stage.get("status", "unknown"),
            "unresolved": {name: sorted(set(users)) for name, users in sorted(files.items())},
            "problems": problems, "recommended_actions": remedy,
            "gameplay_verified": False}


def emit(summary: dict, summary_file: Path | None):
    lines = ["## OpenV Windows Client — exact build diagnosis", "",
             "**No verified playable client was produced by this failed run.**", ""]
    for message in summary["problems"]:
        lines.append("- " + message)
    lines.append("")
    for message in summary["recommended_actions"]:
        lines.append("- " + message)
    lines.append("")
    lines.append("Full machine-readable evidence: build-report/runtime-static-audit.json and build-report/open-runtime-provenance.json")
    output = "\n".join(lines) + "\n"
    print(output)
    if summary_file:
        with summary_file.open("a", encoding="utf-8") as f:
            f.write(output)
    # A short build log annotation rather than thousands of JSON lines.
    for message in summary["problems"][:12]:
        safe = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error title=OpenV runtime dependency blocked::" + safe)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", required=True, type=Path)
    p.add_argument("--open-runtime", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--github-summary", type=Path)
    args = p.parse_args(argv)
    result = explain(read_report(args.audit), read_report(args.open_runtime))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit(result, args.github_summary)
    return 0  # Diagnosis must not hide previous gate results or prevent artifact upload.


if __name__ == "__main__":
    raise SystemExit(main())
