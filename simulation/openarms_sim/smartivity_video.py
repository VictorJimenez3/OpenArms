"""Edit a Smartivity episode from its captured simulator states."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
from itertools import groupby, pairwise
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw

from .render import _font

FPS = 30
SIZE = (1280, 720)
STAGES = {
    'pick': ('Pick up the beaker', 'Prepared source at dock A'),
    'pour': ('Pour into the flask', 'Liquid transfer drives the modeled reaction'),
    'return_cup': ('Return the beaker', 'Place the source back in dock A'),
    'home': ('Retract the arm', 'Keep the vessels in view'),
}


def _select_frames(frames):
    """Keep each motion sample and short edges of each policy wait."""
    retained = []
    for action, entries in groupby(range(len(frames)), key=lambda index: frames[index][1]):
        span = list(entries)
        if action:
            retained.extend(span)
        elif span[0] == 0:
            retained.extend(span[-33:])
        elif span[-1] == len(frames) - 1:
            retained.extend(span[:51])
        elif len(span) <= 27:
            retained.extend(span)
        else:
            retained.extend(span[:17])
            retained.extend(span[-10:])
    return retained


def _cuts(frames, retained):
    """Map each omitted source interval to the output frame where playback resumes."""
    cuts = []
    for output, (before, after) in enumerate(pairwise([-1, *retained, len(frames)])):
        if after <= before + 1:
            continue
        first = before + 1
        stop_time = frames[after][0] if after < len(frames) else frames[-1][0] + 1 / FPS
        cuts.append({
            'first_source_frame': first,
            'last_source_frame': after - 1,
            'sim_start_s': round(frames[first][0], 6),
            'sim_end_s': round(stop_time, 6),
            'duration_s': round(stop_time - frames[first][0], 6),
            'resume_at_output_frame': output if output < len(retained) else None,
        })
    return cuts


def _foam(state):
    return state.get('foam', 0) if isinstance(state, Mapping) else getattr(state, 'foam', 0)


def _reaction_window(frames):
    # Keep the beginning of the pour wide. Cut in once the captured state shows strong foam.
    pouring = [index for index, (_, action, _) in enumerate(frames) if action == 'pour']
    onset = next((index for index in pouring if _foam(frames[index][2]) >= .20), None)
    if onset is None:
        return (math.inf, math.inf)
    start = frames[onset][0] + .40
    following = next((t for t, action, _ in frames[pouring[-1] + 1:] if action), math.inf)
    return start, min(following, start + 1.65)


def _caption(rgb, fonts, title, mode, sim_time, action, camera, note, *, opening=False, closing=False):
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image, 'RGBA')
    title_font, detail_font, small_font = fonts
    dark = (12, 25, 32, 231)
    light = (250, 254, 252, 255)
    subtle = (209, 227, 225, 255)
    teal = (118, 225, 208, 255)

    # The corners and the lower edge leave the arm, flask neck, and approach visible.
    provenance = f'SIMULATED  /  {mode.replace("_", " ").upper()}'
    width = round(draw.textlength(provenance, font=small_font)) + 30
    draw.rounded_rectangle((26, 24, 26 + width, 64), radius=9, fill=dark)
    draw.text((41, 44), provenance, font=small_font, fill=teal, anchor='lm')
    angle = 'Reaction close-up' if camera == 'reaction' else 'Bench view'
    detail = f'{angle}  |  Sim {sim_time:05.1f} s'
    width = round(draw.textlength(detail, font=small_font)) + 28
    draw.rounded_rectangle((SIZE[0] - width - 26, 24, SIZE[0] - 26, 64), radius=9, fill=dark)
    draw.text((SIZE[0] - 40, 44), detail, font=small_font, fill=light, anchor='rm')

    if camera == 'reaction':
        heading, description = 'Modeled foam rises', 'Close-up of the recorded reaction'
    elif opening:
        heading, description = title, 'Smartivity’s My First Science Kit'
    elif closing:
        heading, description = 'Observe the outcome', 'Final camera view of this trial'
    else:
        heading, description = STAGES.get(action, ('Inspect the scene', 'Check the latest camera views'))
    card_width = max(draw.textlength(heading, font=title_font), draw.textlength(description, font=detail_font)) + 44
    draw.rounded_rectangle((26, 612, 26 + round(card_width), 694), radius=9, fill=dark)
    draw.rectangle((39, 627, 42, 680), fill=teal)
    draw.text((51, 618), heading, font=title_font, fill=light)
    draw.text((51, 665), description, font=detail_font, fill=subtle)
    if note:
        width = round(draw.textlength(note, font=small_font)) + 28
        draw.rounded_rectangle((SIZE[0] - width - 26, 654, SIZE[0] - 26, 694), radius=9, fill=dark)
        draw.text((SIZE[0] - 40, 674), note, font=small_font, fill=teal, anchor='rm')
    return np.asarray(image)


def render_movie(world, frames, path, *, title: str, mode: str, episode_id: str) -> dict:
    """Render one native RGB view of each retained 30 Hz state and return its source mapping.

    Call on the thread that owns the world's OpenGL context. Input samples have
    Action=None during inference waits, and state holds the actual captured world.
    """
    frames = list(frames)
    if not frames:
        raise ValueError('A recording needs captured simulator states.')
    times = [item[0] for item in frames]
    if any(not math.isfinite(time) for time in times) or any(a >= b for a, b in pairwise(times)):
        raise ValueError('Recording samples must have strictly increasing finite simulation times.')
    if any(action is not None and action not in STAGES for _, action, _ in frames):
        raise ValueError('The recording contains an unknown motion action.')

    retained = _select_frames(frames)
    cuts = _cuts(frames, retained)
    resumes = {cut['resume_at_output_frame']: cut['duration_s'] for cut in cuts}
    close_start, close_end = _reaction_window(frames)
    first_action = next((index for index, item in enumerate(frames) if item[1]), len(frames))
    last_action = next((index for index in reversed(range(len(frames))) if frames[index][1]), len(frames))
    fonts = (_font(32), _font(17), _font(17))
    timeline = []
    note = ''
    show_note_until = -1
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(prefix='.smartivity-', suffix='.mp4', dir=path.parent, delete=False) as handle:
        destination = Path(handle.name)
    try:
        with imageio.get_writer(
            destination, fps=FPS, codec='libx264', quality=None, macro_block_size=2, pixelformat='yuv420p',
            output_params=[
                '-crf', '17', '-preset', 'fast', '-movflags', '+faststart',
                '-metadata', f'title={title}', '-metadata', 'artist=OpenArms',
                '-metadata', f'comment=SIMULATED | {mode} | source episode {episode_id}',
            ],
            ffmpeg_log_level='error',
        ) as writer:
            for sample, index in enumerate(retained):
                sim_time, action, state = frames[index]
                camera = 'reaction' if close_start <= sim_time < close_end else 'wide'
                rgb = world.replay_rgb(state, camera)
                if rgb.shape != (SIZE[1], SIZE[0], 3) or rgb.dtype != np.uint8:
                    raise ValueError('Replay camera must return native 1280×720 uint8 RGB.')
                if resumes.get(sample, 0) >= .10:
                    note = f'Policy wait shortened by {resumes[sample]:.1f} s'
                    show_note_until = sample + 2 * FPS
                writer.append_data(_caption(
                    rgb, fonts, title, mode, sim_time, action, camera,
                    note if sample < show_note_until else '',
                    opening=index < first_action, closing=index > last_action,
                ))
                timeline.append({
                    'output_frame': sample, 'source_frame': index, 'sim_time_s': round(sim_time, 6),
                    'action': action, 'camera': camera,
                    'native_rgb_sha256': hashlib.sha256(np.ascontiguousarray(rgb)).hexdigest(),
                })
        with imageio.get_reader(destination) as reader:
            encoded = reader.get_meta_data()
            if encoded['source_size'] != SIZE or encoded['fps'] != FPS:
                raise RuntimeError('Encoded Smartivity video does not match the recording format.')
        destination.replace(path)
    finally:
        destination.unlink(missing_ok=True)

    return {
        'source_episode_id': episode_id, 'provenance': 'SIMULATED', 'mode': mode,
        'width_px': SIZE[0], 'height_px': SIZE[1], 'fps': FPS,
        'retained_frames': len(timeline), 'duration_s': round(len(timeline) / FPS, 6),
        'source_frames': len(frames), 'source_motion_frames': sum(action is not None for _, action, _ in frames),
        'omitted_source_frames': len(frames) - len(timeline),
        'omitted_simulation_duration_s': round(sum(cut['duration_s'] for cut in cuts), 6),
        'max_source_sample_interval_s': round(max((b - a for a, b in pairwise(times)), default=0), 6),
        'unique_native_frame_hashes': len({item['native_rgb_sha256'] for item in timeline}),
        'omitted_policy_waits': cuts, 'timeline': timeline,
    }
