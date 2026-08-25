import cv2
from pathlib import Path


def check_image_quality(image_path):
    """
    Fast, lightweight image-quality check.

    This runs BEFORE OCR so expensive OCR processing
    is avoided for obviously poor images.
    """

    image_path = Path(image_path)

    image = cv2.imread(str(image_path))

    if image is None:
        return {
            "acceptable": False,
            "reason": "Unable to read image"
        }

    height, width = image.shape[:2]

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # --------------------------------------------------
    # Blur detection
    # --------------------------------------------------

    blur_score = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    # --------------------------------------------------
    # Brightness
    # --------------------------------------------------

    brightness = float(gray.mean())

    # --------------------------------------------------
    # Resolution
    # --------------------------------------------------

    pixels = width * height

    # We don't demand extremely high resolution.
    # We only reject obviously tiny images.
    resolution_ok = (
        width >= 700 and
        height >= 900 and
        pixels >= 700_000
    )

    # --------------------------------------------------
    # Blur threshold
    # --------------------------------------------------

    # Moderate threshold.
    #
    # We don't want to reject every slightly soft
    # mobile-camera image.
    blur_ok = blur_score >= 45

    # --------------------------------------------------
    # Lighting
    # --------------------------------------------------

    brightness_ok = (
        55 <= brightness <= 235
    )

    # --------------------------------------------------
    # Final decision
    # --------------------------------------------------

    problems = []

    if not resolution_ok:
        problems.append(
            "Image resolution is too low"
        )

    if not blur_ok:
        problems.append(
            "Image is too blurry"
        )

    if brightness < 55:
        problems.append(
            "Image is too dark"
        )

    if brightness > 235:
        problems.append(
            "Image is too bright"
        )

    acceptable = len(problems) == 0

    return {
        "acceptable": acceptable,

        "width": width,
        "height": height,

        "blur_score": round(
            float(blur_score),
            2
        ),

        "brightness": round(
            brightness,
            2
        ),

        "resolution_ok": bool(resolution_ok),
        "blur_ok": bool(blur_ok),
        "brightness_ok": bool(brightness_ok),

        "problems": problems
    }