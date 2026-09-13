# Security Policy

## Supported versions

Only the latest release of the AI Native Dev Stack is supported. Security
fixes are prepared for the current major-minor line and published as a patch
release; older releases are not patched.

| Version | Supported |
|---|---|
| latest release (currently 2.2.x) | yes |
| any earlier release | no |

## Reporting a vulnerability

Use GitHub private vulnerability reporting on this repository:
**Security** tab, **Report a vulnerability**. That channel keeps the report
private until a fix is published.

Do not open a public issue for a suspected vulnerability. Do not include
secret values, live credentials, tokens or personal data in a public issue,
a pull request description, or a CI log: reports are public the moment they
are filed. Share only what is necessary to reproduce, and reference the
affected file and version.

If private reporting is unavailable to you, open a minimal public issue saying
only that you have a security report and would like a private channel; leave
every technical detail out of it.

## What to expect

- Acknowledgement on a best-effort basis. This is a single-maintainer project;
  no response-time SLA is promised.
- Confirmed findings are fixed on `dev`, released as a patch on `main`, and
  credited in the release notes unless you ask otherwise.
- If a report is out of scope, the reasoning is stated in the same channel.

## Security boundaries and threat model

Read these before reporting; several properties are deliberate and documented:

- `docs/DISTRIBUTION-LIFECYCLE.md` and `docs/adr/0009` - what the lifecycle
  defends against, and what SHA-256 integrity does and does not prove. Release
  artifacts are integrity-verified, not cryptographically authenticated by a
  maintainer signature (unless issue #24 changes that).
- `stack/agents/anti-debt/docs/security-boundaries.md` - the anti-debt agent
  sandboxing and egress boundaries.
- `docs/knowledge/KNOWLEDGE-CONVERGENCE-MATRIX.md` - Knowledge/Auto-Memory
  guarantees, including what is intentionally not shipped (canonical
  auto-promotion, K5 = STOP).
- `docs/VERIFIED-WORK-PLANE.md` - the Verified Work Plane trust model.

Out of scope: findings that amount to "the documentation says the trust model
is limited" where it is; vulnerabilities requiring a compromised maintainer
account or a compromised release source (that is the documented residual risk).