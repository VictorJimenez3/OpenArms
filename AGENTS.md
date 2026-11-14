# Working in OpenArms

- Each agent uses an isolated worktree and branch; the integrator owns shared contracts and merges.
- Read the [ownership table](README.md#where-to-start) and keep edits in the assigned area. Check with the other owner before changing their files or shared setup.
- Before creating any new worktree, pull the latest `main` from `origin`. Run `git pull --ff-only origin main` in the checkout of `main`.
- Before starting technical research or rerunning an experiment, check the [research index](research/README.md) and search `research/` with `rg`. Cite the relevant note when using a finding, and link new evidence from the index.
- Prototype independently with sample inputs and mocked outputs. When two areas need to connect, agree on one concrete example and record it in [INTERFACES.md](docs/INTERFACES.md).
- Use a GitHub issue for a shared blocker or decision. Reuse the issue thread for follow-ups. Local tasks can stay in your branch.
- Keep these notes editable as the team learns.
