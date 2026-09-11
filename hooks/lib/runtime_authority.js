/** In-process, fail-closed runtime capability authority for privileged hooks.
 *
 * See ADR-0013, ADR-0014, ADR-0015, ADR-0016. Mirrors
 * ainative/multivault/runtime_authority.py's shape for the JS side. This is
 * a same-process, single-runtime primitive — not a process-isolation or IPC
 * claim. ADR-0015 section 2's authenticated IPC primitives (named pipe /
 * Unix socket) remain pending MV-00/MV-01 platform evidence and are out of
 * scope here. What this module does guarantee: privileged hook logic never
 * reads process.env directly for security-critical material — it only ever
 * receives an opaque RuntimeContextHandle and must resolve it through the
 * authority that issued it, as the exact caller identity it was issued to.
 */

const crypto = require('crypto');

class RuntimeContextHandle {
  constructor(authorityInstanceId, securityDomainId) {
    this.authorityInstanceId = authorityInstanceId;
    this.securityDomainId = securityDomainId;
    Object.freeze(this);
  }

  toString() {
    return '<redacted>';
  }

  toJSON() {
    return '<redacted>';
  }
}

class RuntimeAuthority {
  /**
   * @param {string} securityDomainId - may be empty; validity is judged by the
   *   consumer (e.g. createObsidianClient), not by this authority.
   * @param {{apiKey: string, endpoints: (string[]|undefined), timeoutMs: number}} sensitiveMaterial
   */
  constructor(securityDomainId, sensitiveMaterial) {
    this._authorityInstanceId = crypto.randomUUID();
    this._securityDomainId = typeof securityDomainId === 'string' ? securityDomainId : '';
    this._sensitiveMaterial = Object.freeze({ ...sensitiveMaterial });
    // WeakMap keyed by the handle object itself: resolution requires the
    // literal issued reference, not a copy or guess of any field on it.
    this._issuedTo = new WeakMap();
  }

  /** Issue a handle bound to one caller identity. No identity, no handle. */
  issueHandle(callerIdentity) {
    if (!callerIdentity) return null;
    const handle = new RuntimeContextHandle(this._authorityInstanceId, this._securityDomainId);
    this._issuedTo.set(handle, callerIdentity);
    return handle;
  }

  /**
   * Return the sensitive material only for this exact authority instance,
   * this exact issued handle, and the caller identity it was issued to.
   * Any mismatch fails closed (returns null) — never a partial result.
   */
  resolve(handle, callerIdentity) {
    if (!handle || !callerIdentity) return null;
    if (handle.authorityInstanceId !== this._authorityInstanceId) return null;
    if (handle.securityDomainId !== this._securityDomainId) return null;
    const issuedTo = this._issuedTo.get(handle);
    if (issuedTo === undefined || issuedTo !== callerIdentity) return null;
    return { securityDomainId: this._securityDomainId, ...this._sensitiveMaterial };
  }

  /** Idempotent; revoking an unknown or already-revoked handle is a no-op. */
  revoke(handle) {
    if (handle) this._issuedTo.delete(handle);
  }
}

module.exports = { RuntimeAuthority, RuntimeContextHandle };
