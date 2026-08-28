import os
import json
import time

import cv2
from paddleocr import PaddleOCR


# ============================================================
# GLOBAL OCR MODEL
# ============================================================
# IMPORTANT:
# Load PaddleOCR ONLY ONCE.
#
# Do NOT create PaddleOCR() inside extract_text().
# Creating/loading the model for every page/request is expensive.
# ============================================================

print("[OCR] Loading PaddleOCR model...")

OCR_ENGINE = PaddleOCR(
    use_angle_cls=False,
    lang="en",
    show_log=False,

    # Detection
    det_algorithm="DB",
    det_db_thresh=0.3,
    det_db_box_thresh=0.5,
    det_db_unclip_ratio=1.6,

    # Keep enough resolution for documents.
    # Do NOT aggressively resize the image.
    det_limit_side_len=1280,

    # Recognition
    rec_algorithm="CRNN",
    rec_batch_num=6,
)

print("[OCR] PaddleOCR model loaded.")


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_image(image_path):
    """
    Load the original image without destroying document detail.

    We intentionally do NOT:
        - grayscale aggressively
        - threshold
        - sharpen heavily
        - resize to tiny dimensions
        - compress the image

    PaddleOCR's detector works best when it receives
    reasonably clean document pixels.
    """

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError(
            f"Unable to read image: {image_path}"
        )

    return image


# ============================================================
# NORMALIZE PADDLEOCR OUTPUT
# ============================================================

def normalize_ocr_result(result):
    """
    Convert PaddleOCR's output into our project's format:

    {
        "text": [
            {
                "text": "...",
                "confidence": 0.98,
                "box": [...]
            }
        ]
    }

    This preserves BOTH:
        1. recognized text
        2. spatial coordinates

    The coordinates are important for extracting fields such as:

        Father's / Guardian's Name
        Mother's Name
        School
        marks-table columns
    """

    output = []

    if not result:
        return output

    # PaddleOCR 2.x commonly returns:
    #
    # [
    #     [
    #         [box, (text, confidence)],
    #         [box, (text, confidence)]
    #     ]
    # ]

    for page in result:

        if not page:
            continue

        for item in page:

            if not item or len(item) < 2:
                continue

            box = item[0]
            recognition = item[1]

            if not recognition or len(recognition) < 2:
                continue

            text = str(
                recognition[0]
            ).strip()

            try:
                confidence = float(
                    recognition[1]
                )
            except Exception:
                confidence = 0.0

            if not text:
                continue

            # Convert coordinates to normal Python floats.
            normalized_box = []

            for point in box:

                if len(point) >= 2:

                    normalized_box.append([
                        float(point[0]),
                        float(point[1])
                    ])

            output.append({
                "text": text,
                "confidence": confidence,
                "box": normalized_box
            })

    return output


# ============================================================
# MAIN OCR FUNCTION
# ============================================================

def extract_text(image_path):
    """
    Run PaddleOCR on one document page.

    Returns structured OCR information while preserving
    bounding boxes and confidence scores.
    """

    start = time.perf_counter()

    image = prepare_image(image_path)

    height, width = image.shape[:2]

    # --------------------------------------------------------
    # PaddleOCR
    # --------------------------------------------------------
    #
    # Angle classifier is disabled because your documents are
    # normally upright and disabling it removes one expensive
    # processing stage.
    #
    # If we later receive rotated documents, we can selectively
    # enable angle handling rather than slowing every document.
    # --------------------------------------------------------

    result = OCR_ENGINE.ocr(
        image,
        cls=False
    )

    text_items = normalize_ocr_result(
        result
    )

    # --------------------------------------------------------
    # Build raw text
    # --------------------------------------------------------

    raw_text = "\n".join(
        item["text"]
        for item in text_items
    )

    # --------------------------------------------------------
    # Quality statistics
    # --------------------------------------------------------

    confidences = [
        item["confidence"]
        for item in text_items
        if item["confidence"] >= 0
    ]

    if confidences:

        average_confidence = (
            sum(confidences)
            / len(confidences)
        )

        minimum_confidence = min(
            confidences
        )

    else:

        average_confidence = 0.0
        minimum_confidence = 0.0

    elapsed = (
        time.perf_counter()
        - start
    )

    print(
        f"[OCR] {os.path.basename(image_path)} "
        f"→ {len(text_items)} lines "
        f"in {elapsed:.2f}s"
    )

    return {
        "success": True,

        "image": {
            "width": width,
            "height": height
        },

        "text": text_items,

        "raw_text": raw_text,

        "ocr_quality": {
            "average_confidence": round(
                average_confidence,
                4
            ),
            "minimum_confidence": round(
                minimum_confidence,
                4
            ),
            "confidence_count": len(
                confidences
            ),
            "text_lines": len(
                text_items
            )
        },

        "timing": {
            "ocr_seconds": round(
                elapsed,
                4
            )
        }
    }


# ============================================================
# COMMAND LINE TEST
# ============================================================

if __name__ == "__main__":

    import sys

    if len(sys.argv) < 2:

        print(
            "Usage:"
        )

        print(
            "python app/ocr/module3_ocr.py "
            "image.jpg"
        )

        sys.exit(1)

    image_path = sys.argv[1]

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