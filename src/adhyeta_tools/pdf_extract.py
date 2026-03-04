# SPDX-License-Identifier: MPL-2.0

import io
import math
from dataclasses import dataclass
from multiprocessing import cpu_count, get_context
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz
from PIL import Image


@dataclass
class ImageConfig:
    dpi: int
    max_width: int
    crop: int


def text_detection(pil_img_rgb, page_num):
    """
    MSER text detection: Find text blobs, blackout everything else.
    Reliable for yellowed magazines.
    """
    try:
        print(f"Page {page_num}: MSER text detection...")
        opencv_img = cv2.cvtColor(np.array(pil_img_rgb), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(opencv_img, cv2.COLOR_BGR2GRAY)

        # Enhance contrast for yellowed paper
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # MSER text detection
        mser = cv2.MSER_create()
        regions, bboxes = mser.detectRegions(enhanced)

        # Create text mask
        text_mask = np.zeros_like(enhanced)
        for region in regions:
            # Filter reasonable text blob sizes
            x, y, w, h = cv2.boundingRect(region)
            aspect_ratio = w / float(h)
            if (
                20 < w < 1200 and 10 < h < 100 and 0.2 < aspect_ratio < 3.0 and len(region) > 30
            ):  # Enough pixels for text
                cv2.rectangle(text_mask, (x, y), (x + w, y + h), 255, -1)

        # Morphology to connect letters → words
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        # Blackout non-text areas
        result = cv2.bitwise_and(enhanced, enhanced, mask=text_mask)
        result_img = Image.fromarray(result, "L")

        coverage = np.sum(text_mask > 0) / text_mask.size
        print(f"Page {page_num}: Text coverage {coverage:.1%}")

    except ImportError:
        print(f"Page {page_num}: opencv-python missing")
        result_img = pil_img_rgb.convert("L")

    return result_img


def adaptive_change(pil_img):
    img_array = np.array(pil_img)

    # Apply adaptive thresholding (better for pages with shadows)
    from skimage.filters import threshold_local

    block_size = 35  # Should be odd
    threshold = threshold_local(img_array, block_size, offset=10)
    binary_array = img_array > threshold

    # Convert boolean to uint8
    binary_array = (binary_array * 255).astype(np.uint8)

    return Image.fromarray(binary_array, mode="L")


def clahe(pil_img):
    # Convert to OpenCV format for advanced processing
    img_array = np.array(pil_img)

    # Convert to grayscale if not already
    if len(img_array.shape) == 3:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img_array = clahe.apply(img_array)

    # Denoise while preserving edges
    img_array = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)

    # Apply Otsu's thresholding
    _, img_array = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Optional: Morphological operations to clean up
    kernel = np.ones((1, 1), np.uint8)
    img_array = cv2.morphologyEx(img_array, cv2.MORPH_CLOSE, kernel)

    return Image.fromarray(img_array, mode="L")


def compute_tokens(pil_img):
    return math.ceil((pil_img.width / 32) * (pil_img.height / 32) + 2)


def process_pix_data(parent: str, page_num: int, img_data: bytearray, c: ImageConfig):
    pil_img = Image.open(io.BytesIO(img_data))

    pil_img = pil_img.crop(
        (
            c.crop,
            c.crop,
            pil_img.width - c.crop,
            pil_img.height - c.crop,
        )
    )

    # Resize while preserving aspect ratio
    if pil_img.width > c.max_width:
        ratio = c.max_width / pil_img.width
        new_height = int(pil_img.height * ratio)
        pil_img = pil_img.resize((c.max_width, new_height), Image.Resampling.LANCZOS)

    # Text detection
    # pil_img = text_detection(pil_img, page_num + 1)

    # Convert to grayscale (1 channel = fewer tokens)
    pil_img = pil_img.convert("L")
    pil_img = clahe(pil_img)

    # Save optimized PNG
    output_path = f"{parent}/{page_num + 1:03d}.png"
    pil_img.save(output_path, optimize=True, compress_level=9)

    print(f"Saved page {page_num + 1}: {pil_img.size}px ({compute_tokens(pil_img)} toks)")


def process_pix_data_simple(parent: str, page_num: int, img_data: bytearray, c: ImageConfig):
    pil_img = Image.open(io.BytesIO(img_data))
    output_path = f"{parent}/{page_num + 1:03d}.png"
    pil_img.save(output_path, optimize=True, compress_level=9)
    print(f"Saved page {page_num + 1}: {pil_img.size}px ({compute_tokens(pil_img)} toks)")


def parse_skip_pages(skip: str, max: int):
    """Convert '1,3-5,10,20-25' → set of 0-based page indices to DROP."""
    q = set()

    if not skip:
        return q

    for part in skip.split(","):
        part = part.strip()
        if part.endswith("-"):
            # Open-ended range: "57-" → 57 to end
            start = int(part[:-1])
            q.update(range(start, max + 1))
        elif "-" in part:
            # Range: "3-5"
            start, end = map(int, part.split("-"))
            q.update(range(start, end + 1))
        else:
            # Single: "1"
            q.add(int(part))

    return q


def process(args):
    c = ImageConfig(args.dpi, args.max_width, args.crop)

    file = args.input
    parent = str(Path(file).parent)

    doc = fitz.open(file)
    pages_n = len(doc)

    zoom_x = c.dpi / 72
    zoom_y = c.dpi / 72
    mat = fitz.Matrix(zoom_x, zoom_y)

    # Extract ALL page pixmaps upfront (single PDF open)
    if args.simple:
        print("Extracting page pixmaps... Simple Mode. DPI/MAX-WIDTH/CROP ignored")
        fn = process_pix_data_simple
    else:
        print(f"Extracting page pixmaps... (dpi: {c.dpi}, max-width: {c.max_width}, crop: {c.crop}px)")
        fn = process_pix_data

    skip = parse_skip_pages(args.skip, pages_n)
    page_pix_data = []

    for n in range(pages_n):
        if n + 1 in skip:
            continue
        page = doc.load_page(n)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL for optimization
        img_data = pix.tobytes("ppm")
        page_pix_data.append((parent, n, img_data, c))
    doc.close()

    with get_context("spawn").Pool(processes=cpu_count() - 1) as pool:
        pool.starmap(fn, page_pix_data)
    return 0
