# Universal Engineering Rules
<!-- Cross-tool: Claude Code (@AGENTS.md in CLAUDE.md), Cursor (.cursorrules @AGENTS.md), Codex (auto-loaded AGENTS.md) -->
<!-- Keep this file at the project root. Customize per project as needed. -->
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
