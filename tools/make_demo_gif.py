"""Render the claude-vault demo GIF.

Every line of output in here was captured from the real CLI (see capture.txt);
nothing is invented for the demo.
"""

import sys

from PIL import Image, ImageDraw, ImageFont

USER = sys.argv[1] if len(sys.argv) > 1 else "jbasoft"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/claude-vault-demo.gif"

W, H = 900, 540
BG = (13, 17, 23)
BAR = (22, 27, 34)
BORDER = (48, 54, 61)

GREEN = (63, 185, 80)
WHITE = (230, 237, 243)
GRAY = (139, 148, 158)
BLUE = (88, 166, 255)
RED = (248, 81, 73)
GOLD = (210, 153, 34)
MAGENTA = (219, 97, 162)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
UI = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
UI_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

f = ImageFont.truetype(FONT, 16)
fb = ImageFont.truetype(FONT_B, 16)
f_small = ImageFont.truetype(FONT, 13)
ui = ImageFont.truetype(UI, 14)
ui_b = ImageFont.truetype(UI_B, 15)
ui_s = ImageFont.truetype(UI, 11)
title_f = ImageFont.truetype(UI_B, 30)
sub_f = ImageFont.truetype(UI, 17)

PAD_X, PAD_Y, LH = 26, 52, 25

frames: list[Image.Image] = []
durations: list[int] = []


# --------------------------------------------------------------------- chrome


def base() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, 32], fill=BAR)
    d.line([0, 33, W, 33], fill=BORDER)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([16 + i * 20, 11, 26 + i * 20, 21], fill=c)
    t = "claude-vault — demo"
    d.text(((W - d.textlength(t, font=ui_s)) / 2, 10), t, font=ui_s, fill=GRAY)
    d.rectangle([0, 0, W - 1, H - 1], outline=BORDER)
    return img


def render(lines, dialog=None, cursor=False) -> Image.Image:
    """lines: list of (text, color, font). Last line may get a cursor."""
    img = base()
    d = ImageDraw.Draw(img)
    y = PAD_Y
    for i, (text, color, font) in enumerate(lines):
        d.text((PAD_X, y), text, font=font, fill=color)
        if cursor and i == len(lines) - 1:
            x = PAD_X + d.textlength(text, font=font)
            d.rectangle([x + 2, y + 2, x + 10, y + 18], fill=WHITE)
        y += LH
    if dialog:
        draw_dialog(img, *dialog)
    return img


def draw_dialog(img, typed: str, focus: bool = True) -> None:
    """The real tkinter dialog, redrawn at the same proportions."""
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 34, W, H], fill=(0, 0, 0, 120))
    bw, bh = 470, 258
    x0, y0 = (W - bw) // 2, (H - bh) // 2 + 10
    x1, y1 = x0 + bw, y0 + bh
    d.rectangle([x0 + 4, y0 + 6, x1 + 4, y1 + 6], fill=(0, 0, 0, 90))
    d.rectangle([x0, y0, x1, y1], fill=(240, 240, 240), outline=(170, 170, 170))
    d.rectangle([x0, y0, x1, y0 + 26], fill=(222, 222, 222))
    d.text((x0 + 10, y0 + 6), "claude-vault", font=ui_s, fill=(60, 60, 60))

    tx, ty = x0 + 22, y0 + 44
    d.text((tx, ty), "A credential is needed", font=ui_b, fill=(20, 20, 20))
    d.text((tx, ty + 28), "Enter the value for “STAGING_DB_PASSWORD”.",
           font=ui, fill=(85, 85, 85))
    d.text((tx, ty + 48), "It is stored locally and is never shown to the",
           font=ui, fill=(85, 85, 85))
    d.text((tx, ty + 66), "AI agent.", font=ui, fill=(85, 85, 85))

    ey = ty + 100
    d.text((tx, ey + 4), "Value", font=ui, fill=(40, 40, 40))
    ex0 = tx + 64
    d.rectangle([ex0, ey, x1 - 22, ey + 26], fill=(255, 255, 255),
                outline=(70, 110, 190) if focus else (160, 160, 160))
    d.text((ex0 + 7, ey + 5), "•" * len(typed), font=ui, fill=(30, 30, 30))
    if focus:
        cx = ex0 + 9 + d.textlength("•" * len(typed), font=ui)
        d.line([cx, ey + 5, cx, ey + 21], fill=(30, 30, 30))

    by = y1 - 66
    for label, bx, strong in (("Cancel", x1 - 212, False), ("Save", x1 - 112, True)):
        d.rectangle([bx, by, bx + 90, by + 28],
                    fill=(225, 235, 250) if strong else (232, 232, 232),
                    outline=(140, 150, 165))
        d.text((bx + (90 - d.textlength(label, font=ui)) / 2, by + 6),
               label, font=ui, fill=(20, 20, 20))

    d.text((tx, y1 - 28), "What you type here does not enter the conversation.",
           font=ui_s, fill=(130, 130, 130))


def add(img, ms: int) -> None:
    frames.append(img)
    durations.append(ms)


def type_line(lines, text, color, font, prefix="", speed=3, ms=38, dialog=None):
    """Append frames that type `text` after `prefix` on a new line."""
    for i in range(0, len(text) + 1, speed):
        add(render(lines + [(prefix + text[:i], color, font)], dialog, cursor=True), ms)
    return lines + [(prefix + text, color, font)]


def hold(lines, ms, dialog=None, cursor=False):
    add(render(lines, dialog, cursor), ms)


# --------------------------------------------------------------------- script

L = []

# ---- beat 1: the agent needs a credential
L = type_line(L, "claude", WHITE, f, prefix="$ ")
hold(L, 300)
L = type_line(L, "run the pending EF migration against staging", GRAY, f, prefix="> ")
hold(L, 500)

L = L + [("", WHITE, f)]
L = L + [("● I need the staging database password. Opening a dialog —", BLUE, f)]
hold(L, 450)
L = L + [("  the value goes straight to your vault, I won't see it.", BLUE, f)]
hold(L, 700)
L = L + [("", WHITE, f)]
L = L + [("● Bash(vault need STAGING_DB_PASSWORD)", WHITE, fb)]
hold(L, 700)

# ---- beat 2: the human types into a dialog the agent cannot see
for n in (0, 3, 6, 9, 12, 15, 18):
    hold(L, 110, dialog=("x" * n,))
hold(L, 900, dialog=("x" * 18,))

L = L + [("  Stored “STAGING_DB_PASSWORD” (keyring).", GREEN, f)]
hold(L, 800)

# ---- beat 3: it works, and the value stays out of the transcript
L = L + [("", WHITE, f)]
L = type_line(L, "● Bash(vault run STAGING_DB_PASSWORD -- dotnet ef database update)",
             WHITE, fb, speed=4, ms=26)
hold(L, 400)
L = L + [("  Applying migration '20261113_AddContracts' ... Done.", GRAY, f)]
hold(L, 1500)

# ---- beat 4: the agent tries to read the value, and is stopped
L = L + [("", WHITE, f)]
L = type_line(L, "# and if the agent tries to read the value?", GRAY, f,
              prefix="$ ", speed=3, ms=30)
hold(L, 500)
L = L + [("", WHITE, f)]
L = type_line(L, "● Bash(vault get STAGING_DB_PASSWORD)", WHITE, fb, speed=3, ms=32)
hold(L, 600)
L = L + [("  [claude-vault] Blocked.", RED, fb)]
hold(L, 450)
L = L + [("  `vault get` prints a secret value into the transcript.", RED, f)]
hold(L, 250)
L = L + [("  Use `vault run <NAME> -- <your command>` instead.", RED, f)]
hold(L, 2000)

# ---- beat 5: the scrubber, on real verbose output
L2 = [("$ vault run STRIPE_SECRET_KEY -- curl -v https://api.stripe.com/v1/charges",
       WHITE, f)]
L2 = [(l[0][:88], l[1], l[2]) for l in L2]
add(render(L2), 700)
L2 = L2 + [("", WHITE, f)]
L2 = L2 + [("> POST /v1/charges HTTP/2", GRAY, f)]
add(render(L2), 350)
L2 = L2 + [("> Authorization: Bearer ", GRAY, f)]
add(render(L2), 250)


def with_redaction(base_lines, tail):
    img = base()
    d = ImageDraw.Draw(img)
    y = PAD_Y
    for text, color, font in base_lines[:-1]:
        d.text((PAD_X, y), text, font=font, fill=color)
        y += LH
    text, color, font = base_lines[-1]
    d.text((PAD_X, y), text, font=font, fill=color)
    d.text((PAD_X + d.textlength(text, font=font), y), tail, font=fb, fill=GOLD)
    return img


for i in range(0, len("***REDACTED:STRIPE_SECRET_KEY***") + 1, 4):
    add(with_redaction(L2, "***REDACTED:STRIPE_SECRET_KEY***"[:i]), 45)
add(with_redaction(L2, "***REDACTED:STRIPE_SECRET_KEY***"), 2200)

# ---- end card
end = base()
d = ImageDraw.Draw(end)
d.text((PAD_X + 10, 150), "claude-vault", font=title_f, fill=WHITE)
d.text((PAD_X + 10, 196), "Your coding agent knows the name of your password.",
       font=sub_f, fill=GRAY)
d.text((PAD_X + 10, 220), "Never the value.", font=sub_f, fill=GOLD)
for i, line in enumerate([
    "env injection + output scrubbing   ·   native prompt, out of band",
    "config templates that stay in git  ·   PreToolUse guard hook",
]):
    d.text((PAD_X + 10, 278 + i * 24), line, font=ui, fill=GRAY)
d.text((PAD_X + 10, 360), f"github.com/{USER}/claude-vault", font=ui_b, fill=BLUE)
d.text((PAD_X + 10, 390), "MIT  ·  en · fa · ar · fr · tr · es", font=ui_s, fill=GRAY)
add(end, 3200)

# --------------------------------------------------------------------- save

pal = frames[0].convert("P", palette=Image.ADAPTIVE, colors=200)
conv = [im.convert("RGB").quantize(palette=pal, dither=Image.NONE) for im in frames]
conv[0].save(
    OUT,
    save_all=True, append_images=conv[1:], duration=durations,
    loop=0, optimize=True, disposal=2,
)
print(f"frames={len(frames)} total={sum(durations)/1000:.1f}s")
