import struct, zlib, sys

# Left half of a 32x32 sprite (16 cols); mirrored to make the right half.
LEFT = [
    "................",
    "................",
    "..........KKKKKK",
    "........KKHHHHHH",
    ".......KHHHhHHHH",
    "......KHHhHHHHHH",
    ".....KHHHHHHHHHH",
    ".....KHHHHHHHHHH",
    ".....KHHHSSSSLLL",
    ".....KHHSSSSSSSS",
    ".....KHSSHHHSSSS",
    "...KKKHSSSSSSSSS",
    "..KSSKSSSEWSSSSS",
    "..KSsKSSSEESSSSL",
    "..KSsKSBBSSSSSSs",
    "...KSKSSSSSSSSss",
    "....KKSSSSSSSSSS",
    ".....KGSSSSMSSSS",
    ".....KGGSSSSMTTT",
    "......KGGSSSSMMM",
    "......KGGGGGGGGG",
    ".......KGGGGGGGG",
    "........KKGGGGGG",
    "..........KKKsss",
    "............KSSS",
    "......KKKKKKgsSS",
    "....KKwwwwwwwgss",
    "...Kwwwwwwwwwwgg",
    "..Kgwwwwwwwwwwww",
    "..Kgwwwwwwwwwwww",
    ".Kggwwwwwwwwwwww",
    ".Kggwwwwwwwwwwww",
]

PALETTE = {
    "K": (43, 29, 22),     # outline
    "H": (46, 35, 32),     # hair
    "h": (84, 66, 58),     # hair highlight
    "S": (201, 138, 94),   # skin
    "s": (169, 109, 71),   # skin shadow
    "L": (226, 168, 124),  # skin highlight
    "E": (30, 19, 15),     # eye
    "W": (255, 255, 255),  # eye shine
    "B": (228, 128, 110),  # blush
    "M": (130, 62, 55),    # lips / mouth
    "T": (246, 236, 220),  # teeth
    "G": (181, 124, 88),   # stubble
    "w": (238, 241, 245),  # shirt
    "g": (196, 204, 214),  # shirt shadow
}
BG = (191, 227, 214)  # pastel mint

rows = []
for r in LEFT:
    assert len(r) == 16, (r, len(r))
    rows.append(list(r + r[::-1]))

# Asymmetric touches: eye shine on the same side for both eyes, side-swept hair.
rows[12][21], rows[12][22] = "E", "W"
rows[4][20] = "H"; rows[5][22] = "H"
rows[3][13] = "h"; rows[4][12] = "h"
rows[8][10] = "S"


def png(path, scale, bg):
    n = len(rows)
    raw = b""
    for r in rows:
        line = b""
        for ch in r:
            if ch == ".":
                px = bytes(bg) if bg else b"\x00\x00\x00\x00"
            else:
                c = PALETTE[ch]
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


out = sys.argv[1]
png(f"{out}/parag-pixel.png", 32, BG)
png(f"{out}/parag-pixel-transparent.png", 32, None)
png(f"{out}/parag-pixel-32.png", 1, None)
