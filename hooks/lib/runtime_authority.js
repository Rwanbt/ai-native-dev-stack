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
 *
 * Conformance to ADR-0013 section 3's RuntimeContextHandle properties:
 *   >= 128 bits CSPRNG entropy   yes (256-bit secret, crypto.randomBytes)
 *   opaque                        yes (redacted toString/toJSON; secret is a
 *                                  non-enumerable field, mirroring the
 *                                  Python side's field(repr=False))
 *   non-persistent                yes (in-memory only, never serialized)
 *   session-scoped                yes (lifetime of one RuntimeAuthority)
 *   security-domain-scoped        yes (checked in resolve())
 *   security-epoch-scoped         NOT IMPLEMENTED — SecurityEpoch (ADR-0013
 *                                  section 7.2) has no schema/implementation
 *                                  anywhere in this repo yet (MV-02 scope,
 *                                  not yet a merged PR); a handle here cannot
 *                                  be scoped to an epoch that does not exist.
 *                                  Revisit when MV-02 lands.
 *   authority-instance-scoped     yes (checked in resolve())
 *   caller-identity-scoped        yes (checked in resolve())
 *   revocable                     yes (revoke())
 */

const crypto = require('crypto');

// 32 bytes = 256 bits, comfortably above ADR-0013 section 3's >=128-bit floor.
const SECRET_BYTES = 32;

class RuntimeContextHandle {
  constructor(authorityInstanceId, securityDomainId, secret) {
    this.authorityInstanceId = authorityInstanceId;
    this.securityDomainId = securityDomainId;
    // Mirrors the Python side's field(repr=False, compare=False): present so
    // resolve() can look it up, but excluded from enumeration/serialization.
    Object.defineProperty(this, '_secret', {
      value: secret, enumerable: false, writable: false, configurable: false,
    });
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
    // Keyed by the CSPRNG secret, not the handle object reference: an
    // unguessable bearer token is the actual capability, matching ADR-0013
    // section 3's entropy requirement (and the Python side's design).
    this._issued = new Map();
  }

  /** Issue a handle bound to one caller identity. No identity, no handle. */
  issueHandle(callerIdentity) {
    if (!callerIdentity) return null;
    const secret = crypto.randomBytes(SECRET_BYTES).toString('base64url');
    const handle = new RuntimeContextHandle(this._authorityInstanceId, this._securityDomainId, secret);
    this._issued.set(secret, callerIdentity);
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
    const issuedTo = this._issued.get(handle._secret);
    if (issuedTo === undefined || issuedTo !== callerIdentity) return null;
    return { securityDomainId: this._securityDomainId, ...this._sensitiveMaterial };
  }

  /** Idempotent; revoking an unknown or already-revoked handle is a no-op. */
  revoke(handle) {
    if (handle) this._issued.delete(handle._secret);
  }
}

module.exports = { RuntimeAuthority, RuntimeContextHandle };
