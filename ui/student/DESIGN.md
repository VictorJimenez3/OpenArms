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

Simulated runs are labelled “Recorded simulation” on the video and in the report. The report states its evidence source. Ask Ollie says its answers come from the lab guide.
