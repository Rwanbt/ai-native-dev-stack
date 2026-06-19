#!/usr/bin/env python3
"""
permission-readonly-env.py — PermissionRequest: auto-allow read-only commands with env var prefix.

Example: RUST_LOG=debug cat file.txt → stripped = "cat file.txt" → allow

Compatible: Claude Code, Codex (PermissionRequest), MiniMax Code.
Python stdlib uniquement.

Usage: python3 run.py
stdin: payload JSON de l'agent (PermissionRequest event)
stdout: JSON { hookSpecificOutput: ... } ou vide (silence = pas d'autorisation automatique)
"""
import json
import sys

READONLY = {
    'ls', 'll', 'cat', 'head', 'tail', 'grep', 'rg',
    'wc', 'diff', 'echo', 'pwd', 'which', 'file',
    'stat', 'type', 'dir', 'find', 'awk', 'cd',
}


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    tool_input = (
        payload.get('tool_input')
        or payload.get('input', {}).get('tool_input')
        or {}
    )
    cmd = tool_input.get('command', '')
    parts = cmd.split()

    # Skip leading ENV_VAR=value tokens
    n = 0
    for p in parts:
        if '=' in p:
            key = p.split('=', 1)[0]
            if key and key == key.upper() and key.replace('_', '').isalpha():
                n += 1
                continue
        break

    first_word = parts[n] if n < len(parts) else ''

    if first_word in READONLY:
        print(json.dumps({
            'hookSpecificOutput': {
                'hookEventName': 'PermissionRequest',
                'permissionDecision': 'allow',
                'permissionDecisionReason': f"read-only command '{first_word}' with env var prefix",
            }
        }))


if __name__ == '__main__':
    main()
