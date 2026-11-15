# Ollie by OpenArms: brand and interface

Ollie is the student-facing brand for OpenArms. OpenArms is the team and the platform; Ollie is the robot lab partner a student talks to.

## Promise

**You’re the scientist. Ollie’s the hands.** The student makes every call (what to test, when to pour, when to stop). Ollie does the reaching and pouring and always states its plan before moving.

## Ollie, the character

A small robot arm drawn from the real arm’s parts: a base, two capsule segments, three pink joints, and a head whose two “ears” are the gripper fingers. Ollie has no mouth; it speaks through a speech bubble and through posture.

| Pose | When | Reads as |
| --- | --- | --- |
| `hello` / `idle` | shelf, lab question | relaxed S-curve, slow bob |
| `listen` | waiting for an instruction or an observation | leaning in, ears apart |
| `think` | prediction, showing a plan | leaning back, head tipped |
| `pour` | the action is running | tipped right over |
| `wave` | finished, right answer | upright, ears wide, head wag |
| `stop` | Stop was pressed | folded down, eyes shut |

Poses are CSS variables on one SVG (`ollieSVG` in `app.js`), so the same figure can be driven by real arm state later and reused in a trailer.

## Voice

First person, short sentences, a nine-year-old’s vocabulary. Ollie calls the student “scientist”, never gives orders, and never moves without a yes. Wrong answers get “Not quite. Have another go.” Ollie says plainly when something is a simulation or when it can only answer from the lab guide.

## Visual system: capsules and joints

Every shape comes from the arm: capsule buttons and inputs, circular joints for markers, and a step tracker drawn as an arm linkage that fills joint by joint. Flat colour, no outlines, no drop shadows on content.

- **Colour comes from the liquids.** Ink `#1a1538`, cream `#fff6e3`, tea indigo `#3b34c4`, acid pink `#ff4f9a`, base green `#9be05a`. Each experiment owns a full-screen field: tea indigo, volcano `#ff6240`, potions `#c9aaff`, lava `#ffc53a`, snow `#bfe6ff`. Pink always means “now” or “yes”; red is reserved for Stop.
- **Type.** Bagel Fat One for the wordmark, headings and experiment names; Atkinson Hyperlegible Next for everything read or tapped, chosen for low-vision legibility. Both are self-hosted.
- **Motion.** Springy and physical, like a joint settling. Ollie’s pose change is the main moment on each screen. Everything stops under reduced-motion.
- **Access.** 48 px minimum targets, every answer available by tap, keyboard or microphone, results described in words rather than colour alone, and a read-aloud button on Ollie’s plan and description.

## Honesty rules

Simulated runs are labelled “Recorded simulation” on the video and in the report. The report states its evidence source. Ask Ollie answers typed questions with an AI model through the lab server (the key never reaches the browser), says it is an AI that can make mistakes, and falls back to lab-guide answers when the model is unavailable.

## Input and accessibility

The student may not be able to use a mouse, trackpad or standard keyboard. They may use speech recognition, a switch, eye gaze, a head pointer or a mouth stick, all of which drive the page through the keyboard and pointer interfaces. So the app targets WCAG 2.2 AA and leans on the assistive technology the student already has rather than a bespoke voice-only mode. Ollie's own spoken conversation is the Gemini Live path in the bench client.

- Everything is operable by keyboard alone, one key at a time (2.1.1, 2.1.2). There are no single-letter shortcuts that speech input could trigger by accident (2.1.4); Escape is the only global key and it means Stop.
- Visible button text is the accessible name, so voice control users can say what they see (2.5.3).
- Targets are at least 48 px with spacing; nothing needs dragging, holding, hovering or a precise path (2.5.1, 2.5.7, 2.5.8).
- No time limits. A proposal that expires on the server while the student decides is requested again and explained (2.2.1).
- Focus is always visible, moves to the new step's heading, and moves to Stop when the arm starts (2.4.3, 2.4.7).
- Text contrast is at least 4.5:1 on every experiment colour; the current step is marked by shape and a ring, not colour alone (1.4.1, 1.4.3, 1.4.11).
- Results are given in words and can be read aloud; status changes are announced (1.1.1, 4.1.3). Motion stops under reduced-motion (2.3.3).

The Access page (`#/access`, in the top bar) states this to students and judges: the tools Ollie works with, the only keys needed, and four saved settings (bigger text and buttons, Ollie reads out loud, extra-bold focus highlight, calm screen).

Checked by keyboard-only runs in a browser and by an axe-core 4.10 audit (WCAG 2.0–2.2 A/AA rules plus best practices) of 27 screen states: home, Access, reports, every step of the bench lab, a recorded lab and the live lab, the Ask Ollie panel, 320 px reflow and the bigger-text setting. Result: 0 violations, every control named, no target under 24 px, no horizontal scroll at 320 px. Automated rules cover only part of WCAG. Not yet tested with real switch, eye-gaze or screen-reader users.
