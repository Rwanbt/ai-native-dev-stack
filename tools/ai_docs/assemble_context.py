#!/usr/bin/env python3
"""
assemble_context.py — AI context assembler for any project module.

Given a source file path, assembles a single focused AI briefing document:
  - Module AI_CONTEXT.md           (always — primary reference)
  - AI_SUMMARY.md                  (always, if exists — public API snapshot)
  - docs/REALTIME_RULES.md         (if module has RT thread constraints)
  - Referenced ADRs                (from ## See also section, up to N lines each)
  - docs/KNOWN_FAILURE_PATTERNS.md (always, if exists — bounded at 200 lines)
  - graphify dependency path       (if binary available)
  - Claude Code MEMORY.md          (first 50 lines — cross-session context)

Usage:
    python tools/ai_docs/assemble_context.py <source_file>
    python tools/ai_docs/assemble_context.py <source_file> --output context.md
    python tools/ai_docs/assemble_context.py <source_file> --no-memory

Works for any project structure — no hardcoded paths.
The AI_CONTEXT.md acts as the module marker (same as generate_ai_summary.py).

Exit codes:
    0 — success (context written)
    1 — source_file not found or no module found in ancestor tree
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOP_DIRS = {".git", "node_modules", "vendor", "__pycache__"}

# Keywords in AI_CONTEXT.md that indicate real-time thread constraints
RT_KEYWORDS = {
    "audio thread", "rt thread", "audio callback", "real-time",
    "processaudio", "process_block", "zero alloc", "zero allocation",
    "no allocation", "lock-free", "rt_safe", "audio_thread_only",
    "real time", "no mutex", "no blocking",
}

SECTION_WIDTH = 72


# ---------------------------------------------------------------------------
# Module discovery (mirrors update_on_edit.py logic)
# ---------------------------------------------------------------------------

def find_project_root(start: Path) -> Path:
    """Walk up to find the git root; fall back to start."""
    p = start.resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return start.resolve()


def find_module(file_path: Path) -> Path | None:
    """Walk up from file_path to find the nearest directory with AI_CONTEXT.md."""
    current = file_path.resolve().parent
    visited: set[Path] = set()
    while current not in visited:
        visited.add(current)
        if (current / "AI_CONTEXT.md").exists():
            return current
        if (current / ".git").exists() or current == current.parent:
            return None
        if current.name in STOP_DIRS:
            return None
        current = current.parent
    return None


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
    """Locate the graphify binary from PATH or common install locations."""
    import shutil
    if g := shutil.which("graphify"):
        return g
    candidates = [
        "/d/App/graphify/bin/graphify",
        str(Path.home() / ".local" / "bin" / "graphify"),
        "/usr/local/bin/graphify",
        str(Path.home() / "bin" / "graphify"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def run_graphify_path(graphify_bin: str, root: Path, file_path: Path) -> str | None:
    """Run `graphify path <file>` and return the output."""
    try:
        result = subprocess.run(
            [graphify_bin, "path", str(file_path)],
            capture_output=True, text=True, timeout=10, cwd=str(root),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


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

    # Fallback: pick the most-recently-modified MEMORY.md
    found = sorted(
        projects_dir.rglob("MEMORY.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return found[0] if found else None


def section_header(title: str) -> str:
    bar = "─" * SECTION_WIDTH
    return f"\n{bar}\n## {title}\n{bar}\n"


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

def assemble(
    source_file: Path,
    include_memory: bool = True,
    max_adr_lines: int = 60,
    memory_lines: int = 50,
    max_kfp_lines: int = 200,
) -> str:
    """Assemble the context document for source_file."""

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

    # ------------------------------------------------------------------ #
    # AI_CONTEXT.md (always)
    # ------------------------------------------------------------------ #
    ctx_path = module_dir / "AI_CONTEXT.md"
    ctx_text = ctx_path.read_text(encoding="utf-8", errors="ignore")
    parts.append(section_header(f"MODULE CONTEXT — {module_name}"))
    parts.append(ctx_text.strip())

    # ------------------------------------------------------------------ #
    # AI_SUMMARY.md (if exists)
    # ------------------------------------------------------------------ #
    summary_path = module_dir / "AI_SUMMARY.md"
    if summary_path.exists():
        summary_text = summary_path.read_text(encoding="utf-8", errors="ignore")
        parts.append(section_header("PUBLIC API SNAPSHOT  (auto-generated)"))
        parts.append(summary_text.strip())

    # ------------------------------------------------------------------ #
    # REALTIME_RULES.md (if RT constraints detected)
    # ------------------------------------------------------------------ #
    if has_rt_constraints(ctx_text):
        rt_path = root / "docs" / "REALTIME_RULES.md"
        if rt_path.exists():
            rt_text = rt_path.read_text(encoding="utf-8", errors="ignore")
            parts.append(section_header("REAL-TIME RULES  (injected — RT constraints detected)"))
            parts.append(rt_text.strip())
        else:
            parts.append(section_header("REAL-TIME RULES"))
            parts.append(
                "_`docs/REALTIME_RULES.md` not found._  \n"
                "_Create it to capture zero-alloc / zero-blocking constraints._"
            )

    # ------------------------------------------------------------------ #
    # Referenced ADRs
    # ------------------------------------------------------------------ #
    adr_refs = extract_adr_refs(ctx_text)
    adr_dir = root / "docs" / "adr"
    if adr_refs and adr_dir.exists():
        parts.append(section_header("REFERENCED ADRs"))
        for adr_id in adr_refs:
            num = adr_id.replace("ADR-", "")
            matches = list(adr_dir.glob(f"{num}-*.md")) or list(adr_dir.glob(f"ADR-{num}-*.md"))
            if matches:
                adr_text = matches[0].read_text(encoding="utf-8", errors="ignore")
                adr_lines = adr_text.splitlines()
                excerpt = "\n".join(adr_lines[:max_adr_lines])
                parts.append(f"### {adr_id}")
                parts.append(excerpt)
                if len(adr_lines) > max_adr_lines:
                    parts.append(
                        f"\n_... ({len(adr_lines) - max_adr_lines} more lines "
                        f"— see `{matches[0].relative_to(root)}`)_"
                    )
                parts.append("")
            else:
                parts.append(f"### {adr_id} — _not found in `docs/adr/`_\n")

    # ------------------------------------------------------------------ #
    # KNOWN_FAILURE_PATTERNS.md (if exists)
    # ------------------------------------------------------------------ #
    kfp_path = root / "docs" / "KNOWN_FAILURE_PATTERNS.md"
    if kfp_path.exists():
        kfp_lines = kfp_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        excerpt = "\n".join(kfp_lines[:max_kfp_lines])
        parts.append(section_header("KNOWN FAILURE PATTERNS"))
        parts.append(excerpt)
        if len(kfp_lines) > max_kfp_lines:
            parts.append(
                f"\n_... ({len(kfp_lines) - max_kfp_lines} more lines "
                f"— see `docs/KNOWN_FAILURE_PATTERNS.md`)_"
            )

    # ------------------------------------------------------------------ #
    # graphify dependency path
    # ------------------------------------------------------------------ #
    graphify_bin = find_graphify_bin()
    if graphify_bin:
        gfx_result = run_graphify_path(graphify_bin, root, source_file)
        if gfx_result:
            parts.append(section_header("DEPENDENCY PATH  (graphify)"))
            parts.append(f"```\n{gfx_result}\n```")

    # ------------------------------------------------------------------ #
    # Claude Code memory excerpt
    # ------------------------------------------------------------------ #
    if include_memory:
        mem_path = find_claude_memory(root)
        if mem_path and mem_path.exists():
            mem_lines = mem_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            excerpt = "\n".join(mem_lines[:memory_lines])
            parts.append(section_header(f"PROJECT MEMORY  (first {memory_lines} lines)"))
            parts.append(excerpt)
            if len(mem_lines) > memory_lines:
                parts.append(
                    f"\n_... ({len(mem_lines) - memory_lines} more lines — see `{mem_path}`)_"
                )

    return "\n".join(parts) + "\n"


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
    args = parser.parse_args()

    try:
        text = assemble(
            Path(args.source_file),
            include_memory=not args.no_memory,
            max_adr_lines=args.max_adr_lines,
            memory_lines=args.memory_lines,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Context written to: {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
