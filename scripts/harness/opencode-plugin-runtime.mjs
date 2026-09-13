// Runtime harness for the OpenCode plugin (#153).
//
// The plugin bug this exists to catch — a global `Bun.file` and a Bun-shell `$`
// that the opencode runtime does not provide — only appears when the real file
// is loaded by a real JavaScript runtime and its hooks are driven. So this
// harness imports the *rendered* plugin, builds it with a workspace, then runs
// the step list it was given through `tool.execute.before` / `tool.execute.after`.
//
// It asserts nothing: the plan and the assertions live in the Python driver
// (scripts/opencode_plugin_runtime_e2e.py), so a failure message names the
// property, not a stack trace. The report is the only thing printed to stdout;
// the driver parses it. Node warnings and errors go to stderr untouched.
//
// Usage: node --experimental-strip-types opencode-plugin-runtime.mjs <plan.json>
// Plan:  {"plugin": "<abs path>", "workspace": "<abs dir>",
//         "steps": [{"id", "hook", "input", "output"}, ...]}

import { pathToFileURL } from "node:url"
import { readFile } from "node:fs/promises"

const plan = JSON.parse(await readFile(process.argv[2], "utf8"))
const report = { loaded: false, export: null, hooks: [], steps: [] }

const emit = (failed) => {
  console.log(JSON.stringify(report))
  process.exit(failed ? 1 : 0)
}

// The #153 failure mode was a runtime with no global `Bun`. Recording what the
// runtime actually provides makes the absence part of the evidence rather than
// an assumption about the host.
report.globalBun = typeof Bun

let module
try {
  module = await import(pathToFileURL(plan.plugin).href)
} catch (error) {
  report.loadError = String((error && error.stack) || error)
  emit(true)
}

const factory = module.AiNativeDevStack
  ?? Object.values(module).find((value) => typeof value === "function")
if (typeof factory !== "function") {
  report.loadError = "the rendered module exports no plugin factory"
  emit(true)
}
report.export = "AiNativeDevStack" in module ? "AiNativeDevStack" : "anonymous"

let hooks
try {
  hooks = await factory({ directory: plan.workspace })
} catch (error) {
  report.loadError = String((error && error.stack) || error)
  emit(true)
}
report.loaded = true
report.hooks = Object.keys(hooks).sort()

for (const step of plan.steps) {
  const entry = { id: step.id, ok: true }
  try {
    const hook = hooks[step.hook]
    if (typeof hook !== "function") throw new Error(`the plugin exposes no ${step.hook}`)
    await hook(step.input ?? {}, step.output ?? {})
  } catch (error) {
    entry.ok = false
    entry.error = String((error && error.message) || error)
  }
  report.steps.push(entry)
}

emit(false)
