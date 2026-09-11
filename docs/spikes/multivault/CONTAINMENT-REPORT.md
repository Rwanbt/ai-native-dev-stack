# MV-00.6 — Windows containment report

## Executed evidence

```text
python scripts/mv00/containment_probe.py --output docs/spikes/multivault/CONTAINMENT-REPORT.json
```

Executed on this machine (win32, Python 3.13, Git Bash environment).

## Result

```text
session_containment (Windows primitive) = VERIFIED
kill_on_close = true
detached_descendant_killed = true
breakaway_denied = true (winerror 5 ACCESS_DENIED)
```

A Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and breakaway disabled
killed the workload including a `DETACHED_PROCESS` grandchild when every
supervisor handle was closed, and denied a `CREATE_BREAKAWAY_FROM_JOB` spawn.

This is the mechanism ADR-0014 section 13 requires for `session_containment =
VERIFIED` on Windows. It does **not** qualify any tuple: model-egress
observation, provider identity and harness autoload control remain UNKNOWN,
so sensitive admission stays DENY.

## Scope limits

Linux cgroup/fail-dead evidence and macOS primitives remain UNKNOWN; only the
Windows Job Object path is proven here.