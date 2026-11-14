# OpenArms UI

`ui/` is the student-facing app. The folder is currently a placeholder. The UI framework and cross-component payloads are open decisions. Victor is the UI contact.

- **Student flow** — Capture a spoken instruction, show the interpreted action and simulation preview, collect explicit confirmation of that plan, and show execution status.
- **Component boundary** — The UI presents previews and status from the other components. The agent and firmware own validation, approval, and execution. Use mocks for integration work until both sides agree on a concrete example.
- **First integration** — Mock one instruction through preview, confirmation, and completion. Record its input, expected output, and confirmation behavior in [INTERFACES.md](../docs/INTERFACES.md). See [PROJECT.md](../docs/PROJECT.md) for the demo scope.
