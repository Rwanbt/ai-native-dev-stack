# Universal Engineering Rules
<!-- stack-version: 1.0.0 -->
<!-- Cross-tool: Claude Code (@AGENTS.md in CLAUDE.md), Cursor (reads AGENTS.md natively at root + nested dirs), Codex (auto-loaded AGENTS.md) -->
<!-- Keep this file at the project root. Customize per project as needed. -->
<!-- Canonical source — reference this file (@AGENTS.md), do not copy it. Updates flow via `git pull` + /stack-upgrade. See UPDATING.md. -->
<!-- Source: https://github.com/Rwanbt/ai-native-dev-stack -->

## Primary bias to correct

Working code is not clean code. Small pieces are not simple. Familiar patterns are not correct patterns.
Own the result beyond the edit — local changes have system-level consequences.

---

## Code structure

- **File size**: flag >500 LOC new file; propose extraction >800 LOC existing; mandatory refactor >1500 LOC
- **Function size**: ≤50 LOC target; >100 alert; >200 blocking — extract sub-functions, never keep adding
- **Cyclomatic complexity**: ≤10 target; >15 alert; >25 blocking
- **Single responsibility**: before adding to a file — "does this belong here?", "am I adding a second responsibility?", "is this helper reusable elsewhere?"
- **No global state**: no `static` globals, no singletons (`getInstance()`). Prefer injection via parameter or owner member. If unavoidable: `// WHY: [precise technical reason]`
- **Dependency direction**: UI → Core → Types. Never reverse. Use forward declarations or interfaces to break upward deps.
- **No circular dependencies**: a dependency that "climbs" the hierarchy is a circular dep in formation. Resolve by forward declaration or interface extraction.

---

## Error handling

- Never swallow errors silently: no empty `catch {}`, no ignored `Result`, no `_ =`
- **Rust**: `?`, `map_err()`, or `anyhow::bail!` — `unwrap()` only with `// SAFETY: [proven reason]`
- **C++**: `std::optional`/`std::expected` over exceptions in hot paths; never `catch(...) {}`
- At system boundaries (I/O, HTTP, user input, external parsing): always handle explicitly
- Internal trusted boundaries may `assert`/`debug_assert` in debug, panic in Rust

---

## Naming & comments

- **Language**: English everywhere — code, comments, commits, PR descriptions. One language per repo.
- **Names**: explicit over short — `processAudioFrame()` > `process()`, `userEmailAddress` > `email`
- **No cryptic abbreviations**: `idx→index`, `cnt→count`, `mgr→manager` (exceptions: `ptr`, `id`, `num`)
- **Comments**: WHY only — hidden constraint, subtle invariant, workaround for a specific bug. Never describe WHAT the code does.
- **Dead code**: delete immediately, never comment out. `git log -S "functionName"` recovers any deleted code.

---

## Constants & resources

- No magic numbers or strings appearing more than once → named constant
- **Rust**: `const` at module level or in `impl` block
- **C++**: `constexpr` or `static constexpr`; never bare `#define` for typed values
- **C++ resources**: no naked `new`/`delete` — `std::unique_ptr`, `std::make_unique`, RAII always. Every acquired resource is released via RAII.

---

## Git & collaboration

- Commit format: `<type>(<scope>): <description>` — types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`
- PR size: ≤400 LOC changed. Beyond: split into sequential autonomous PRs, each independently buildable
- Squash merge preferred: one clean commit per PR in main history; never merge-commit noise in `main`
- **Pre-commit** (before every non-trivial commit):
  - Rust: `cargo clippy --all-targets -- -D warnings && cargo test`
  - C++: `cmake --build build/ --config Release`
  - TS/JS: `tsc --noEmit && eslint src/`

---

## Engineering discipline
<!-- Distilled from The Pragmatic Programmer — Hunt & Thomas -->

- One authoritative source per piece of system knowledge (DRY). When knowledge is copied, choose one owner and derive or trace the rest.
- Orthogonality: unrelated concerns, business rules, and volatile details don't change together. When changes fan out widely, restore ownership.
- Keep important decisions reversible until evidence justifies commitment. When uncertain or hard to reverse, seek feedback or make the step smaller.
- Automate repeatable work; keep automation versioned.
- Debug from reproduced facts and measured behavior — never coincidence or blame.
- Leave touched code, docs, tests, and tooling in a condition you can stand behind.

---

## Clean code discipline
<!-- Distilled from Clean Code — Robert C. Martin -->

- Preserve behavior, write for the next reader, leave touched code cleaner within scope.
- Precise names with one term per concept; split boolean flags and mixed abstraction levels out of functions.
- Separate commands from queries. No hidden side effects.
- Comments only for rationale or contracts — never to explain confusing code (simplify the code instead).
- When touching code: remove the smell most likely to make the next change risky or unclear.

---

## Refactoring discipline
<!-- Distilled from Refactoring — Martin Fowler -->

- Preserve observable behavior; isolate feature changes, migrations, and cleanup into separate steps.
- Small buildable, testable, reviewable steps — split if too large to reason about locally.
- Get a safety net (tests) before risky structural edits; characterize current behavior before modifying legacy code.
- Refactor the smell blocking the current change, not every smell nearby.
- When the same edit appears for a third time: centralize ownership instead of copying again.
- Stop when the change is easy, the code is clearer, and further cleanup would be speculative.

---

## Design complexity
<!-- Distilled from A Philosophy of Software Design — John Ousterhout -->

- Optimize for lower cognitive load — not shorter files, familiar patterns, or clever compactness.
- Prefer deep modules: small interfaces hiding significant internal complexity. Reject wrappers that don't hide real complexity.
- Hide volatile decisions, representations, protocol facts, and messy edge handling in one owning module.
- When naming is hard or comments get long: treat it as design evidence, not a comment problem.
- When one change spreads widely: look for duplicated knowledge, hidden dependencies, or the wrong owner.
- Add complexity for performance or patterns only when evidence justifies it.

---

## Codebase analysis strategy

Before any analysis, audit, or review, estimate scope and classify intent.

**Estimate scope** (run this first):
```bash
git ls-files | grep -E "\.(py|rs|cpp|c|h|hpp|ts|js|go|sh)$" | xargs wc -c 2>/dev/null | tail -1
# → divide by 4 = estimated tokens (±20% heuristic)
git ls-files | grep -E "\.(py|rs|cpp|c|h|hpp|ts|js|go|sh)$" | wc -l
# → file count
```

**Classify intent**:

| Signal in the request | Mode | Strategy |
|---|---|---|
| "Where is X?", "find Y" | **Lookup** | Explore sub-agent |
| "How does X work?" | **Understanding** | Sub-agent + targeted read |
| "Review", "analyse the architecture" | **Review** | Central synthesis + list of read/unread files |
| "Exhaustive", "nothing missing", "audit" | **Audit** | Manifest-driven direct read + verified coverage |

**Secondary complexity signal**: if `tokens < 50k` but `files > 100` → prefer a clarification round even for Audit (many small files = complex dependency graph).

**Strategy by size**:
```
< 50 000 tokens  → read ALL files directly in the main context (100% coverage guaranteed)
50k – 150k       → deterministic cartography (ctags/AST) + layered reads
> 150 000 tokens → multi-phase workflow (cartography → parallel reads → synthesis)
```

**Verified coverage (mandatory in Audit mode)**:
1. Before starting: generate the complete file list — `git ls-files | grep -E "..."` — this is the execution contract
2. Declare legitimate exclusions upfront by path (`generated/`, `vendor/`, `build/`)
3. Read every remaining file in sequence
4. Report at the end:

```
Coverage — Audit [repo]
Files: 11 total | Excluded (generated): 0 | Excluded (vendor): 0 | To read: 11
Read: 11/11 (100%) ✅

Unread business-logic files: none
Central unread modules (>5 incoming imports): none
```

**Confidence rule derived from coverage**:
- `≥ 80%` → conclusions without qualifier
- `60–80%` → prefix each conclusion with "Partial analysis:"
- `< 60%` → prefix with "⚠️ Provisional — insufficient coverage"

**Note**: `ctags`/AST tools give structural exhaustiveness (all symbols), NOT behavioral exhaustiveness (same signature ≠ same logic). Direct read remains necessary for behavioral audits. Never use a sub-agent for Audit mode.

---

### This project — ai-native-dev-stack

Measured 2026-06-13 via `git ls-files`:

| Scope | Tokens (÷4) | Files | Strategy |
|---|---|---|---|
| Full project (source) | ~22 000 | 11 | **Direct read always** — fits in context in one pass |

The project is small enough that direct read is always the right choice regardless of mode. No clarification round needed unless the request is genuinely ambiguous.

---

## Senior engineering reflexes

The rules above are the always-on core. The reflexes below are the full senior playbook — apply them proactively, without being asked, scaled to the project's language and risk. They are the canonical source: per-tool configs (`CLAUDE.md`, MiniMax `agent.md`, `.cursorrules`) should reference this file rather than re-state these rules.

### Documentation & decisions

- **ADR** (Architecture Decision Record) — documents a decision *already made*. Retrospective, in `docs/adr/NNNN-short-title.md`: Context · Decision · Rejected alternatives · Consequences. Triggers: new central pattern, lib choice, thread-model constraint, public-API change.
- **RFC** (Request for Comments) — requests feedback *before* a major change. Prospective, in `docs/rfcs/`: Motivation · Detailed proposal · Alternatives · Open questions · Review deadline.
- **`// See ADR-NNNN`** in code — when a block implements a documented decision, link it so a reader reaches the "why" without searching the docs.
- **Documentation proportional to size**: >10 source files → `CLAUDE.md`; >3,000 LOC → `ARCHITECTURE.md` (thread model, data flow, ownership, red zones); >5,000 LOC → `CONTRIBUTING.md` (conventions, how to add a module, PR checklist).
- **Domain glossary** — for any jargon-dense domain (audio, finance, medical, network, games), create `docs/glossary.md` defining terms *operationally* (precise definition + link to the implementing module + concrete in-project example). A dev without domain background introduces subtle bugs by misreading a technical term.
- **Data format versioning & migrations** — every persisted format carries an explicit version + one migration function per delta (`upgradeProjectV6toV7()`). Without migrations a refactor that changes the format makes all old files unreadable.
- **CHANGELOG.md** — on any project with releases, maintain it from Conventional Commits: `## [VERSION] - YYYY-MM-DD` with `### Added/Fixed/Changed/Removed`.

### Testing

- **Propose tests at service creation** — when a stateless service / pure business logic is created or extracted, proactively offer a test (don't wait to be asked). Stateless free functions are the highest-priority, easiest wins.
- **Test naming**: `Component_Scenario_ExpectedBehavior` (e.g. `ProjectReader_LoadCorruptedJson_DoesNotCrash`).
- **Three classified suites**: `*_Unit` (pre-commit + CI, zero I/O, <100ms) · `*_Integration` (CI nightly, mocked devices/files) · `*_Device`/`*_AudioDevice` (manual, real hardware).
- **Integration & golden tests** on deterministic outputs: golden (render a known output, compare checksum/RMS), replay (import → edit → undo → render → verify), session-load (load N historical projects → migrations still work).
- **Fuzz & property-based**: fuzz every parser of external data (libFuzzer / `cargo-fuzz`) — malformed input must fail cleanly, never corrupt state silently. Property-based test algorithms with math invariants (`proptest`/`quickcheck`/`rapidcheck`) — e.g. "audio output stays within [-1.0, 1.0] for any input".
- **Invariants as runtime asserts** — every critical invariant documented in ARCHITECTURE.md has a matching `assert()`/`debug_assert!()` in code. An unverified invariant is just a promise. Free in release, immediate detection in debug.
- **Zero-alloc CI check** — any real-time thread has a test asserting `heap_alloc_count == 0` after N iterations. An accidental allocation in a hot path is invisible until user reports ("crash after 2h").

### Concurrency & systems

- **Ownership graph = DAG** — never an ownership cycle. Upward (child→parent) or lateral (sibling→sibling) references use `weak_ptr`/observer/callback, never a strong ref. Destruction order = reverse of construction.
- **Shutdown sequence** — in any multi-threaded system, document in ARCHITECTURE.md which thread is joined first, in what order queues drain, when OS handles are released. A service destroyed while the audio thread holds a reference = guaranteed crash.
- **Lock hierarchy** — document the mandatory acquisition order (e.g. `ProjectMutex → AudioGraphMutex → TrackMutex`). Never acquire a level-N lock while holding level-N+1. Prevents deadlocks; TSan detects violations.
- **Thread annotations** — comment every method with `// THREAD: audio | ui | any` so the model is explicit in code, not only in ARCHITECTURE.md.
- **RT threads** (audio callback, video decode) — no logging, no mutex, no I/O, no allocation. Communicate via a lock-free ring buffer: RT thread pushes `(EventId, timestamp, value)` with atomics; a low-priority thread drains to log/UI. Without it, "it crackles sometimes" reports are undebuggable.
- **Structured logging** — 4 levels (ERROR irrecoverable · WARN degraded · INFO session events · DEBUG off in release). Per-domain macros when justified (`LOG_AUDIO_WARN`). RT threads log only via the ring buffer above.

### Safety & static analysis

- **Error handling policy** — never swallow silently. Rust: `unwrap()`/`expect()` forbidden in prod except a proven invariant with `// SAFETY:`; prefer `?`/`map_err()`. C++: prefer return codes / `std::optional`/`std::expected` in critical code; never empty `catch(...)`. Errors at system boundaries (I/O, network, user parsing) always handled explicitly.
- **RAII (C++)** — no naked `new`/`delete`; `make_unique`/`make_shared`/stack. FFI opaque handles wrapped in a RAII type immediately (no naked handle circulating).
- **`using namespace` banned at file scope** — in headers (0 exceptions, fully qualify) and production `.cpp` (function scope or explicit alias `namespace fs = std::filesystem;` only).
- **Sanitizers** in dedicated CI builds: ASan (use-after-free, overflow) + UBSan (signed overflow, null deref) can combine; TSan (data races) separate build; MSan (uninit reads). Rust FFI modules: `cargo miri test` (nightly) catches UB at the `extern "C"` boundary that C++ sanitizers miss.
- **Clang-Tidy (C++)** — beyond cppcheck. Priority checks: `bugprone-use-after-move`, `bugprone-dangling-handle`, `performance-unnecessary-copy-initialization`, `modernize-use-override/make-unique`, `readability-function-size`. Ship a `.clang-tidy` + run in pre-commit/CI.
- **Hardware abstraction for testability** — any service touching OS resources consumes an interface, never the hardware directly. Priority interfaces: `IFileSystem`, `IClock` (timers/autosave), `IAudioSink`. Lets CI simulate disk errors / latency without real hardware.

### Supply chain

- **`cargo audit --deny warnings`** (RustSec CVE scan of `Cargo.lock`) and **`cargo-deny`** (crate bans, license policy, duplicate versions) on any serious Rust project.
- **`osv-scanner --recursive .`** or **`trivy fs .`** for vendored/system C++ deps (SDL3, ImGui, FFmpeg, codecs). C++ CVEs are rarer but graver (codec overflow = RCE). Nightly CI.
- **CODEOWNERS** — `.github/CODEOWNERS` assigning ownership by domain + mandatory reviewer on frozen cores / public APIs / CI. Create it even solo: it prepares a second dev with zero ambiguity.

### Process & collaboration

- **Code review checklist** (before approving any PR): Correctness · Security (secret/injection/missing validation) · Thread safety (shared data protected, atomics correct) · Resources (no leak) · Performance (no alloc in hot path, no avoidable O(n²)) · Readability (a senior understands it in 30s) · Tests (logic covered / no broken test).
- **Performance budgets** — document per subsystem and check in CI: audio callback <2ms · UI frame <16.6ms (60fps) · undo/redo <50ms · project load <3s · heavy ops (scan, waveform) async non-blocking.
- **Tech debt SLA** — build/clippy warning: immediate (don't commit) · race condition: 24h · architecture violation: 7 days · legacy TODO: next sprint. "Stop-the-line" on the first two.
- **Feature flags** — isolate unfinished/experimental code behind a runtime flag (preferred, `config.json`) or compile-time `#ifdef` with `// FEATURE: ... — remove when: ...`. `#if 0` is forbidden (that's dead code — delete it or use a real flag).
- **Public interface contracts** (exception to "comments = WHY only") — public interface headers document non-inferable contracts in one line: `// @pre Must NOT be called from audio thread`, `// @thread-safety lock-free, MT-safe`, `// @throws never (noexcept)`.
- **FFI conventions (C++ ↔ Rust)** — the most dangerous boundary. Every `extern "C"`: return an `int32_t`/`ResultCode` error code (never implicit); complex errors via a thread-local `get_last_error_str()`; ownership documented explicitly (`Box::into_raw()` → C++ `unique_ptr` with a deleter calling back into Rust; never `free()` C++-side on Rust-allocated memory). Capture conventions in an "Interop Error Handling + Memory Ownership" ADR.
- **Boy Scout rule** — when editing a file and you spot neighbouring debt fixable in <15 min (un-injected global, over-long function, untested helper), fix it in the same commit with a note. If >15 min: create a TODO/ticket and move on.

---

## Pre-commit checklist

Before marking any task done:

- [ ] Behavior preserved (or intentionally changed with tests)?
- [ ] One authoritative source per fact modified?
- [ ] Local reasoning clear without external context?
- [ ] No silent errors, no magic numbers, no dead code?
- [ ] Named accurately? Comments WHY only?
- [ ] File/function within size budget?
- [ ] Pre-commit checks pass (lint + tests)?
- [ ] PR ≤400 LOC or split planned?
