# AI_CONTEXT — <ModuleName>

<!-- IMPORTANT: This file must be in the same directory as the source files it
     documents. Subdirectory source files are NOT included in AI_SUMMARY.md.
     See the flat module constraint in README.md. -->

> This file is hand-written and version-controlled. Keep it concise (< 80 lines).
> It is the AI assistant's primary reference for this module.
> AI_SUMMARY.md is auto-generated alongside it — never edit AI_SUMMARY.md manually.
> Delete this instruction block before committing.

## Purpose
<!-- 2-3 sentences: what this module does, what domain problem it solves,
     why it exists as a separate module rather than being inlined in its callers. -->

## Thread model (if applicable)
<!-- Fill only if this module has thread or concurrency constraints.
     Delete this section entirely if the module is single-threaded with no constraints. -->

| Component | Thread / Context | Notes |
|---|---|---|
| `functionA()` | Main thread | Synchronous, I/O OK |
| `processCallback()` | Worker thread | No blocking, no dynamic alloc |
| `queryState()` | Any thread | Lock-free read, MT-safe |

## Constraints
<!-- What must always be true when using this module.
     Focus on non-obvious rules that an experienced developer might miss. -->
- <Constraint 1: e.g., "Must call `publish()` after any structural change to sync state">
- <Constraint 2: e.g., "Thread A writes; Thread B reads — always use provided atomics">
- <Constraint 3: e.g., "The returned pointer is valid only until the next call to `reset()`">

## Forbidden
<!-- What must NEVER happen in code that uses this module.
     These are the most important rules — violations cause bugs that are hard to debug. -->
- <e.g., "Never call `heavyOp()` from the real-time callback — it allocates">
- <e.g., "Never store a raw reference to the returned object — it may be invalidated">

## Common patterns
<!-- Show the most frequent correct usage. Use your project's actual language. -->

```python
# Python example
result = module.do_thing(arg)
if result.ok:
    process(result.value)
```

```typescript
// TypeScript example
const result = await module.doThing(arg);
if (result.success) {
    process(result.data);
}
```

```cpp
// C++ example
auto result = Module::doThing(arg);
if (result) { process(*result); }
```

```go
// Go example
result, err := module.DoThing(arg)
if err != nil { return fmt.Errorf("doThing: %w", err) }
process(result)
```

```rust
// Rust example
let result = module::do_thing(arg)?;
process(result);
```

<!-- Keep only the example(s) relevant to your project's language(s). Delete the others. -->

## Key types
<!-- List the 2-5 most important types/structs/classes in this module. -->
- `MyServiceConfig` — configuration passed at construction
- `MyServiceResult` — returned by all operations; contains status + data

## Common failure modes
<!-- The 3-5 most dangerous bugs introduced when misusing this module.
     These are the patterns that are hard to debug — each entry should answer:
     WHAT goes wrong (symptom), WHY it happens (root cause), HOW to detect it.
     Delete this instruction block. -->
- **[Short label]**: [symptom — what the developer observes] → [root cause] / [how to detect or fix]
- **[Short label]**: [symptom] → [root cause] / [how to detect or fix]

## Hot files
<!-- The 2-4 files that change most often or contain the most dangerous invariants.
     These are the files where a reviewer should spend extra attention.
     Delete this instruction block. -->
- `FileName.ext` — [why it's hot: complex invariants / RT path / frequently modified / single point of failure]

## See also
<!-- Link to related modules, ADRs, or docs that provide more context. -->
- [Related module: `../OtherModule/AI_CONTEXT.md`]
- [ADR-XXXX: Why this module was extracted]
- [docs/ARCHITECTURE.md — overall system design]
