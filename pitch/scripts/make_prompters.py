"""Cut one read-along clip per speaker from the rendered film: 3-2-1 countdown with beeps, then their section.
The last, higher beep lands exactly on the section start, so a phone recording can be lined up by ear or by script."""
import subprocess, sys, wave, struct, math, os
from PIL import Image, ImageDraw, ImageFont
SRC = sys.argv[1]; OUT = 'prompter'
PARTS = [('1-victor', 14, 51, 'VICTOR'), ('2-duc', 51, 73, 'DUC'), ('3-joseph', 73, 92, 'JOSEPH'), ('4-stef', 92, 112, 'STEF'), ('5-close-victor', 112, 120, 'VICTOR · CLOSE')]
big = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 420); mid = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 64)
for name, a, b, label in PARTS:
    for n in (3, 2, 1):
        im = Image.new('RGB', (1280, 720), '#3b34c4'); d = ImageDraw.Draw(im)
        d.text((640, 330), str(n), font=big, fill='#fff6e3', anchor='mm')
        d.text((640, 620), f'{label}: start reading on the high beep. Follow the pink dot.', font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 34), fill='#fff6e3', anchor='mm')
        d.text((640, 70), 'Phone recording? Lab coat on? Look at the lens.', font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 34), fill='#ff4f9a', anchor='mm')
        im.save(f'/tmp/cd{n}.png')
    sr = 44100; dur = 3 + (b - a); w = wave.open('/tmp/beeps.wav', 'w'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    beeps = [(0, 880, .12), (1, 880, .12), (2, 880, .12), (3, 1760, .3)]
    buf = bytearray()
    for i in range(int(dur * sr)):
        t = i / sr; v = 0
        for t0, f, l in beeps:
            if t0 <= t < t0 + l: v = .5 * math.sin(2 * math.pi * f * t)
        buf += struct.pack('<h', int(v * 32767))
    w.writeframes(bytes(buf)); w.close()
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-t', '1', '-i', '/tmp/cd3.png', '-loop', '1', '-t', '1', '-i', '/tmp/cd2.png', '-loop', '1', '-t', '1', '-i', '/tmp/cd1.png',
        '-ss', str(a), '-t', str(b - a), '-i', SRC, '-i', '/tmp/beeps.wav', '-filter_complex',
        '[0:v]fps=30,format=yuv420p[a];[1:v]fps=30,format=yuv420p[b];[2:v]fps=30,format=yuv420p[c];[3:v]scale=1280:720,fps=30,format=yuv420p[d];[a][b][c][d]concat=n=4:v=1:a=0[v]',
        '-map', '[v]', '-map', '4:a', '-c:v', 'libx264', '-crf', '23', '-c:a', 'aac', '-shortest', f'{OUT}/prompter-{name}.mp4'], check=True)
    print(name)
