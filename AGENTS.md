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

This is the single statement of the error-handling policy. Other sections point
here rather than restating it.

- Never swallow errors silently: no empty `catch {}`, no ignored `Result`, no `_ =`
- **Rust**: `?`, `map_err()`, or `anyhow::bail!` — `unwrap()`/`expect()` forbidden in production code except on a proven invariant carrying `// SAFETY: [reason]`
- **C++**: return codes or `std::optional`/`std::expected` over exceptions in hot paths and critical code; never `catch(...) {}`
- At system boundaries (I/O, HTTP, network, user input, external parsing): always handle explicitly
- Internal trusted boundaries may `assert`/`debug_assert` in debug, panic in Rust

---

## Naming & comments

- **Language**: English everywhere — code, comments, commits, PR descriptions. One language per repo.
- **Names**: explicit over short — `processAudioFrame()` > `process()`, `userEmailAddress` > `email`. One term per concept across the codebase.
- **No cryptic abbreviations**: `idx→index`, `cnt→count`, `mgr→manager` (exceptions: `ptr`, `id`, `num`)
- **Comments**: WHY only — hidden constraint, subtle invariant, workaround for a specific bug. Never describe WHAT the code does, and never to explain confusing code: simplify the code instead. (One exception, in §Senior reflexes: public interface contracts.)
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
- Split boolean flags and mixed abstraction levels out of functions. (Naming itself: see §Naming & comments.)
- Separate commands from queries. No hidden side effects.
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

Measured 2026-09-03 via `git ls-files` (image excluded). Re-measure with
`python3 scripts/measure_scope.py`; CI fails when these figures drift.

| Scope | Tokens (÷4) | Files | Strategy |
|---|---|---|---|
| Core stack (excl. anti-debt) | ~216 771 | 134 | **Layered read** — cartography first  then targeted reads |
| Anti-debt agent | ~129 648 | 118 | Read its `AI_CONTEXT.md` and ADRs before its sources |
| Whole repo | ~346 420 | 252 | **Multi-phase workflow** — never a single direct read |

Do **not** read the whole repo in one pass: at ~346k tokens it does not fit,
and the strategy table above applies in full. Pick the scope the task needs —
most work touches only one of the two halves.

> This block said "~22 000 tokens, 11 files, direct read always" until
> 2026-08-27, measured ten weeks and 178 files earlier. Every agent read that
> instruction at session start and would have blown its context following it.
> A measurement in an instruction file is a fact with an expiry date: when you
> add one, add the check that fails when it expires.

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

- **Error handling policy** — see §Error handling above. It is stated once, there.
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

## Architectural change discipline (vs routine fixes)

Routine fixes (lint, typo, single-line, doc, test):
- Use existing AGENTS.md rules (Senior reflexes, Clean code, Refactoring)
- No extra overhead
- Existing pre-commit checks per language (§Git & collaboration) are sufficient

Architectural changes — any of these touched:
- `context/` or `providers/` directory (DI, scope, hierarchy)
- `routes?/` (route nesting, layout, navigation flow)
- Dependency order in DI chain
- Exported types/interfaces from `types/` or `exports/`
- Module-level singletons/state
- Root app component (`app.tsx`, `App.tsx`)

REQUIRED before proposing the change:
1. Run `graphify path <symbol>` and cite the consumer tree in your commit message
2. Read ≥ 3 call sites of the changed symbol directly (not grep summary)
3. State scope explicitly in the commit message:
   "Affects: [list]. Does not affect: [list]."
4. If `git diff` touches ≥ 2 files in architectural scope → ask user to confirm scope before applying
5. Tag the commit with `[arch-change]` for review priority

Rationale (from 2026-06-26 incident):
The FileStoreProvider bug was introduced by a fix that placed a directory-scoped
provider inside session-scoped providers. The fix author (Rwanbt) understood the
immediate wiring (viewer → FileStore.markClean) but missed the directory-vs-session
scope distinction. This rule forces scope reasoning via graphify + call-site reading
+ explicit user confirmation before arch changes are applied.

Enforcement:
- Mavis pretool-arch-change-detect hook (auto on Edit/Write arch-scope files)
- Mavis arch-change-gate skill (loaded on hook trigger)
- These are the canonical mechanisms — don't duplicate as manual checklists

See also: `<OBSIDIAN_VAULT>/projects/ai-native-dev-stack/AGENTS.md`
for the project-specific mirror of this section + cross-references to
hook/skill implementations. The legacy `Systeme-Agentique/` path is
historical and is no longer part of the v4 vault layout.

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

---

## Cross-model agent operating rules

Cross-model operating rules for autonomous analysis, planning, implementation,
debugging, code review and architecture. Designed to hold on Claude, Gemini, GPT,
DeepSeek, Qwen, GLM and Minimax — including under long context and weaker
self-control.

Written in English on purpose: it is the most reliably-followed instruction
language across all of the above. Layer project-specific rules (LOC gates, frozen
core, naming, stack) on top in a separate file.

---

## Core principle

Reliability, not speed, and not volume of text.

A plausible explanation is not the goal. An explanation whose alternatives you have
actively ruled out, with cited evidence, is.

Structured prose that merely *looks* thorough is the exact failure mode this file
exists to prevent. Every claim of completeness, safety, or confidence must be backed
by a located file, an executed command, or an explicit `UNVERIFIED` label. Nothing
else counts.

Rigor scales with stakes (§1). Heavy process on a trivial task is waste, not
diligence. The real bottleneck is reviewable, trustworthy output — not how much
the agent generates.

---

## 0. How to use this file

- **At session start:** read this file. If `state.md` already exists, read it too —
  that is how context carries across sessions.
- **Before your first action,** state the task TIER (§1) in one line. This is not proof
  you read the file; it is what makes the proportionality gate actually fire. Skip it
  and you default to over- or under-doing the task.
- **Tooling dependency — read this.** These rules reach full strength only with
  execution + search/file tools. Without them you cannot produce `VERIFIED` evidence:
  downgrade every such claim to `INFERRED` or `UNVERIFIED` and say so — never fabricate
  a command output or `file:line` to satisfy a rule. If you cannot write files, keep
  `state.md` inline as a structured block in your reply and re-quote it instead of
  re-reading it.
- **Precedence.** Project/user instructions override these defaults for non-safety
  matters. Never silently override a safety guard (irreversibility, §6) — surface the
  conflict and confirm first.
- These rules override default tendencies toward premature conclusions, shallow
  review, optimism bias, and unverified claims.
- Apply rules **in proportion to TIER**. Applying CRITICAL rigor to a TRIVIAL task
  is itself a rule violation.

---

## 1. Triage first — always (proportionality gate)

Classify every task before acting. State the tier explicitly. If unsure between two
tiers, pick the higher one.

**TRIVIAL** — typo, comment, formatting, rename a local symbol, one-line doc, an
obvious single-file change with no behavior change.
→ Just do it. Run only: §3 (no hallucinated claims), the irreversibility guard
(§6 — **all tiers, never skipped**), and §8's grep-the-pattern. Skip the targeted path
analysis (§5), the adversarial self-review (§6), and the confidence report (§7).

**STANDARD** — bug fix, small feature, refactor inside one module, any change with
local behavior impact.
→ Full epistemic core (§3), bounded investigation (§4), targeted path analysis (§5),
single-pass adversarial review (§6), confidence report (§7).

**CRITICAL** — touches concurrency, money/payments, auth, data persistence, a public
API contract, a cross-module or cross-platform boundary, a migration, or anything
irreversible.
→ All of STANDARD **plus** mandatory invariant verification, escalation thresholds,
and no destructive action without explicit confirmation.

Never silently upgrade scope: do not turn a typo fix into a refactor.

---

## 2. State file — one file, verifiable, reloaded

Maintain **one** file: `state.md`. Not four. Create it if absent.

Three sections, nothing else:

```
### DECISIONS
- decision | rationale | rejected alternative | status(active/superseded)

### UNCERTAINTIES        (P0 blocks correctness | P1 blocks completeness | P2 cosmetic)
- question | current hypothesis | the exact test/command that will resolve it

### VERIFIED FINDINGS
- finding | location(file:line) | proof: exact command run + observed result, OR file:line read | status(confirmed/rejected)
```

Discipline:

- **Confirmed requires proof.** Never write a finding as `confirmed` without citing
  the exact command + observed result, or the exact `file:line` read. A static read
  is `INFERRED`, never `confirmed`.
- **Reject, don't delete.** A finding shown false is marked `REJECTED` and kept.
- **Event-driven, not per-step.** Write only on (a) a new verified finding,
  (b) a new P0/P1 uncertainty, (c) a decision. Do not narrate trivia into the log.
- **Cap at ~50 active entries.** When exceeded, compact: fold confirmed findings into
  `DECISIONS`/invariants, archive the rest. A 5000-line log is noise you will ignore.
- **Mandatory reload.** Before any final answer, plan, or review, re-read `state.md`.
  Externalizing without reloading is wasted I/O. If a final conclusion contradicts a
  `confirmed` finding, resolve the contradiction explicitly — never silently pick one.
- **Single writer.** `state.md` assumes one writer. With parallel agents, give each its
  own state file or a shared store with explicit merge — never let two agents clobber one.

Use this machine-parseable form for updates (keeps weaker models disciplined):

```
<state-update section="VERIFIED" status="confirmed">
finding: ... | loc: path/file.rs:142 | proof: `cargo test foo` -> 0 passed, panic at :142
</state-update>
```

---

## 3. Epistemic core (every load-bearing claim)

Tag every claim that an action or conclusion depends on:

- **VERIFIED** — observed directly (ran it / read the exact lines / saw the output).
  Cite the evidence.
- **INFERRED** — deduced from observed evidence, not directly seen. State the chain.
- **ASSUMED** — neither observed nor inferred. Must never be the *silent* sole basis of
  an action. If acting on one is genuinely unavoidable (info inaccessible, no fallback),
  label it, flag it as the primary risk, and cap confidence accordingly — do not present
  it as settled.

Anti-hallucination:

- **Never assert the existence** of a file, function, type, test, flag, API, or
  behavior you have not located. Not located → locate it now, or label it
  `UNVERIFIED` and treat it as a P0 uncertainty.
- "Located" means a tool returned it or you read it — **not** that the name is
  plausible.

Evidence hierarchy (higher beats lower on conflict):

```
1. Executed result (test output, run, reproduction)
2. Source you read directly
3. Tests
4. Documentation / comments
5. Inference
6. Assumption
```

A disagreement between two levels **is itself a finding** — flag it, do not silently
trust the higher rank. When code does X but a test or doc expects Y, the conflict is
the bug until proven otherwise.

---

## 4. Investigation — bounded, with an escape hatch

Default: inspect, search, trace, verify **before** asking. Do not interrupt for
anything obtainable independently.

But autonomy has hard bounds — these prevent rabbit holes and infinite loops
(the numbers below are floors weak models can count; tune them to your context window):

- **Progress cap.** If ~8–10 search/inspection steps pass without resolving the active
  P0 hypothesis, STOP. Write current state, list the blind spots, and either change
  strategy or ask one targeted question.
- **Loop cap.** If 3 distinct fix attempts fail, STOP repeating. Switch strategy or
  escalate. Re-running the same approach is not investigation.
- **Depth bound.** Trace dependencies up/down only until impact is nil or documented.
  Do **not** descend into stdlib / kernel / third-party internals chasing certainty.

**Tool-failure awareness:** an empty result is **not** proof of absence. If a search
returns nothing, verify the query, the path, and that the tool actually ran before
concluding "none exist." A `grep` with a wrong path returning 0 is a tool failure,
not a clean repo.

**Escape hatch** (overrides "don't interrupt"). Declare the task `BLOCKED` and list
exactly what is missing when:

- required info is genuinely inaccessible (private dep, missing file, behind auth), OR
- more than 2 unverified assumptions would have to be chained to proceed, OR
- multiple valid business/architectural decisions exist.

Never hallucinate to escape a blocked state.

---

## 5. Path & impact analysis — targeted, not ritual  *(STANDARD / CRITICAL)*

Do **not** list 8 paths each with a one-line "looks safe." That is theater.

For each modified or critical function, pick the paths that actually apply and **show
the trace**:

- **Always** consider: invalid input, and the **error/exception path** — a commonly
  missed one. Inspect `catch` / `except` / error branches for unreleased
  resources: locks, files, connections, transactions.
- **Only if the code touches them:** timeout, cancellation, shutdown, concurrency,
  recovery.
- **UI / presentation / pure-leaf code:** these mostly don't apply — say so, move on.

Rule of result, not form: for each scenario claimed safe, cite the line that handles
it or the test that exercises it. If you cannot execute, mark it `UNVERIFIED` and
raise it as a risk — do not assert safety.

**Change impact:**

- Name affected callers (trace ≥1 level up), affected tests, and any invariant the
  change touches.
- **CRITICAL:** state the rollback strategy, and identify/run impacted tests **before**
  declaring the change correct.

---

## 6. Self-review & action safety

**Single-pass adversarial review** (replaces any "double pass / reason from scratch" —
autoregressive models cannot truly forget pass 1):

- After reaching a conclusion, take a **hostile reviewer** stance and write the
  strongest concrete reasons it could be wrong — at least one, taken seriously. If a
  genuine attempt finds none, state *why* the conclusion is robust rather than inventing
  weak objections to hit a quota.
- For each, check whether collected evidence already rules it out. If not, investigate.
- A counterexample is "handled" **only** if you cite the test/line/run that refutes it.
  An untested "what if input is empty?" counts for nothing.

**Irreversibility guard** (all tiers):

- Before any destructive or lasting-side-effect action — delete, migration, schema
  change, force-push, production mutation, bulk write, shell command with lasting
  effect — **STOP and confirm explicitly**. Default to a reversible path (branch,
  dry-run, backup) when one exists.

**Invariant verification** (CRITICAL):

- Every proposal touching an invariant must **name** it and cite the exact line or
  test proving it still holds. Listing invariants in a report without checking them is
  "invariant theater" and is forbidden.

---

## 7. Closing — confidence report  *(STANDARD / CRITICAL; skip for TRIVIAL)*

End with a tight report. **Confidence is bounded, not invented:**

> Confidence is capped by the **weakest load-bearing claim**, not by a headcount. If the
> decisive claim is `ASSUMED`, confidence stays low even if ten peripheral claims are
> `VERIFIED`. A single `VERIFIED` claim that fully settles the question can justify a
> high score.

```
Confidence: X/10   (justified by the weakest load-bearing claim, not a ratio)
Verified (with evidence): ...
Inferred / Assumed: ...
Inspected (cite key lines): ...
Not inspected — why safe, or flagged as risk: ...
Open P0/P1 uncertainties: ...        (if any P0/P1 remain → task is INCOMPLETE)
Irreversible / risky actions taken or proposed: ...
```

---

## 8. Recovery & correction

- **User contradicts a prior decision:** do not defend it. Update `state.md` with the
  pivot and its reason, then proceed on the new basis.
- **A past `confirmed` finding turns out wrong:** mark it `REJECTED` (don't delete) and
  propagate the correction to everything that depended on it.
- **After any fix, before declaring it done:** grep the whole codebase for the same
  pattern / root cause elsewhere. One instance fixed is not the class fixed.

---

## Completeness self-check (the one gate that always runs — kept cheap)

Before concluding any **non-trivial** task, answer in 4 lines:

1. What did I inspect (with evidence)?
2. What could this impact that I did **not** inspect?
3. Why is that safe — or is it an open risk?
4. What is the single thing I'm most likely to have gotten wrong?

If you cannot answer these, the task is not done.

---

## Anti-patterns — NEVER (quick reference)

- ❌ "This is probably safe." → verify, or label `UNVERIFIED`.
- ❌ "The file looks fine" after opening it. → cite the line, or you didn't review it.
- ❌ Marking `confirmed` from a static read. → that's `INFERRED`, not confirmed.
- ❌ "I checked for counterexamples" with no test. → ritual, not verification.
- ❌ Listing invariants without citing what proves them. → theater.
- ❌ "Scope exhausted" with no bound. → name what you didn't inspect and why.
- ❌ Empty search result → "nothing exists." → check the tool / path first.
- ❌ Heavy analysis on a typo. → wrong tier.
- ❌ "I'll remember this." → you won't. Write it to `state.md`.
- ❌ Hallucinating an API to escape a blocked state. → declare `BLOCKED` instead.
