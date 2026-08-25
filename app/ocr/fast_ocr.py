import json
import sys
import time
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import Output


# ============================================================
# FAST OCR — TESSERACT
# ============================================================

TESSERACT_CONFIG = "--psm 6"


# ============================================================
# CONFIDENCE
# ============================================================

def normalize_confidence(value):
    try:
        value = float(value)

        if value < 0:
            return 0.0

        if value > 100:
            value = 100.0

        return round(value / 100.0, 4)

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# BOX
# ============================================================

def make_box(left, top, width, height):

    left = float(left)
    top = float(top)
    width = float(width)
    height = float(height)

    return [
        [left, top],
        [left + width, top],
        [left + width, top + height],
        [left, top + height]
    ]


# ============================================================
# GROUP TESSERACT WORDS INTO LINES
# ============================================================

def group_into_lines(data):

    groups = {}

    count = len(data["text"])

    for i in range(count):

        text = str(
            data["text"][i]
        ).strip()

        if not text:
            continue

        confidence = normalize_confidence(
            data["conf"][i]
        )

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        block = data["block_num"][i]
        paragraph = data["par_num"][i]
        line = data["line_num"][i]

        key = (
            block,
            paragraph,
            line
        )

        if key not in groups:
            groups[key] = []

        groups[key].append({
            "text": text,
            "confidence": confidence,
            "left": left,
            "top": top,
            "width": width,
            "height": height
        })

    lines = []

    for words in groups.values():

        if not words:
            continue

        # Reading order inside the line
        words.sort(
            key=lambda x: x["left"]
        )

        text = " ".join(
            word["text"]
            for word in words
        )

        left = min(
            word["left"]
            for word in words
        )

        top = min(
            word["top"]
            for word in words
        )

        right = max(
            word["left"] + word["width"]
            for word in words
        )

        bottom = max(
            word["top"] + word["height"]
            for word in words
        )

        confidences = [
            word["confidence"]
            for word in words
            if word["confidence"] > 0
        ]

        if confidences:

            confidence = (
                sum(confidences)
                / len(confidences)
            )

        else:

            confidence = 0.0

        box = make_box(
            left,
            top,
            right - left,
            bottom - top
        )

        lines.append({
            "text": text,
            "confidence": round(
                confidence,
                4
            ),
            "box": box,
            "page_number": 1
        })

    # Sort complete lines by reading order
    lines.sort(
        key=lambda item: (
            min(
                point[1]
                for point in item["box"]
            ),
            min(
                point[0]
                for point in item["box"]
            )
        )
    )

    return lines


# ============================================================
# OCR
# ============================================================

def extract_text(image_path):

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )

    if not image_path.is_file():
        raise ValueError(
            f"Not a file: {image_path}"
        )

    started = time.perf_counter()

    image = Image.open(
        image_path
    )

    # Keep original resolution.
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    # --------------------------------------------------------
    # Tesseract
    # --------------------------------------------------------

    data = pytesseract.image_to_data(
        image,
        lang="eng",
        config=TESSERACT_CONFIG,
        output_type=Output.DICT
    )

    # --------------------------------------------------------
    # Convert words → lines
    # --------------------------------------------------------

    lines = group_into_lines(
        data
    )

    # --------------------------------------------------------
    # Raw text
    # --------------------------------------------------------

    raw_text = "\n".join(
        item["text"]
        for item in lines
    )

    # --------------------------------------------------------
    # Quality
    # --------------------------------------------------------

    confidences = [
        item["confidence"]
        for item in lines
        if item["confidence"] > 0
    ]

    if confidences:

        average_confidence = round(
            sum(confidences)
            / len(confidences),
            4
        )

        minimum_confidence = round(
            min(confidences),
            4
        )

    else:

        average_confidence = 0.0
        minimum_confidence = 0.0

    elapsed = (
        time.perf_counter()
        - started
    )

    return {

        "success": True,

        "ocr_engine": "tesseract",

        "image": str(
            image_path
        ),

        "line_count": len(lines),

        "text": lines,

        "raw_text": raw_text,

        "ocr_quality": {

            "average_confidence":
                average_confidence,

            "minimum_confidence":
                minimum_confidence,

            "confidence_count":
                len(confidences)

        },

        "timing": {

            "ocr_seconds":
                round(
                    elapsed,
                    4
                )

        }

    }


# ============================================================
# CLI
# ============================================================

def main():

    if len(sys.argv) != 2:

        print(
            "Usage:\n"
            "python app/ocr/fast_ocr.py "
            "<image_path>"
        )

        sys.exit(1)

    image_path = sys.argv[1]

    try:

        result = extract_text(
            image_path
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False
            )
        )

    except Exception as error:

        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(error)
                },
                indent=2
            )
        )

        sys.exit(1)


if __name__ == "__main__":
    main()