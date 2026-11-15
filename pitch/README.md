# Pitch, film and submission

Everything for HackPrinceton judging. Start with [TEAM.md](TEAM.md) for who does what by when.

| File | What it is |
| --- | --- |
| [TEAM.md](TEAM.md) | Schedule to the 8:00 a.m. cutoff and each person's lines, shots and table questions |
| [FILM.md](FILM.md) | The two-minute film: what we sell, timeline, exact voiceover, Ollie's animation plan, shot list, honesty rules |
| [FACTS.md](FACTS.md) | Statistics and numbers we can say out loud, with sources and the limits of each |
| [renders/animatic-v2-ollie.mp4](renders/animatic-v2-ollie.mp4) | Current cut: real app and simulation footage, brand cards, animated Ollie, script captions. Dashed boxes are bench shots still to film |
| [film/](film/) | HyperFrames source. Edit `build.py`, then `python3 build.py && npm run check` and `npm run render` (Node 22+, ffmpeg) |
| [scripts/](scripts/) | `capture_app_run.sh` records a full lab from the running student app; `clean_smartivity.py` re-renders recorded Smartivity episodes without burned-in captions |
| [../research/victor/hackprinceton-devpost-draft.md](../research/victor/hackprinceton-devpost-draft.md) | Devpost copy, ready to paste |

Send bench footage (named by shot ID, e.g. `H4-take2.mov`), voice memos (`vo-<name>.m4a`) and the music track to Victor; they go into the local drop folder and the final cut lands here.
