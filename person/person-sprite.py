# Left half of a 32x32 sprite (16 cols); mirrored to make the right half.
LEFT = [
    "................",
    "................",
    "...........KKKKK",
    "........KKKHHHHH",
    ".......KSSSSSLLL",
    ".......KSSSSSSSS",
    "......KSSSSSSSSS",
    "......KSSSSSSSSS",
    "......KSSSSSSSSS",
    "......KSSSSSSSSS",
    "......KSSSSNNNSS",
    "....KKKSSSRRRRSS",
    "...KSSKRRRREWRRR",
    "...KSsKSSSREERSL",
    "...KSsKSSSRRRRSs",
    "....KKKSSBBSSSss",
    "......KKGGGGGGGG",
    ".......KGGGMGGGG",
    "........KGGGMTTT",
    ".........KGGSMMM",
    "..........KGGGGG",
    "...........KGGGG",
    "...........Kssss",
    "...........KSSSS",
    ".....KKKKKKgSSSS",
    "....KwwwwwwggSSS",
    "..KKwwwwwwwwgggg",
    ".Kwwwwwwwwwwwwww",
    ".Kwwwwwwwwwwwwww",
    ".Kwwwwwwwwwwwwww",
    ".Kwwwwwwwwwwwwww",
    ".Kwwwwwwwwwwwwww",
]

PALETTE = {
    "K": (58, 50, 46),    # outline
    "H": (118, 113, 113), # hair
    "N": (89, 61, 47),    # eyebrows
    "h": (145, 141, 141), # hair highlight
    "S": (217, 163, 130), # skin
    "s": (182, 137, 109), # skin shadow
    "L": (226, 186, 161), # skin highlight
    "E": (30, 19, 15),    # eye
    "W": (255, 255, 255), # eye shine
    "B": (226, 137, 118), # blush
    "M": (135, 72, 62),   # lips / mouth
    "T": (246, 236, 220), # teeth
    "G": (94, 59, 43),    # beard
    "R": (62, 56, 60),    # glasses
    "w": (217, 200, 187), # shirt
    "g": (182, 168, 157), # shirt shadow
}
BG = (191, 227, 214)

# Asymmetric touches: eye shine on the same side for both eyes, hair highlight.
rows[12][19] = "E"
rows[12][20] = "W"
rows[3][13] = "h"
