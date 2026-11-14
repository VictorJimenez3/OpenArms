# Interfaces

These are the first handoffs to discuss. Before both sides build against the same example, agree on the input and expected output.

| Areas | First question |
| --- | --- |
| Firmware and simulation | What arm state, motion or bench data does the preview need? |
| Simulation and agentic | What does the simulator need to preview a proposed action, and what does it return? |
| Agentic and UI | How will the UI pass along the user's command and show the interpreted action, confirmation and status? |
| Agentic and firmware | What does the arm need to run a confirmed action, and what does it report back? |

## Shared examples

Add the first example when a handoff is ready to build. Keep each entry short.

- **Handoff and status** — Name both sides. Mark the example as draft until both agree.
- **Example** — Show one input and its expected output. Include units, error or confirmation behavior when relevant.
- **Check** — Say how to verify that both sides work with the example.

When an agreed example changes, update it in the same pull request as the change or link the related pull requests. Have both sides review the change and run the example before merging.
