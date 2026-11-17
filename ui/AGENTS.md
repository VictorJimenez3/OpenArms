# Working in the UI

- Follow the [root agent rules](../AGENTS.md) and read [HANDOFF.md](../HANDOFF.md) section 4 for which front end is which.
- `ui/student` is the product (Ollie). Its design system and accessibility mapping are in [student/DESIGN.md](student/DESIGN.md). It has no build step.
- `ui/lab` is the original lab client and the real-bench screen. `ui/student/live.js` depends on `ui/lab/live-client.js`, and `/bench` is `ui/lab` with `ui/student/bench-skin.css` injected by the server.
- Check changes in a browser at desktop and phone width, by keyboard only, before calling them done.
