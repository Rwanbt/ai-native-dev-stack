# Mavis/OpenCode generated files - never committed

The Mavis daemon generates `opencode.json`, `plugins/mavis.js` and `tools/*.js`
in this directory, and every one of them contains absolute paths from the
machine that generated it (the daemon installation, the user's `~/.mavis`
skills). They were committed once by accident and shipped a maintainer's home
directory to every clone.

They are machine-local by nature: regenerate them with your own Mavis daemon on
your own machine. Nothing in the stack installs from this directory -
`scripts/install_agents.py` owns the OpenCode integration and writes its plugin
to `~/.config/opencode/plugins/ai-native-dev-stack.ts`.