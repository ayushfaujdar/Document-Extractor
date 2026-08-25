import json
import sys
from pathlib import Path

from paddleocr import PaddleOCR


# ============================================================
# OCR ENGINE
#
# IMPORTANT:
# This object is created ONLY ONCE when this module is loaded.
#
# Do NOT create PaddleOCR inside extract_text().
# ============================================================

print("[OCR] Loading PaddleOCR model...")

_ocr = PaddleOCR(
    use_angle_cls=True,
    lang="en",
    show_log=False
)

print("[OCR] PaddleOCR model loaded.")


# ============================================================
# OCR FUNCTION
# ============================================================

def extract_text(image_path):

    image_path = Path(
        image_path
    )


    if not image_path.exists():

        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )


    if not image_path.is_file():

        raise ValueError(
            f"Image path is not a file: {image_path}"
        )


    # --------------------------------------------------------
    # Run OCR
    #
    # IMPORTANT:
    # The existing _ocr object is reused.
    # --------------------------------------------------------

    result = _ocr.ocr(
        str(image_path),
        cls=True
    )


    lines = []


    # --------------------------------------------------------
    # PaddleOCR 2.x result format
    # --------------------------------------------------------

    if result and result[0]:

        for item in result[0]:

            if not item or len(item) < 2:

                continue


            box = item[0]

            text_info = item[1]


            if (
                not text_info
                or
                len(text_info) < 2
            ):

                continue


            text = str(
                text_info[0]
            ).strip()


            confidence = float(
                text_info[1]
            )


            if not text:

                continue


            lines.append({

                "text":
                    text,

                "confidence":
                    round(
                        confidence,
                        4
                    ),

                "box":
                    box

            })


    # --------------------------------------------------------
    # Reading order
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Combined text
    # --------------------------------------------------------

    raw_text = "\n".join(

        item["text"]

        for item in lines

    )


    return {

        "success":
            True,

        "image":
            str(image_path),

        "line_count":
            len(lines),

        "text":
            lines,

        "raw_text":
            raw_text

    }


# ============================================================
# COMMAND LINE MODE
#
# This is kept so your existing testing command still works:
#
# python app/ocr/module3_ocr.py image.jpg
#
# NOTE:
# CLI mode still has to load the model each time because the
# process itself ends.
# The WEBSITE will NOT use this mode anymore.
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: "
            "python app/ocr/module3_ocr.py <image>"
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
            f"ERROR: {error}"
        )

        sys.exit(1)