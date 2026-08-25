import cv2
import numpy as np


def order_points(points):
    points = np.array(points, dtype=np.float32)

    result = np.zeros((4, 2), dtype=np.float32)

    s = points.sum(axis=1)
    d = np.diff(points, axis=1).reshape(-1)

    result[0] = points[np.argmin(s)]   # top-left
    result[1] = points[np.argmin(d)]   # top-right
    result[2] = points[np.argmax(s)]   # bottom-right
    result[3] = points[np.argmax(d)]   # bottom-left

    return result


def perspective_crop(image, points):

    points = order_points(points)

    tl, tr, br, bl = points

    width1 = np.linalg.norm(br - bl)
    width2 = np.linalg.norm(tr - tl)

    height1 = np.linalg.norm(tr - br)
    height2 = np.linalg.norm(tl - bl)

    width = int(max(width1, width2))
    height = int(max(height1, height2))

    if width < 100 or height < 100:
        return None

    destination = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1]
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(
        points,
        destination
    )

    return cv2.warpPerspective(
        image,
        matrix,
        (width, height)
    )


def find_document(image):

    original = image.copy()

    height, width = image.shape[:2]

    # ==================================================
    # METHOD 1: BRIGHT PAPER DETECTION
    # ==================================================

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # The paper in your photograph is substantially
    # brighter than the surrounding objects.
    mask = cv2.inRange(
        gray,
        175,
        255
    )

    # Remove tiny regions/noise
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (9, 9)
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        kernel
    )

    # Find connected regions
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8
    )

    image_area = width * height

    candidates = []

    for i in range(1, count):

        x, y, w, h, area = stats[i]

        area_ratio = area / image_area

        # Ignore tiny regions
        if area_ratio < 0.08:
            continue

        aspect = h / float(w)

        # Marksheets are normally portrait
        if aspect < 1.1:
            continue

        if aspect > 2.2:
            continue

        # Don't accept a region touching almost the
        # entire image.
        if w > width * 0.95:
            continue

        if h > height * 0.90:
            continue

        # Prefer larger paper regions
        score = area_ratio

        candidates.append(
            (
                score,
                x,
                y,
                w,
                h,
                area
            )
        )

    if candidates:

        candidates.sort(
            reverse=True
        )

        best = candidates[0]

        _, x, y, w, h, area = best

        print(
            "Paper region detected:"
        )

        print(
            f"x={x}, y={y}, width={w}, height={h}"
        )

        # Small padding
        padding = 5

        x1 = max(
            0,
            x - padding
        )

        y1 = max(
            0,
            y - padding
        )

        x2 = min(
            width,
            x + w + padding
        )

        y2 = min(
            height,
            y + h + padding
        )

        cropped = original[
            y1:y2,
            x1:x2
        ]

        return cropped

    # ==================================================
    # METHOD 2: EDGE / CONTOUR FALLBACK
    # ==================================================

    print(
        "Bright-paper detection failed."
    )

    blurred = cv2.GaussianBlur(
        gray,
        (5, 5),
        0
    )

    edges = cv2.Canny(
        blurred,
        30,
        120
    )

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (11, 11)
    )

    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        kernel
    )

    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for contour in contours:

        area = cv2.contourArea(
            contour
        )

        if area < image_area * 0.10:
            continue

        perimeter = cv2.arcLength(
            contour,
            True
        )

        approx = cv2.approxPolyDP(
            contour,
            0.03 * perimeter,
            True
        )

        if len(approx) != 4:
            continue

        points = approx.reshape(
            4,
            2
        )

        x, y, w, h = cv2.boundingRect(
            points.astype(np.int32)
        )

        aspect = h / float(w)

        if aspect < 1.1 or aspect > 2.2:
            continue

        candidates.append(
            (
                area,
                points
            )
        )

    if candidates:

        candidates.sort(
            key=lambda x: x[0],
            reverse=True
        )

        points = candidates[0][1]

        cropped = perspective_crop(
            original,
            points
        )

        if cropped is not None:

            print(
                "Document detected using contour method."
            )

            return cropped

    return None


# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":

    input_file = "marksheet.jpeg"
    output_file = "cropped_document.jpg"

    image = cv2.imread(
        input_file
    )

    if image is None:

        raise ValueError(
            f"Could not read {input_file}"
        )

    print(
        f"Original image: "
        f"{image.shape[1]} x {image.shape[0]}"
    )

    document = find_document(
        image
    )

    if document is None:

        print(
            "ERROR: Could not detect document."
        )

        exit(1)

    # Upscale for OCR
    document = cv2.resize(
        document,
        None,
        fx=2,
        fy=2,
        interpolation=cv2.INTER_CUBIC
    )

    cv2.imwrite(
        output_file,
        document,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            95
        ]
    )

    print(
        "Document detected successfully."
    )

    print(
        f"Cropped image: "
        f"{document.shape[1]} x {document.shape[0]}"
    )

    print(
        f"Saved: {output_file}"
    )