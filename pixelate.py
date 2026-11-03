import argparse, os, struct, subprocess, sys, tempfile, zlib


def read_png(path):
    """Decode a non-interlaced PNG into (w, h, rows of (r, g, b, a))."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte, trns = 8, b"", None, None
    while pos < len(data):
        n, t = struct.unpack(">I4s", data[pos:pos + 8])
        d = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if t == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", d)
        elif t == b"PLTE":
            plte = [tuple(d[i:i + 3]) for i in range(0, len(d), 3)]
        elif t == b"tRNS":
            trns = d
        elif t == b"IDAT":
            idat += d
        elif t == b"IEND":
            break
    if interlace:
        raise ValueError("interlaced PNGs are not supported")
    if depth not in (8, 16) and not (ctype == 3 and depth in (1, 2, 4)):
        raise ValueError(f"unsupported bit depth {depth} for color type {ctype}")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, channels * depth // 8)
    stride = (w * channels * depth + 7) // 8
    raw = zlib.decompress(idat)

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

    prev = bytearray(stride)
    out = []
    for y in range(h):
        i = y * (stride + 1)
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4: line[x] = (line[x] + paeth(a, b, c)) & 255
        prev = line

        if depth == 16:
            samples = line[::2]  # keep the high byte
        elif depth == 8:
            samples = line
        else:
            per = 8 // depth
            mask = (1 << depth) - 1
            samples = [(line[k // per] >> (8 - depth * (k % per + 1))) & mask for k in range(w)]

        row = []
        for x in range(w):
            s = samples[x * channels:(x + 1) * channels]
            if ctype == 0:
                px = (s[0], s[0], s[0], 255)
            elif ctype == 2:
                px = (*s, 255)
            elif ctype == 3:
                idx = s[0]
                alpha = trns[idx] if trns and idx < len(trns) else 255
                px = (*plte[idx], alpha)
            elif ctype == 4:
                px = (s[0], s[0], s[0], s[1])
            else:
                px = tuple(s)
            row.append(px)
        out.append(row)
    return w, h, out


def load_image(path):
    """Load a PNG directly; convert anything else to PNG first via macOS sips."""
    try:
        return read_png(path)
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        tmp_png = os.path.join(tmp, "in.png")
        try:
            subprocess.run(["sips", "-s", "format", "png", path, "--out", tmp_png],
                           check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            sys.exit(f"can't read {path}: only PNG is supported without macOS sips")
        return read_png(tmp_png)


N = 32  # sprite size, same as make_avatar.py
R = 4   # analysis pixels per sprite cell
NA = N * R


def downscale(w, h, px, box, size):
    """Box-average the square box (x0, y0, side) of the source to size x size. Outside the image is transparent."""
    x0, y0, side = box
    cell = side / size
    step = max(1, int(cell / 4))  # subsample big cells; plenty for averaging
    grid = []
    for gy in range(size):
        ya, yb = int(y0 + gy * cell), max(int(y0 + (gy + 1) * cell), int(y0 + gy * cell) + 1)
        row = []
        for gx in range(size):
            xa, xb = int(x0 + gx * cell), max(int(x0 + (gx + 1) * cell), int(x0 + gx * cell) + 1)
            r = g = b = a = n = 0
            for y in range(ya, yb, step):
                for x in range(xa, xb, step):
                    n += 1
                    if 0 <= x < w and 0 <= y < h:
                        pr, pg, pb, pa = px[y][x]
                        r += pr * pa; g += pg * pa; b += pb * pa; a += pa
            row.append((r // a, g // a, b // a, a // n) if a else (0, 0, 0, 0))
        grid.append(row)
    return grid


def dist(c1, c2):
    return sum((c1[i] - c2[i]) ** 2 for i in range(3)) ** 0.5


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def neighbors4(x, y, n):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= x + dx < n and 0 <= y + dy < n:
            yield x + dx, y + dy


def subject_mask(grid, has_alpha):
    """True where the subject is: alpha if the image has it, else flood the background in from the edges.
    Keeps only the largest blob so stray specks don't skew the measurements."""
    n = len(grid)
    if has_alpha:
        fg = [[c[3] >= 128 for c in row] for row in grid]
    else:
        # Background colors: whatever dominates a band along the top and upper sides (the bottom is
        # usually the subject). A band rather than the edge row copes with framed photos.
        band = n // 8
        border = [grid[y][x][:3] for y in range(n // 2) for x in range(n)
                  if (y < band or x < band or x >= n - band) and grid[y][x][3] >= 128]
        bins = {}
        for c in border:
            bins.setdefault(tuple(v // 32 for v in c), []).append(c)
        bg_colors = [tuple(sum(c[i] for c in cs) // len(cs) for i in range(3))
                     for cs in bins.values() if len(cs) >= 0.1 * len(border)]

        def is_bg(c):
            return c[3] < 128 or any(dist(c[:3], b) < 40 for b in bg_colors)

        bg = [[False] * n for _ in range(n)]
        stack = [(x, y) for y in range(n) for x in range(n)
                 if (x in (0, n - 1) or y in (0, n - 1)) and is_bg(grid[y][x])]
        while stack:
            x, y = stack.pop()
            if bg[y][x]:
                continue
            bg[y][x] = True
            stack += [(a, b) for a, b in neighbors4(x, y, n) if not bg[b][a] and is_bg(grid[b][a])]
        fg = [[not v for v in row] for row in bg]

    # Open (erode then dilate) to drop thin lines like photo frame edges that touch the subject.
    for keep in (all, any):
        fg = [[keep(fg[yy][xx] for yy in range(max(0, y - 1), min(n, y + 2)) for xx in range(max(0, x - 1), min(n, x + 2)))
               for x in range(n)] for y in range(n)]

    seen, best = set(), []
    for y in range(n):
        for x in range(n):
            if fg[y][x] and (x, y) not in seen:
                blob, stack = [], [(x, y)]
                seen.add((x, y))
                while stack:
                    p = stack.pop()
                    blob.append(p)
                    for q in neighbors4(*p, n):
                        if fg[q[1]][q[0]] and q not in seen:
                            seen.add(q)
                            stack.append(q)
                if len(blob) > len(best):
                    best = blob
    if not best:
        sys.exit("no subject found in image")
    mask = [[False] * n for _ in range(n)]
    for x, y in best:
        mask[y][x] = True
    return mask


def measure(mask):
    """Read the silhouette top-down: head top, widest point, chin, neck, shoulders (analysis pixels)."""
    n = len(mask)
    spans = []
    for row in mask:
        xs = [x for x, v in enumerate(row) if v]
        spans.append((xs[0], xs[-1]) if xs else None)
    half = [(s[1] - s[0] + 1) / 2 if s else 0 for s in spans]
    rows = [y for y in range(n) if half[y] >= 2]
    top, bottom = rows[0], rows[-1]

    head_half, head_y, narrow = 0, top, None
    for y in range(top, bottom + 1):
        if half[y] > head_half:
            head_half, head_y = half[y], y
        elif half[y] < 0.8 * head_half:
            narrow = y
            break

    neck_half, neck_y, shoulder = head_half * 0.4, None, None
    if narrow is None:
        chin = bottom  # head fills the frame, no neck in view
    else:
        neck_half, neck_y = half[narrow], narrow
        for y in range(narrow, bottom + 1):
            if half[y] < neck_half:
                neck_half, neck_y = half[y], y
            if half[y] > neck_half * 1.4 + R:
                shoulder = y
                break
        chin = next(y for y in range(head_y, neck_y + 1) if half[y] <= neck_half * 1.25 + R / 2)
    mids = [(spans[y][0] + spans[y][1] + 1) / 2 for y in range(top, chin + 1) if spans[y]]
    return {"top": top, "chin": chin, "head_half": head_half, "neck_half": neck_half,
            "shoulder": shoulder, "half": half, "cx": sum(mids) / len(mids)}


class Photo:
    """The analysis grid plus helpers to sample it in sprite-cell coordinates (row, distance from center line)."""

    def __init__(self, grid, mask, cx):
        self.grid, self.mask, self.cx = grid, mask, cx

    def pixels(self, y0, y1, d0, d1):
        out = []
        for y in range(max(0, int(y0 * R)), min(NA, int((y1 + 1) * R))):
            for x in range(NA):
                d = abs(x + 0.5 - self.cx) / R
                if d0 <= d < d1 and self.mask[y][x]:
                    out.append(self.grid[y][x][:3])
        return out

    def color(self, *region):
        pix = self.pixels(*region)
        if not pix:
            return None
        return tuple(sorted(p[i] for p in pix)[len(pix) // 2] for i in range(3))


def find_eyes(grid, mask, top, cx, half):
    """Eyes are the darkest band across the upper-middle face; returns (row, distance from center), analysis px."""
    n = len(grid)

    def band(y, d0, d1):
        pix = [grid[y][x][:3] for x in range(n) if mask[y][x] and d0 <= abs(x + 0.5 - cx) < d1]
        return sum(map(lum, pix)) / len(pix) if pix else 255

    lo, hi = int(top + 0.8 * half), min(n - 2, int(top + 1.8 * half))
    rows = {y: band(y, 0.2 * half, 0.75 * half) for y in range(lo, hi + 1)}
    y = min(range(lo + 1, hi), key=lambda y: rows[y - 1] + rows[y] + rows[y + 1])
    ds = range(int(0.2 * half), int(0.75 * half))
    d = min(ds, key=lambda d: sum(band(yy, d, d + 1) for yy in range(y - 1, y + 2)))
    return y, d + 0.5


def analyze(w, h, px):
    """Two passes: find the head and eyes in the whole photo, then re-crop so the head top and eyes
    land on the same rows as in make_avatar's sprite (top at row 2, eyes at row 12)."""
    # Trust alpha only for real cutouts, not images with a thin transparent border.
    samples = [px[y][x][3] < 128 for y in range(0, h, 7) for x in range(0, w, 7)]
    has_alpha = sum(samples) / len(samples) > 0.1
    side = min(w, h)
    box = ((w - side) / 2, (h - side) / 2, side)
    grid = downscale(w, h, px, box, NA)
    mask = subject_mask(grid, has_alpha)
    m = measure(mask)
    eye_y, _ = find_eyes(grid, mask, m["top"], m["cx"], m["head_half"])
    scale = box[2] / NA
    side = max(eye_y - m["top"], 1) * scale * N / 10
    box = (box[0] + m["cx"] * scale - side / 2, box[1] + m["top"] * scale - side * 2 / N, side)

    grid = downscale(w, h, px, box, NA)
    mask = subject_mask(grid, has_alpha)
    m = measure(mask)
    m["eye"], m["eye_d"] = find_eyes(grid, mask, m["top"], m["cx"], m["head_half"])
    return Photo(grid, mask, m["cx"]), m


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def features(photo, m, opts):
    """Turn measurements into sprite-cell geometry and decide which features to draw."""
    f = {}
    f["top"] = top = clamp(round(m["top"] / R), 1, 3)
    f["eye"] = eye = clamp(round(m["eye"] / R - 0.5), top + 9, top + 11)
    f["chin"] = chin = clamp(round(m["chin"] / R), eye + 9, eye + 11)
    f["hw"] = hw = clamp(m["head_half"] / R * 1.1, 9.0, 12.5)  # cartoon heads are a bit wider than real ones
    f["eo"] = eo = clamp(int(m["eye_d"] / R) + 1.5, 4.5, int(0.7 * hw) + 0.5)  # outer eye column
    f["neck"] = neck = clamp(round(m["neck_half"] / R * 0.8), 3, 5)
    # The cartoon face is shorter than a real one, so shoulders sit just below the cartoon chin (as in
    # make_avatar) and only their width comes from the photo.
    f["shoulder"] = sh = chin + 3
    full = clamp(max(m["half"][-R:]) / R, neck + 7, N / 2) if m["shoulder"] else N / 2
    f["sw"] = {y: clamp(neck + 6 + 1.5 * (y - sh), neck + 4, full) for y in range(sh, N)}

    forehead = photo.pixels(eye - 4, eye - 3, 0, 2)
    cheeks = photo.pixels(eye + 2, eye + 3, eo - 1, eo + 1)
    pix = forehead + cheeks
    skin = tuple(sorted(p[i] for p in pix)[len(pix) // 2] for i in range(3)) if pix else (201, 138, 94)
    # The photo keeps real proportions, so lower-face features are found relative to an estimated photo chin.
    photo_chin = eye + 1.35 * (eye - top)
    crown = photo.color(top + 1, top + 1, 0, hw * 0.4)
    # Just inside the silhouette edge beside the forehead, clear of any background halo.
    temple_pix = [photo.grid[y][x][:3] for y in range((top + 2) * R, (eye - 3) * R) for x in range(NA)
                  if photo.mask[y][x] and R <= m["half"][y] - abs(x + 0.5 - photo.cx) < 2.5 * R]
    temples = tuple(sorted(p[i] for p in temple_pix)[len(temple_pix) // 2] for i in range(3)) if temple_pix else None
    hair = max((c for c in (photo.color(top, top, 0, hw * 0.4), crown, temples) if c), key=lambda c: dist(c, skin), default=None)
    beard = photo.color(round(photo_chin) - 3, round(photo_chin) - 1, 0, hw * 0.3)
    brow = photo.color(eye - 2, eye - 1, eo - 1.5, eo + 0.5)
    shirt = photo.color(N - 2, N - 1, neck + 3, f["sw"][N - 1] - 2)
    pick = lambda flag, auto: auto if flag is None else flag

    f["hair"] = pick(opts.hair, bool(hair) and dist(hair, skin) > 45)
    if f["hair"]:
        # Hairline: first row down the middle that looks like skin.
        line = next((y for y in range(top + 1, eye - 2)
                     if (c := photo.color(y, y, 0, 2)) and dist(c, skin) < 40), top + 6)
        f["hairline"] = clamp(line, top + 2, eye - 4)
        f["sideburns"] = bool(temples) and dist(temples, skin) > 45
    f["beard"] = pick(opts.beard, bool(beard) and dist(beard, skin) > 22 and lum(beard) < lum(skin))

    # Teeth: a band of bright, low-color pixels below the nose.
    def whiteness(y):
        pix = photo.pixels(y, y, 0, 3)
        white = [p for p in pix if lum(p) > lum(skin) * 1.15 and max(p) - min(p) < 70]
        return len(white) / len(pix) if pix else 0
    teeth_y = max(range(eye + round(0.4 * (photo_chin - eye)), eye + round(0.8 * (photo_chin - eye)) + 1), key=whiteness)
    f["teeth"] = pick(opts.teeth, whiteness(teeth_y) > 0.1)
    f["mouth"] = min(eye + 5, chin - 4)

    # Glasses: a dark bridge between the eyes, compared with the forehead.
    bridge = min((photo.pixels(y, y, 0, 1) for y in range(eye - 2, eye + 1)),
                 key=lambda p: sum(map(lum, p)) / len(p) if p else 255)
    ratio = (sum(map(lum, bridge)) / len(bridge)) / (sum(map(lum, forehead)) / len(forehead)) if bridge and forehead else 1
    f["glasses"] = pick(opts.glasses, ratio < 0.5)

    def tone(c, k):
        return tuple(clamp(round(v * k), 0, 255) for v in c)

    def mix(a, b, t):
        return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))

    hair_c = hair if f["hair"] else tone(brow or skin, 0.6)
    brow_c = hair_c if f["hair"] and lum(hair_c) < 100 else tone(brow or skin, 0.55)
    shirt_c = shirt or (238, 241, 245)
    f["palette"] = {
        "K": (tone(mix(hair_c, (43, 29, 22), 0.6), 0.8), "outline"),
        "H": (hair_c, "hair"),
        "N": (brow_c, "eyebrows"),
        "h": (mix(hair_c, (255, 255, 255), 0.2), "hair highlight"),
        "S": (skin, "skin"),
        "s": (tone(skin, 0.84), "skin shadow"),
        "L": (mix(skin, (255, 255, 255), 0.25), "skin highlight"),
        "E": ((30, 19, 15), "eye"),
        "W": ((255, 255, 255), "eye shine"),
        "B": (mix(skin, (232, 120, 110), 0.6), "blush"),
        "M": (mix(tone(skin, 0.6), (140, 45, 45), 0.5), "lips / mouth"),
        "T": ((246, 236, 220), "teeth"),
        "G": (beard if f["beard"] else skin, "beard"),
        "R": ((62, 56, 60), "glasses"),
        "w": (shirt_c, "shirt"),
        "g": (tone(shirt_c, 0.84), "shirt shadow"),
    }
    return f


def draw(f):
    """Paint the sprite from simple shapes, the way make_avatar's LEFT is laid out by hand."""
    D = [abs(x + 0.5 - N / 2) for x in range(N)]  # distance of each column from the mirror line
    top, chin, hw, eye, mouth, eo, neck = f["top"], f["chin"], f["hw"], f["eye"], f["mouth"], f["eo"], f["neck"]
    c, ry = (top + chin + 1) / 2, (chin + 1 - top) / 2

    def head_w(y):
        if not top <= y <= chin:
            return -1
        t = abs(y + 0.5 - c) / ry
        p = 3.0 if y + 0.5 < c else 2.2  # boxier cranium, rounder jaw
        return hw * (1 - t ** p) ** (1 / p)

    part = {}  # (x, y) -> part name
    fill = {}  # (x, y) -> palette char
    sh = f["shoulder"]
    if True:
        for y in range(sh, N):
            for x in range(N):
                if D[x] < f["sw"][y]:
                    part[x, y], fill[x, y] = "shirt", "g" if D[x] > f["sw"][y] - 2 else "w"
    for y in range(chin - 1, (sh + 2) if sh else N):
        for x in range(N):
            if D[x] < neck - (1 if sh and y == sh + 1 else 0) and not (sh and y >= sh + 2):
                part[x, y], fill[x, y] = "neck", "s" if y == chin + 1 else "S"
    if sh:  # collar around the neck
        for y, lo, hi in ((sh, neck - 1, neck + 1), (sh + 1, neck - 2, neck), (sh + 2, 0, neck - 1)):
            for x in range(N):
                if lo <= D[x] < hi and part.get((x, y)) in ("shirt", "neck"):
                    part[x, y], fill[x, y] = "shirt", "g"
    ear_w = {-1: 2, 0: 3, 1: 3, 2: 3, 3: 2, 4: 1}
    for k, e in ear_w.items():
        y = eye + k
        for x in range(N):
            if head_w(y) < D[x] <= head_w(y) + e:
                part[x, y], fill[x, y] = "ear", "s" if k in (1, 2) and D[x] <= head_w(y) + 1 else "S"
    for y in range(top, chin + 1):
        for x in range(N):
            if D[x] <= head_w(y):
                part[x, y], fill[x, y] = "head", "S"

    def paint(y, d_test, ch, only_head=True):
        for x in range(N):
            if d_test(D[x]) and (not only_head or part.get((x, y)) == "head"):
                fill[x, y] = ch

    # Hair or a bald-head shine, then the forehead highlight.
    if f["hair"]:
        for y in range(top, f["hairline"]):
            paint(y, lambda d: True, "H")
        # Sideburns, if the photo has hair beside the forehead.
        for k, y in enumerate(range(f["hairline"], eye if f["sideburns"] else f["hairline"])):
            depth = max(1, 3 - k)
            paint(y, lambda d, y=y, depth=depth: d > head_w(y) - 1 - depth, "H")
        paint(f["hairline"], lambda d: d < 3, "L")
    else:
        paint(top + 1, lambda d: 1 <= d < 4, "L")
        paint(top + 2, lambda d: 2 <= d < 3, "L")

    if f["beard"]:
        for y in range(mouth - 1, chin + 1):
            paint(y, lambda d, y=y: y >= mouth + 3 or d >= 4.5 or y <= mouth, "G")
    else:
        paint(chin, lambda d: True, "s")

    paint(eye - 2, lambda d: eo - 2 <= d <= eo, "N")             # eyebrows
    paint(eye, lambda d: eo - 1 <= d <= eo, "E")                 # eyes
    paint(eye + 1, lambda d: eo - 1 <= d <= eo, "E")
    paint(eye, lambda d: d == eo - 1, "W")                       # shine (inner side; right eye fixed below)
    blush = eye + (3 if f["glasses"] else 2)
    paint(blush, lambda d: eo + 1 <= d <= eo + 2, "B")
    paint(eye + 1, lambda d: d < 1, "L")                          # nose
    paint(eye + 2, lambda d: d < 1, "s")
    paint(eye + 3, lambda d: d < 2, "s")
    if f["teeth"]:                                                # smile
        paint(mouth, lambda d: d == 4.5, "M")
        paint(mouth, lambda d: d < 4.5, "S" if not f["beard"] else "G")
        paint(mouth + 1, lambda d: d == 3.5, "M")
        paint(mouth + 1, lambda d: d < 3, "T")
        paint(mouth + 2, lambda d: d < 3, "M")
    else:
        paint(mouth, lambda d: d == 3.5, "M")
        paint(mouth + 1, lambda d: d < 3, "M")

    if f["glasses"]:
        for y in range(eye - 1, eye + 3):
            edge = y in (eye - 1, eye + 2)
            paint(y, lambda d, edge=edge: (eo - 2 <= d <= eo + 1) if edge else d in (eo - 2, eo + 1), "R")
        paint(eye, lambda d, y=eye: d < eo - 2 or eo + 1 < d < head_w(y) - 0.5, "R")  # bridge and arms

    # Outline: anything touching the background, plus the seam where ears meet the head.
    rows = [["."] * N for _ in range(N)]
    for (x, y), ch in fill.items():
        rows[y][x] = ch
    for (x, y), p in part.items():
        nbrs = [part.get(q) for q in neighbors4(x, y, N)]
        if None in nbrs or (p == "head" and "ear" in nbrs):
            rows[y][x] = "K"

    # Asymmetric touches: eye shine on the same side for both eyes, and a hair highlight swoop.
    overrides = []
    ex = int(N / 2 + eo - 1)  # right eye's inner column
    overrides += [(eye, ex, "E"), (eye, ex + 1, "W")]
    if f["hair"]:
        mid = N // 2
        overrides += [(top + 1, mid - 3, "h"), (top + 2, mid - 4, "h"), (top + 2, mid - 5, "h"), (top + 3, mid - 6, "h")]
        overrides = [o for o in overrides if rows[o[0]][o[1]] == "H" or o[2] != "h"]
    return ["".join(r[:N // 2]) for r in rows], overrides


def png(path, rows, scale, bg):
    n = len(rows)
    raw = b""
    for r in rows:
        line = b""
        for c in r:
            if c is None:
                px = bytes(bg) if bg else b"\x00\x00\x00\x00"
            else:
                px = bytes(c) + (b"\xff" if bg is None else b"")
            line += px * scale
        line = b"\x00" + line
        raw += line * scale
    ctype = 6 if bg is None else 2

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", n * scale, n * scale, 8, ctype, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9))
    data += chunk(b"IEND", b"")
    open(path, "wb").write(data)


def sprite_code(left, palette, overrides, bg):
    """Emit LEFT / PALETTE / BG / overrides in the same shape as make_avatar.py."""
    used = {ch for r in left for ch in r} | {ch for _, _, ch in overrides}
    out = [f"# Left half of a {N}x{N} sprite ({N // 2} cols); mirrored to make the right half.", "LEFT = ["]
    out += [f'    "{r}",' for r in left]
    out += ["]", "", "PALETTE = {"]
    out += [f'    "{ch}": {col},{" " * (16 - len(str(col)))}# {note}'
            for ch, (col, note) in palette.items() if ch in used]
    out += ["}", f"BG = {bg}", "", "# Asymmetric touches: eye shine on the same side for both eyes, hair highlight."]
    out += [f'rows[{y}][{x}] = "{ch}"' for y, x, ch in overrides]
    return "\n".join(out) + "\n"


def hex_color(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


ap = argparse.ArgumentParser(description="Turn a portrait photo into a cartoon 32x32 sprite in the style of make_avatar.py.")
ap.add_argument("image")
ap.add_argument("out_dir", nargs="?", help="output directory (default: ./<name>, created if needed)")
ap.add_argument("--scale", type=int, default=32, help="upscale factor for large outputs (default 32)")
ap.add_argument("--bg", type=hex_color, default=hex_color("bfe3d6"), help="background hex for the opaque output (default bfe3d6)")
ap.add_argument("--name", help="output file prefix and default directory name (default: input file name)")
for feat in ("hair", "beard", "glasses", "teeth"):
    ap.add_argument(f"--{feat}", action=argparse.BooleanOptionalAction, default=None,
                    help=f"force {feat} on or off (default: detect from the photo)")
args = ap.parse_args()

w, h, px = load_image(args.image)
photo, m = analyze(w, h, px)
f = features(photo, m, args)
left, overrides = draw(f)
rows = [list(r + r[::-1]) for r in left]
for y, x, ch in overrides:
    rows[y][x] = ch

detected = ", ".join(k for k in ("hair", "beard", "glasses", "teeth") if f[k]) or "none"
print(f"# features: {detected}", file=sys.stderr)
name = args.name or os.path.splitext(os.path.basename(args.image))[0]
out = args.out_dir or name
os.makedirs(out, exist_ok=True)
code = sprite_code(left, f["palette"], overrides, args.bg)
open(f"{out}/{name}-sprite.py", "w").write(code)
print(code)
pal = {ch: col for ch, (col, _) in f["palette"].items()}
colored = [[None if ch == "." else pal[ch] for ch in r] for r in rows]
png(f"{out}/{name}-pixel.png", colored, args.scale, args.bg)
png(f"{out}/{name}-pixel-transparent.png", colored, args.scale, None)
png(f"{out}/{name}-pixel-{N}.png", colored, 1, None)
