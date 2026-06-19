#!/usr/bin/env python3
"""
pretool-graphify-inject.py — version Python pour agents ne supportant pas Node.js.
Mêmes fonctionnalités que run.js. Lit stdin, injecte si search tool + graph existe.
"""
import json
import os
import re
import sys

SEARCH_TOOLS = ['grep', 'rg', 'ripgrep', 'find', 'fd', 'ack', 'ag']


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_input = payload.get('tool_input') or payload.get('input', {}).get('tool_input') or {}
    command = tool_input.get('command', '')
    cwd = payload.get('cwd') or os.getcwd()

    lower = command.lower()
    is_search = any(re.search(rf'(^|\s|\b){re.escape(tool)}(\s|$)', lower) for tool in SEARCH_TOOLS)
    if not is_search:
        return

    graph_path = os.path.join(cwd, 'graphify-out', 'graph.json')
    if not os.path.exists(graph_path):
        return

    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'additionalContext': 'graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files.',
        },
    }))


if __name__ == '__main__':
    main()
