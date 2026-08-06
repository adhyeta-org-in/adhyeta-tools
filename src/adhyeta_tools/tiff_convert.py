from pathlib import Path

import pyvips


def process(args):
    indir = args.input_dir.resolve()
    outdir = args.output_dir.resolve()
    outdir.mkdir(exist_ok=True)

    for tif in sorted(p for p in indir.iterdir() if p.is_file() and p.suffix.lower() in {".tif", ".tiff"}):
        _tiff_to_png(tif, outdir / (tif.stem + ".png"), args.max_width, args.crop)


def _tiff_to_png(
    src: Path,
    dst: Path,
    max_width: int,
    crop: int,
    compression: int = 6,
):
    img = pyvips.Image.new_from_file(
        str(src),
        access="sequential",
    )

    #
    # Restrict width (never upscale)
    #
    if max_width is not None and img.width > max_width:
        scale = max_width / img.width
        img = img.resize(scale, kernel="lanczos3")

    #
    # Centre crop
    #
    if crop > 0:
        w = max(1, img.width - 2 * crop)
        h = max(1, img.height - 2 * crop)

        img = img.crop(
            crop,
            crop,
            w,
            h,
        )

    img.pngsave(
        str(dst),
        compression=compression,
        interlace=False,
    )
