#!/usr/bin/env python3
"""
assemble_context.py — AI context assembler for any project module.

Given a source file path, assembles a single focused AI briefing document:
  - Module AI_CONTEXT.md           (always — primary reference)
  - AI_SUMMARY.md                  (always, if exists — public API snapshot)
  - docs/REALTIME_RULES.md         (if module has RT thread constraints)
  - Referenced ADRs                (from ## See also section, up to N lines each)
  - docs/KNOWN_FAILURE_PATTERNS.md (always, if exists — bounded at 200 lines)
  - graphify dependency context    (node + neighbors, if binary + graph available)
  - Claude Code MEMORY.md          (first 50 lines — cross-session context)

Usage:
    python tools/ai_docs/assemble_context.py <source_file>
    python tools/ai_docs/assemble_context.py <source_file> --output context.md
    python tools/ai_docs/assemble_context.py <source_file> --no-memory
    python tools/ai_docs/assemble_context.py <source_file> --max-bytes 65536

Selection under the total budget goes exclusively through the unified
ContextPlanner (ainative.knowledge.planner); this script gathers files
and renders, it does not rank. Default output is byte-identical to the
pre-planner assembler on the same inputs.

Works for any project structure — no hardcoded paths.
The AI_CONTEXT.md acts as the module marker (same as generate_ai_summary.py).

Exit codes:
    0 — success (context written)
    1 — source_file not found or no module found in ancestor tree
"""

from __future__ import annotations  # PEP 563 — keep `X | None` valid on Python 3.8/3.9

import argparse
import re
import subprocess
import sys
from pathlib import Path

from module_discovery import find_module  # noqa: E402

# Repo root on sys.path so the unified ContextPlanner is importable whether
# this file runs as `python tools/ai_docs/assemble_context.py` (script dir
# only) or is imported by the test suite (tools dir only). Same precedent
# as scripts/workplane_harness_matrix.py. Selection and ranking below go
# through that planner and nothing else (B2 single-owner rule).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ainative.knowledge import planner as planner_module  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Keywords in AI_CONTEXT.md that indicate real-time thread constraints
RT_KEYWORDS = {
    "audio thread", "rt thread", "audio callback", "real-time",
    "processaudio", "process_block", "zero alloc", "zero allocation",
    "no allocation", "lock-free", "rt_safe", "audio_thread_only",
    "real time", "no mutex", "no blocking",
}

SECTION_WIDTH = 72


# ---------------------------------------------------------------------------
# Module discovery helpers
# ---------------------------------------------------------------------------

def find_project_root(start: Path) -> Path:
    """Walk up to find the git root; fall back to start."""
    p = start.resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return start.resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_rt_constraints(ctx_text: str) -> bool:
    """Return True if the AI_CONTEXT.md text mentions RT thread constraints."""
    lower = ctx_text.lower()
    return any(kw in lower for kw in RT_KEYWORDS)


def extract_adr_refs(ctx_text: str) -> list[str]:
    """Parse all ADR-XXXX references from the ## See also section."""
    adrs: list[str] = []
    in_see_also = False
    for line in ctx_text.splitlines():
        if line.startswith("## See also"):
            in_see_also = True
            continue
        if in_see_also:
            if line.startswith("## "):
                break
            for m in re.finditer(r"\bADR-(\d{3,4})\b", line, re.IGNORECASE):
                adrs.append("ADR-" + m.group(1).zfill(4))
    return list(dict.fromkeys(adrs))  # deduplicated, order preserved


def find_graphify_bin() -> str | None:
    """Locate the graphify binary: GRAPHIFY_BIN env, then PATH, then common dirs."""
    import os
    import shutil
    env_bin = os.environ.get("GRAPHIFY_BIN")
    if env_bin and env_bin != "graphify" and Path(env_bin).exists():
        return env_bin
    if g := shutil.which("graphify"):
        return g
    candidates = [
        str(Path.home() / ".local" / "bin" / "graphify"),
        "/usr/local/bin/graphify",
        str(Path.home() / "bin" / "graphify"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def run_graphify_explain(graphify_bin: str, root: Path, file_path: Path) -> str | None:
    """Run `graphify explain <node>` for the file and return its neighbors view.

    graphify's `explain` resolves a node by id or label; a source file's label is
    its basename (e.g. `lib.rs`). It does NOT accept a relative path, and it
    returns exit 0 with "No node matching ..." when nothing is found — so we must
    inspect stdout rather than the return code. (`path` was the wrong command:
    it needs two node names, not a single file.)
    """
    graph = root / "graphify-out" / "graph.json"
    if not graph.exists():
        return None
    try:
        result = subprocess.run(
            [graphify_bin, "explain", file_path.name, "--graph", str(graph)],
            capture_output=True, text=True, timeout=10, cwd=str(root),
        )
    except Exception:
        return None
    out = result.stdout.strip()
    if not out or "No node matching" in out:
        return None
    return out


def find_claude_memory(root: Path) -> Path | None:
    """Locate the Claude Code MEMORY.md for this project."""
    home = Path.home()
    projects_dir = home / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    # Claude Code derives the key from the project path:
    # replaces drive colon and separators with '-', strips leading '-'
    root_str = str(root)
    key_raw = root_str.replace(":", "").replace("\\", "-").replace("/", "-").strip("-")
    for key in (key_raw, key_raw.lower(), key_raw.replace("--", "-")):
        mem = projects_dir / key / "memory" / "MEMORY.md"
        if mem.exists():
            return mem

    # No deterministic match for THIS project. Do not fall back to the
    # most-recently-modified MEMORY.md across all projects: on a multi-project
    # machine that would splice another project's private memory into the
    # context. Better to return nothing than the wrong project's memory.
    return None


def section_header(title: str) -> str:
    bar = "─" * SECTION_WIDTH
    return f"\n{bar}\n## {title}\n{bar}\n"


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

def _section_source(key: str, title: str, text: str, kind: str,
                    scope: str, locator: str, tier: str | None = None) -> dict:
    """One gathered section as a planner source. Pure data mapping."""

    record: dict = {"kind": kind, "locator": locator, "scope": scope,
                    "excerpt": text}
    if tier is not None:
        record["tier"] = tier
    return record


def assemble(
    source_file: Path,
    include_memory: bool = True,
    max_adr_lines: int = 60,
    memory_lines: int = 50,
    max_kfp_lines: int = 200,
    max_total_bytes: int = 262144,
) -> str:
    """Assemble the context document for source_file.

    Gathering is unchanged (same files, same per-section caps, same
    order). Selection under the total budget goes exclusively through
    the unified ContextPlanner: sections it drops are omitted with a
    note, Tier A is never silently evicted (overflow raises visibly).
    """

    source_file = source_file.resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    root = find_project_root(source_file)
    module_dir = find_module(source_file)
    if module_dir is None:
        raise ValueError(
            f"No AI_CONTEXT.md found in ancestor directories of {source_file}.\n"
            "Create an AI_CONTEXT.md in the module directory to enable context assembly."
        )

    module_name = module_dir.name
    module_scope = f"module/{module_name}"
    try:
        rel_source = source_file.relative_to(root)
        rel_module = module_dir.relative_to(root)
    except ValueError:
        rel_source = source_file
        rel_module = module_dir

    parts = [
        f"# AI Context — `{rel_source}`",
        "",
        f"> Assembled by `tools/ai_docs/assemble_context.py`  ",
        f"> Module: `{rel_module}`  ",
        f"> Project root: `{root}`",
        "",
    ]

    # Gather (legacy selection of files, unchanged) -------------------- #
    sections: list[tuple[str, str, str]] = []
    sources: list[dict] = []

    def _add(key: str, title: str, text: str, kind: str, scope: str,
             locator: str, tier: str | None = None) -> None:
        sections.append((key, title, text))
        sources.append(_section_source(key, title, text, kind, scope,
                                       locator, tier))

    ctx_path = module_dir / "AI_CONTEXT.md"
    ctx_text = ctx_path.read_text(encoding="utf-8", errors="ignore")
    _add("context", f"MODULE CONTEXT — {module_name}", ctx_text.strip(),
         "ai-context", module_scope, str(ctx_path.relative_to(root))
         if _within(root, ctx_path) else ctx_path.name)

    summary_path = module_dir / "AI_SUMMARY.md"
    if summary_path.exists():
        summary_text = summary_path.read_text(encoding="utf-8", errors="ignore")
        _add("summary", "PUBLIC API SNAPSHOT  (auto-generated)",
             summary_text.strip(), "summary", module_scope,
             str(summary_path.relative_to(root))
             if _within(root, summary_path) else summary_path.name)

    if has_rt_constraints(ctx_text):
        rt_path = root / "docs" / "REALTIME_RULES.md"
        if rt_path.exists():
            rt_text = rt_path.read_text(encoding="utf-8", errors="ignore")
            _add("realtime",
                 "REAL-TIME RULES  (injected — RT constraints detected)",
                 rt_text.strip(), "policy", "repository", "docs/REALTIME_RULES.md")
        else:
            _add("realtime", "REAL-TIME RULES",
                 "_`docs/REALTIME_RULES.md` not found._  \n"
                 "_Create it to capture zero-alloc / zero-blocking constraints._",
                 "policy", "repository", "docs/REALTIME_RULES.md")

    adr_refs = extract_adr_refs(ctx_text)
    adr_dir = root / "docs" / "adr"
    if adr_refs and adr_dir.exists():
        blocks = []
        for adr_id in adr_refs:
            num = adr_id.replace("ADR-", "")
            matches = list(adr_dir.glob(f"{num}-*.md")) or list(adr_dir.glob(f"ADR-{num}-*.md"))
            if matches:
                adr_text = matches[0].read_text(encoding="utf-8", errors="ignore")
                adr_lines = adr_text.splitlines()
                excerpt = "\n".join(adr_lines[:max_adr_lines])
                if len(adr_lines) > max_adr_lines:
                    excerpt += (
                        f"\n_... ({len(adr_lines) - max_adr_lines} more lines "
                        f"— see `{matches[0].relative_to(root)}`)_"
                    )
                blocks.append(f"### {adr_id}\n{excerpt}")
            else:
                blocks.append(f"### {adr_id} — _not found in `docs/adr/`_")
        _add("adrs", "REFERENCED ADRs", "\n\n".join(blocks) + "\n",
             "adr", "project", "docs/adr")

    kfp_path = root / "docs" / "KNOWN_FAILURE_PATTERNS.md"
    if kfp_path.exists():
        kfp_lines = kfp_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        excerpt = "\n".join(kfp_lines[:max_kfp_lines])
        if len(kfp_lines) > max_kfp_lines:
            excerpt += (
                f"\n_... ({len(kfp_lines) - max_kfp_lines} more lines "
                f"— see `docs/KNOWN_FAILURE_PATTERNS.md`)_"
            )
        _add("kfp", "KNOWN FAILURE PATTERNS", excerpt,
             "kfp", "project", "docs/KNOWN_FAILURE_PATTERNS.md")

    graphify_bin = find_graphify_bin()
    if graphify_bin:
        gfx_result = run_graphify_explain(graphify_bin, root, source_file)
        if gfx_result:
            _add("graphify", "DEPENDENCY CONTEXT  (graphify explain)",
                 f"```\n{gfx_result}\n```", "code", module_scope,
                 "graphify", tier="C")

    if include_memory:
        mem_path = find_claude_memory(root)
        if mem_path and mem_path.exists():
            mem_lines = mem_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            excerpt = "\n".join(mem_lines[:memory_lines])
            if len(mem_lines) > memory_lines:
                excerpt += (
                    f"\n_... ({len(mem_lines) - memory_lines} more lines — see `{mem_path}`)_"
                )
            _add("memory", f"PROJECT MEMORY  (first {memory_lines} lines)",
                 excerpt, "session", "project", str(mem_path))

    # Select (single owner: the unified ContextPlanner) ---------------- #
    bundle = planner_module.plan(
        sources,
        focus=[module_scope],
        budgets=planner_module.Budgets(max_bytes=max_total_bytes,
                                       max_items=64),
    )
    kept = {item.source for item in bundle.items}

    # Render (legacy order and bytes for kept sections) ---------------- #
    # Only ADR blocks historically carried a trailing blank line; every
    # other section renders header plus text, exactly as before.
    for (key, title, text), record in zip(sections, sources):
        if record["locator"] not in kept:
            continue
        parts.append(section_header(title))
        parts.append(text)

    omitted = sorted({record["locator"] for record in sources
                      if record["locator"] not in kept})
    if omitted:
        parts.append(section_header("OMITTED OVER BUDGET  (planner)"))
        for locator in omitted:
            parts.append(f"_— `{locator}` (over total budget)_")

    return "\n".join(parts) + "\n"


def _within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble AI context for a source file into a single document."
    )
    parser.add_argument("source_file", help="Path to the source file")
    parser.add_argument("--output", "-o", help="Write to file instead of stdout")
    parser.add_argument("--no-memory", action="store_true",
                        help="Skip Claude Code MEMORY.md excerpt")
    parser.add_argument("--max-adr-lines", type=int, default=60,
                        help="Max lines per ADR to include (default: 60)")
    parser.add_argument("--memory-lines", type=int, default=50,
                        help="Lines of MEMORY.md to include (default: 50)")
    parser.add_argument("--max-bytes", type=int, default=262144,
                        help="Total budget enforced by the ContextPlanner")
    args = parser.parse_args()

    try:
        text = assemble(
            Path(args.source_file),
            include_memory=not args.no_memory,
            max_adr_lines=args.max_adr_lines,
            memory_lines=args.memory_lines,
            max_total_bytes=args.max_bytes,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        from ainative.knowledge.errors import KnowledgeError
        if isinstance(e, KnowledgeError):
            print(f"Error: {e}", file=sys.stderr)
            return 1
        raise

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Context written to: {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
