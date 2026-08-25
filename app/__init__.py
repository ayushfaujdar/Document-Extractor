import cv2
import numpy as np
import json
import sys
from pathlib import Path


def order_points(points):
    """
    Arrange four points as:
    top-left, top-right, bottom-right, bottom-left
    """

    points = np.array(points, dtype=np.float32)

    result = np.zeros((4, 2), dtype=np.float32)

    total = points.sum(axis=1)
    difference = np.diff(points, axis=1).reshape(-1)

    result[0] = points[np.argmin(total)]       # top-left
    result[2] = points[np.argmax(total)]       # bottom-right
    result[1] = points[np.argmin(difference)] # top-right
    result[3] = points[np.argmax(difference)] # bottom-left

    return result


def detect_document(image_path):
    """
    Detect the largest rectangular document in an image.
    """

    image = cv2.imread(str(image_path))

    if image is None:
        raise ValueError(
            f"Could not read image: {image_path}"
        )

    original = image.copy()

    # ---------------------------------------------------------
    # Resize for faster processing
    # ---------------------------------------------------------

    height, width = image.shape[:2]

    max_dimension = 1200

    scale = min(
        1.0,
        max_dimension / max(height, width)
    )

    if scale < 1.0:
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA
        )

    # ---------------------------------------------------------
    # Convert to grayscale
    # ---------------------------------------------------------

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # ---------------------------------------------------------
    # Reduce noise
    # ---------------------------------------------------------

    blurred = cv2.GaussianBlur(
        gray,
        (5, 5),
        0
    )

    # ---------------------------------------------------------
    # Detect edges
    # ---------------------------------------------------------

    edges = cv2.Canny(
        blurred,
        50,
        150
    )

    # ---------------------------------------------------------
    # Close small gaps in document boundary
    # ---------------------------------------------------------

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (5, 5)
    )

    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2
    )

    # ---------------------------------------------------------
    # Find contours
    # ---------------------------------------------------------

    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    # Largest candidates first
    contours = sorted(
        contours,
        key=cv2.contourArea,
        reverse=True
    )

    document_contour = None

    image_area = (
        image.shape[0] *
        image.shape[1]
    )

    # ---------------------------------------------------------
    # Search for rectangular contour
    # ---------------------------------------------------------

    for contour in contours[:30]:

        area = cv2.contourArea(
            contour
        )

        # Ignore very small objects
        if area < image_area * 0.10:
            continue

        perimeter = cv2.arcLength(
            contour,
            True
        )

        approximation = cv2.approxPolyDP(
            contour,
            0.02 * perimeter,
            True
        )

        # A document should approximately have 4 corners
        if len(approximation) == 4:

            document_contour = approximation

            break

    # ---------------------------------------------------------
    # No document found
    # ---------------------------------------------------------

    if document_contour is None:

        return {
            "document_detected": False,
            "corners": None,
            "confidence": 0.0
        }

    # ---------------------------------------------------------
    # Convert coordinates back to original image size
    # ---------------------------------------------------------

    corners = (
        document_contour
        .reshape(4, 2)
        .astype(np.float32)
    )

    if scale != 1.0:
        corners = corners / scale

    corners = order_points(
        corners
    )

    # ---------------------------------------------------------
    # Calculate confidence
    # ---------------------------------------------------------

    contour_area = cv2.contourArea(
        document_contour
    )

    original_area = (
        image.shape[0] *
        image.shape[1]
    )

    area_ratio = (
        contour_area /
        original_area
    )

    confidence = min(
        100.0,
        area_ratio * 100
    )

    # ---------------------------------------------------------
    # Draw detected boundary
    # ---------------------------------------------------------

    visualization = original.copy()

    draw_points = (
        corners
        .astype(np.int32)
        .reshape((-1, 1, 2))
    )

    cv2.polylines(
        visualization,
        [draw_points],
        True,
        (0, 255, 0),
        5
    )

    # Draw corners
    for point in corners:

        x, y = point.astype(int)

        cv2.circle(
            visualization,
            (x, y),
            10,
            (0, 0, 255),
            -1
        )

    output_path = (
        Path(image_path).parent /
        "document_detected.jpg"
    )

    cv2.imwrite(
        str(output_path),
        visualization
    )

    # ---------------------------------------------------------
    # Result
    # ---------------------------------------------------------

    return {
        "document_detected": True,

        "corners": {
            "top_left": corners[0].tolist(),
            "top_right": corners[1].tolist(),
            "bottom_right": corners[2].tolist(),
            "bottom_left": corners[3].tolist()
        },

        "confidence": round(
            float(confidence),
            2
        ),

        "visualization": str(
            output_path
        )
    }


# =============================================================
# COMMAND LINE
# =============================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: python module2_detection.py <image>"
        )

        sys.exit(1)

    image_path = sys.argv[1]

    try:

        result = detect_document(
            image_path
        )

        print(
            json.dumps(
                result,
                indent=2
            )
        )

    except Exception as error:

        print(
            f"ERROR: {error}"
        )

        sys.exit(1)