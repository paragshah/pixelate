# pixelate

A tiny, dependency-free Python script that generates a 32x32 pixel-art avatar and writes it out as PNG files.

![avatar](person.png)

## How it works

`make_avatar.py` defines the sprite as text:

- `LEFT` holds the left half of the sprite (32 rows of 16 characters). Each row is mirrored to build the full 32x32 image.
- A few cells are then overridden by hand to add asymmetric details (eye shine, side-swept hair).
- `PALETTE` maps each character to an RGB color (outline, hair, skin, eyes, shirt, and so on). `.` is background.
- `BG` is the background color used for the opaque version (pastel mint).

The PNG encoder is written by hand using only `struct` and `zlib` from the standard library, so no Pillow or other packages are required.

## Usage

Requires Python 3.6+.

```sh
python3 make_avatar.py <output-dir>
```

For example, to write into the current directory:

```sh
python3 make_avatar.py .
```

## Output

| File | Size | Background |
| --- | --- | --- |
| `parag-pixel.png` | 1024x1024 (32x scale) | Pastel mint |
| `parag-pixel-transparent.png` | 1024x1024 (32x scale) | Transparent |
| `parag-pixel-32.png` | 32x32 (1x scale) | Transparent |

`parag-template.png` is a high-resolution reference image and is not produced by the script.

## Customizing

- Edit the rows in `LEFT` to change the shape. Every row must be exactly 16 characters (the script asserts this).
- Add or change entries in `PALETTE` to adjust colors. Any character used in `LEFT` must have a palette entry.
- Change `BG` for a different background color.
- Adjust the `scale` arguments in the `png(...)` calls at the bottom of the script for other output sizes.

## Generating a sprite from any image

`pixelate.py` draws a cartoon avatar in the same style as `make_avatar.py` from a portrait photo. It does not pixelate the photo. Instead it measures the photo and draws clean, hand-style features from a template, generating `LEFT`, `PALETTE`, and the asymmetric overrides on the fly:

1. Find the subject (alpha cutout, or flood the background in from the edges) and locate the head top and eyes.
2. Re-crop so the head top and eyes land on the same rows as `make_avatar.py`'s sprite.
3. Measure head width, eye spacing, neck, and shoulders, and sample skin, hair, beard, eyebrow, and shirt colors.
4. Detect hair (and sideburns), beard, glasses, and a toothy smile.
5. Draw the head, ears, hair, eyebrows, eyes with shine, blush, nose, mouth, beard, glasses, neck, collar, and shirt, then outline everything in `K` and mirror it.

```sh
python3 pixelate.py photo.jpg [out-dir] [--scale 32] [--bg bfe3d6] [--name prefix]
                                [--hair|--no-hair] [--beard|--no-beard]
                                [--glasses|--no-glasses] [--teeth|--no-teeth]
```

Detection is heuristic, so the feature flags force a feature on or off when it guesses wrong. The detected features are printed to stderr.

It writes `<name>-pixel.png`, `<name>-pixel-transparent.png`, `<name>-pixel-32.png`, and `<name>-sprite.py`, which holds the generated `LEFT`, `PALETTE`, `BG`, and overrides in `make_avatar.py` format so you can hand-tune it. `<name>` defaults to the input file name. If `out-dir` is omitted, files go in `./<name>/`, which is created if needed. Requires Python 3.9+. PNG is decoded with the standard library; other formats (JPEG, HEIC, etc.) are converted with macOS `sips` first. Works best with a front-facing head-and-shoulders photo on a plain background.
