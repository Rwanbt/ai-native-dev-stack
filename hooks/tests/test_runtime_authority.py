"""Adversarial tests for hooks/lib/runtime_authority.js.

MV-11 refactors privileged hooks (session-start-memory, session-end-save) to
receive only an opaque RuntimeContextHandle instead of reading
MULTIVAULT_SECURITY_DOMAIN_ID / OBSIDIAN_API_KEY from process.env directly.
These tests exercise the authority itself — the boundary that makes that
refusal enforceable — rather than the hooks' external JSON contract (already
covered, unchanged, by test_hooks_v4.py).

Covers:
  * correct caller + its own handle resolves the sensitive material
  * wrong caller identity on an otherwise-valid handle is denied
  * a handle minted by a different RuntimeAuthority instance is denied
  * issueHandle refuses to mint without a caller identity
  * the handle itself never carries the API key, in any representation
  * revocation makes a previously valid handle resolve to null afterward
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

STACK = Path(__file__).resolve().parents[2]


def _node_binary() -> str:
    found = shutil.which("node")
    if found:
        return found
    raise unittest.SkipTest("node not available")


def _run(snippet: str) -> subprocess.CompletedProcess:
    """Run a Node snippet from the stack root, module path resolved relative to it."""
    return subprocess.run(
        [_node_binary(), "-e", snippet],
        cwd=str(STACK), capture_output=True, text=True, timeout=30,
    )


class RuntimeAuthorityTests(unittest.TestCase):
    def test_correct_caller_resolves_sensitive_material(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const handle = authority.issueHandle('session-start-memory');
            const state = authority.resolve(handle, 'session-start-memory');
            assert.strictEqual(state.securityDomainId, 'domain-a');
            assert.strictEqual(state.apiKey, 'secret-key');
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_wrong_caller_identity_is_denied(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const handle = authority.issueHandle('session-start-memory');
            const state = authority.resolve(handle, 'session-end-save');
            assert.strictEqual(state, null);
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_handle_from_a_different_authority_is_denied(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authorityA = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const authorityB = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const handleFromA = authorityA.issueHandle('session-start-memory');
            const state = authorityB.resolve(handleFromA, 'session-start-memory');
            assert.strictEqual(state, null);
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_issue_handle_refuses_without_caller_identity(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            assert.strictEqual(authority.issueHandle(''), null);
            assert.strictEqual(authority.issueHandle(undefined), null);
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_handle_never_carries_the_api_key(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'super-secret' });
            const handle = authority.issueHandle('session-start-memory');
            assert.ok(!Object.keys(handle).includes('apiKey'));
            assert.ok(!JSON.stringify(handle).includes('super-secret'));
            assert.strictEqual(String(handle), '<redacted>');
            assert.strictEqual(JSON.stringify({ h: handle }), '{"h":"<redacted>"}');
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_revoked_handle_resolves_to_null(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const handle = authority.issueHandle('session-start-memory');
            assert.notStrictEqual(authority.resolve(handle, 'session-start-memory'), null);
            authority.revoke(handle);
            assert.strictEqual(authority.resolve(handle, 'session-start-memory'), null);
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_handle_carries_at_least_128_bits_of_csprng_entropy(self) -> None:
        # ADR-0013 section 3 requires the handle to carry >=128 bits of CSPRNG
        # entropy. This module uses a 256-bit secret; two independently issued
        # handles must not collide and must not be derivable from each other.
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const a = authority.issueHandle('session-start-memory');
            const b = authority.issueHandle('session-start-memory');
            assert.notStrictEqual(a._secret, b._secret);
            // base64url of 32 bytes is 43 chars (no padding) -> >=256 bits of material.
            assert.ok(a._secret.length >= 40, `secret too short: ${a._secret.length} chars`);
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_secret_is_not_enumerable_or_own_property_visible(self) -> None:
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const handle = authority.issueHandle('session-start-memory');
            assert.ok(!Object.keys(handle).includes('_secret'));
            assert.ok(!Object.prototype.propertyIsEnumerable.call(handle, '_secret'));
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_forged_handle_with_guessed_field_name_is_denied(self) -> None:
        # A plain object that copies the two visible fields but cannot know
        # the CSPRNG secret must still be denied.
        result = _run("""
            const assert = require('assert');
            const { RuntimeAuthority } = require('./hooks/lib/runtime_authority');
            const authority = new RuntimeAuthority('domain-a', { apiKey: 'secret-key' });
            const real = authority.issueHandle('session-start-memory');
            const forged = {
                authorityInstanceId: real.authorityInstanceId,
                securityDomainId: real.securityDomainId,
                _secret: 'guessed-value',
            };
            assert.strictEqual(authority.resolve(forged, 'session-start-memory'), null);
        """)
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
