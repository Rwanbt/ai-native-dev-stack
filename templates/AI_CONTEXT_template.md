# AI_CONTEXT — <ModuleName>

> Hand-written context for AI assistants. Keep concise (< 80 lines).
> Delete this instruction block before committing.

## Purpose
<2-3 sentences: what this module does, what domain problems it solves, why it exists
as a separate module rather than inline in the caller.>

## Thread model
| Component | Thread | Notes |
|---|---|---|
| `<functionName>()` | Main | <any notes> |
| `<functionName>()` | Audio (RT) | Lock-free, no alloc |
| `<functionName>()` | Export thread | Alloc OK, not RT |

<!-- Common thread names: Main, Audio (RT), Export, Midi callback, Background scan -->

## Constraints
- <Constraint 1: e.g. "Must call publishAudioSnapshot() after any structural track change">
- <Constraint 2: e.g. "atomics are used for cross-thread flags — never replace with mutex">
- <Constraint 3: e.g. "SEH (__try/__except) is Windows-only — guard with #ifdef _WIN32">

## Forbidden
- <What must NEVER happen here: e.g. "No heap allocation in any function called from audio callback">
- <Common mistake to prevent: e.g. "Never read UpdateInfo fields without holding updateMutex">

## Common patterns
```cpp
// Most common usage
Seno::Module::someFunction(host);

// Query (no host needed — read-only, any thread)
bool result = Seno::Module::queryFunction(index, data);

// With error handling
if (!Seno::Module::riskyOp(host)) {
    host.showToast("Failed", ToastNotification::Type::Error);
}
```

## Key types
- `ModuleHost` — N-field host struct (brief description of most important fields)
- `SomeType` — what it represents

## See also
- ADR-XXXX: <relevant architectural decision>
- `docs/REALTIME_RULES.md` — if this module touches RT code
- `Core/RelatedModule/AI_CONTEXT.md` — if tightly coupled
