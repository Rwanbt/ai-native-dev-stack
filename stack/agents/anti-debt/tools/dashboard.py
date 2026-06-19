#!/usr/bin/env python3
"""dashboard.py — Layer 7: Generate a self-contained HTML dashboard for the KG.

Reads the KG SQLite database and emits a single HTML file with:
- Project list (Components)
- Debt breakdown by severity / category
- Top 20 most-recent debts
- Calibration stats

Output: a static HTML page (no JS framework required, vanilla SVG/CSS).

Usage:
    python3 dashboard.py [path-to-kg.db] [output.html]
    # default: <repo>/kg/data/kg.db -> <repo>/tools/dashboard.html
"""
from __future__ import annotations
import html
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_DB = ROOT / "kg" / "data" / "kg.db"
DEFAULT_HTML = ROOT / "tools" / "dashboard.html"

SEVERITY_COLORS = {
    "critical": "#dc2626",  # red
    "high": "#ea580c",      # orange
    "medium": "#ca8a04",    # yellow
    "low": "#65a30d",       # lime
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_stats(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    stats = {}
    # Node counts
    cur.execute("SELECT type, COUNT(*) AS n FROM nodes GROUP BY type")
    stats["by_node_type"] = {row["type"]: row["n"] for row in cur.fetchall()}
    cur.execute("SELECT type, COUNT(*) AS n FROM edges GROUP BY type")
    stats["by_edge_type"] = {row["type"]: row["n"] for row in cur.fetchall()}
    cur.execute("SELECT COUNT(*) AS n FROM nodes")
    stats["total_nodes"] = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM edges")
    stats["total_edges"] = cur.fetchone()["n"]
    # Components
    cur.execute("SELECT id, name, metadata FROM nodes WHERE type='Component' ORDER BY name")
    stats["components"] = [dict(row) for row in cur.fetchall()]
    # Debts grouped by severity
    cur.execute("SELECT metadata, name FROM nodes WHERE type='Debt'")
    debts = []
    for row in cur.fetchall():
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        meta["name"] = row["name"]
        debts.append(meta)
    stats["debts"] = debts
    stats["by_severity"] = Counter(d.get("severity", "unknown") for d in debts)
    stats["by_category"] = Counter(d.get("category", "unknown") for d in debts)
    stats["top_files"] = Counter(d.get("file", "?") for d in debts).most_common(10)
    # Recent debts
    cur.execute("SELECT id, name, metadata FROM nodes WHERE type='Debt' "
                "ORDER BY json_extract(metadata, '$.first_seen') DESC LIMIT 20")
    stats["recent_debts"] = [dict(row) for row in cur.fetchall()]
    conn.close()
    return stats


def render_html(stats: dict) -> str:
    """Render the stats dict as a self-contained HTML page."""
    # Severity bars (SVG)
    sev_total = sum(stats["by_severity"].values()) or 1
    sev_svg_parts = []
    bar_y = 0
    bar_w_max = 400
    for sev in ("critical", "high", "medium", "low"):
        n = stats["by_severity"].get(sev, 0)
        w = int(bar_w_max * n / sev_total)
        if w == 0:
            continue
        sev_svg_parts.append(
            f'<rect x="0" y="{bar_y}" width="{w}" height="20" fill="{SEVERITY_COLORS[sev]}"/>'
            f'<text x="{w+5}" y="{bar_y+15}" font-family="monospace" font-size="12" fill="#222">'
            f'{sev}: {n}</text>'
        )
        bar_y += 28
    severity_svg = (
        '<svg width="600" height="' + str(max(bar_y, 30)) + '" xmlns="http://www.w3.org/2000/svg">'
        + "".join(sev_svg_parts) + "</svg>"
    )
    # Category pie
    cat_total = sum(stats["by_category"].values()) or 1
    cat_colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#6366f1"]
    cat_pie = []
    cum = 0
    for i, (cat, n) in enumerate(stats["by_category"].most_common(7)):
        start = cum / cat_total * 360
        cum += n
        end = cum / cat_total * 360
        if end - start >= 359.9:
            cat_pie.append(f'<circle cx="100" cy="100" r="80" fill="{cat_colors[i % len(cat_colors)]}"/>')
        else:
            # SVG arc path
            import math
            sa = math.radians(start - 90)
            ea = math.radians(end - 90)
            x1 = 100 + 80 * math.cos(sa)
            y1 = 100 + 80 * math.sin(sa)
            x2 = 100 + 80 * math.cos(ea)
            y2 = 100 + 80 * math.sin(ea)
            large = 1 if (end - start) > 180 else 0
            d = f"M 100 100 L {x1:.1f} {y1:.1f} A 80 80 0 {large} 1 {x2:.1f} {y2:.1f} Z"
            cat_pie.append(f'<path d="{d}" fill="{cat_colors[i % len(cat_colors)]}"/>')
    cat_legend = []
    for i, (cat, n) in enumerate(stats["by_category"].most_common(7)):
        cat_legend.append(
            f'<div><span style="display:inline-block;width:12px;height:12px;background:{cat_colors[i % len(cat_colors)]};margin-right:6px;"></span>'
            f'{html.escape(cat)}: {n}</div>'
        )
    cat_svg = (
        '<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">'
        + "".join(cat_pie) + "</svg>"
    )
    # Recent debts table
    recent_rows = []
    for d in stats["recent_debts"]:
        meta = json.loads(d.get("metadata", "{}")) if d.get("metadata") else {}
        sev = meta.get("severity", "?")
        color = SEVERITY_COLORS.get(sev, "#999")
        recent_rows.append(
            f'<tr><td><span style="color:{color};font-weight:bold">{html.escape(sev.upper())}</span></td>'
            f'<td>{html.escape(meta.get("category", "?"))}/{html.escape(meta.get("subcategory", "?"))}</td>'
            f'<td>{html.escape(d.get("name", "?")[:80])}</td>'
            f'<td><code>{html.escape(meta.get("file", "?"))}:{html.escape(str(meta.get("line", "?")))}</code></td>'
            f'<td>{html.escape(meta.get("first_seen", "?"))[:19]}</td></tr>'
        )
    recent_table = (
        '<table><thead><tr><th>Severity</th><th>Cat/Sub</th><th>Description</th><th>Location</th><th>First seen</th></tr></thead>'
        f'<tbody>{"".join(recent_rows)}</tbody></table>'
    )
    # Top files
    top_files_html = "<ul>" + "".join(
        f'<li><code>{html.escape(f)}</code> — {n} findings</li>' for f, n in stats["top_files"]
    ) + "</ul>"
    # Components list
    comps_html = "<ul>" + "".join(
        f'<li><b>{html.escape(c.get("name", "?"))}</b> '
        f'<code>{html.escape(json.loads(c.get("metadata", "{}")).get("path", "?"))}</code></li>'
        for c in stats["components"]
    ) + "</ul>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Anti-Debt Dashboard</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #222; }}
  h1, h2 {{ color: #1e3a8a; }}
  .kpi-row {{ display: flex; gap: 1.5em; margin: 1.5em 0; }}
  .kpi {{ background: #f3f4f6; padding: 1em 1.5em; border-radius: 8px; min-width: 120px; }}
  .kpi .value {{ font-size: 2em; font-weight: bold; color: #1e3a8a; }}
  .kpi .label {{ color: #6b7280; font-size: 0.9em; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
  th, td {{ padding: 0.5em 0.7em; text-align: left; border-bottom: 1px solid #e5e7eb; font-size: 0.9em; }}
  th {{ background: #f9fafb; }}
  code {{ background: #f3f4f6; padding: 0 0.3em; border-radius: 3px; font-size: 0.9em; }}
  .cat-legend {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.3em; font-size: 0.9em; }}
  .footer {{ color: #6b7280; font-size: 0.85em; margin-top: 3em; border-top: 1px solid #e5e7eb; padding-top: 1em; }}
</style>
</head>
<body>
<h1>Anti-Debt Dashboard</h1>
<p>Generated {_now()} from <code>{html.escape(str(DEFAULT_DB))}</code></p>

<div class="kpi-row">
  <div class="kpi"><div class="value">{stats["total_nodes"]}</div><div class="label">Nodes</div></div>
  <div class="kpi"><div class="value">{stats["total_edges"]}</div><div class="label">Edges</div></div>
  <div class="kpi"><div class="value">{len(stats["components"])}</div><div class="label">Components</div></div>
  <div class="kpi"><div class="value">{len(stats["debts"])}</div><div class="label">Debts</div></div>
  <div class="kpi"><div class="value">{stats["by_severity"].get("critical", 0)}</div><div class="label">Critical</div></div>
</div>

<h2>Severity distribution</h2>
{severity_svg}

<h2>Category distribution</h2>
<div style="display:flex; align-items:center; gap:2em;">
  {cat_svg}
  <div class="cat-legend">{"".join(cat_legend)}</div>
</div>

<h2>Top files with debt</h2>
{top_files_html}

<h2>Components (projects scanned)</h2>
{comps_html}

<h2>Recent debts (latest 20)</h2>
{recent_table}

<div class="footer">
  Anti-debt agent v1.2 — generated by tools/dashboard.py
</div>
</body>
</html>"""


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_HTML
    if not db_path.exists():
        print(json.dumps({"error": f"kg db not found: {db_path}. Run scan_periodic.py first."}))
        return 1
    stats = load_stats(db_path)
    out_path.write_text(render_html(stats), encoding="utf-8")
    print(f"Dashboard written to {out_path}")
    print(f"  Components: {len(stats['components'])}, Debts: {len(stats['debts'])}, Edges: {stats['total_edges']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
