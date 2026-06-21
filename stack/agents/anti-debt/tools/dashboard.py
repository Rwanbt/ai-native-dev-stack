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


def load_business_metrics(history_path: Path | None = None) -> dict:
    """Load business metrics from .debt-history.json if available."""
    if history_path is None:
        history_path = ROOT / ".debt-history.json"
    if not history_path.exists():
        return {}

    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    scans = history.get("scans", [])
    overrides = history.get("overrides", [])

    if not scans:
        return {}

    total_findings = sum(s.get("total_findings", 0) for s in scans)
    total_overrides = len(overrides)
    reject_overrides = sum(1 for o in overrides if o.get("action") == "reject_override")
    accept_overrides = sum(1 for o in overrides if o.get("action") in ("accept_override", "confirm"))

    fp_rate = round(reject_overrides / max(total_findings, 1), 4)
    precision = round(accept_overrides / max(accept_overrides + reject_overrides, 1), 4)

    total_regressed = sum(len(s.get("findings_regressed", [])) for s in scans)
    total_resolved = sum(len(s.get("findings_resolved", [])) for s in scans)
    total_new = sum(len(s.get("findings_new", [])) for s in scans)

    deltas = [s.get("debt_delta", 0) for s in scans if "debt_delta" in s]
    avg_velocity = round(sum(deltas) / max(len(deltas), 1), 2)

    by_category_overrides = defaultdict(lambda: {"accept": 0, "reject": 0})
    for o in overrides:
        cat = o.get("category", "unknown")
        if o.get("action") == "reject_override":
            by_category_overrides[cat]["reject"] += 1
        elif o.get("action") in ("accept_override", "confirm"):
            by_category_overrides[cat]["accept"] += 1

    category_precision = {}
    for cat, counts in by_category_overrides.items():
        total = counts["accept"] + counts["reject"]
        if total > 0:
            category_precision[cat] = round(counts["accept"] / total, 3)

    return {
        "total_scans": len(scans),
        "total_findings_all_time": total_findings,
        "total_overrides": total_overrides,
        "false_positive_rate": fp_rate,
        "effective_precision": precision,
        "findings_regressed": total_regressed,
        "findings_resolved": total_resolved,
        "findings_new": total_new,
        "avg_debt_velocity": avg_velocity,
        "precision_by_category": category_precision,
    }


def render_business_metrics_html(metrics: dict) -> str:
    """Render business metrics as an HTML section."""
    if not metrics:
        return "<p><em>No .debt-history.json found — business metrics unavailable.</em></p>"

    cat_rows = ""
    for cat, prec in sorted(metrics.get("precision_by_category", {}).items()):
        color = "#65a30d" if prec >= 0.8 else "#ca8a04" if prec >= 0.6 else "#dc2626"
        cat_rows += (
            f'<tr><td>{html.escape(cat)}</td>'
            f'<td><span style="color:{color};font-weight:bold">{prec:.1%}</span></td></tr>'
        )

    velocity = metrics.get("avg_debt_velocity", 0)
    vel_color = "#65a30d" if velocity <= 0 else "#dc2626"

    return f"""
<h2>Business Metrics</h2>
<div class="kpi-row">
  <div class="kpi"><div class="value">{metrics.get('false_positive_rate', 0):.1%}</div><div class="label">FP Rate</div></div>
  <div class="kpi"><div class="value">{metrics.get('effective_precision', 0):.1%}</div><div class="label">Precision</div></div>
  <div class="kpi"><div class="value" style="color:{vel_color}">{velocity:+.1f}</div><div class="label">Debt Velocity</div></div>
  <div class="kpi"><div class="value">{metrics.get('findings_resolved', 0)}</div><div class="label">Resolved</div></div>
  <div class="kpi"><div class="value">{metrics.get('findings_regressed', 0)}</div><div class="label">Regressed</div></div>
</div>
<div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2em; margin: 1em 0;">
  <div>
    <h3>Precision by category</h3>
    <table><thead><tr><th>Category</th><th>Precision</th></tr></thead>
    <tbody>{cat_rows if cat_rows else '<tr><td colspan="2">No override data yet</td></tr>'}</tbody></table>
  </div>
  <div>
    <h3>Scan history</h3>
    <ul>
      <li>Total scans: {metrics.get('total_scans', 0)}</li>
      <li>Total findings (all time): {metrics.get('total_findings_all_time', 0)}</li>
      <li>Total overrides: {metrics.get('total_overrides', 0)}</li>
      <li>New findings: {metrics.get('findings_new', 0)}</li>
    </ul>
  </div>
</div>"""


def main() -> int:
    import argparse as _ap
    parser = _ap.ArgumentParser(description="Anti-debt dashboard generator")
    parser.add_argument("db", nargs="?", type=Path, default=DEFAULT_DB, help="KG database path")
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_HTML, help="Output HTML path")
    parser.add_argument("--history", type=Path, default=None, help=".debt-history.json for business metrics")
    args = parser.parse_args()

    if not args.db.exists():
        print(json.dumps({"error": f"kg db not found: {args.db}. Run scan_periodic.py first."}))
        return 1
    stats = load_stats(args.db)
    metrics = load_business_metrics(args.history)
    html_content = render_html(stats)
    if metrics:
        html_content = html_content.replace(
            '<div class="footer">',
            render_business_metrics_html(metrics) + '\n<div class="footer">'
        )
    args.output.write_text(html_content, encoding="utf-8")
    print(f"Dashboard written to {args.output}")
    print(f"  Components: {len(stats['components'])}, Debts: {len(stats['debts'])}, Edges: {stats['total_edges']}")
    if metrics:
        print(f"  Business: precision={metrics['effective_precision']:.1%}, FP rate={metrics['false_positive_rate']:.1%}, velocity={metrics['avg_debt_velocity']:+.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
