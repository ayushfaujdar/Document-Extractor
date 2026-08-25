import cv2
import numpy as np
import json
import sys
from pathlib import Path


def order_points(points):
    points = np.array(points, dtype=np.float32)
    result = np.zeros((4, 2), dtype=np.float32)
    total = points.sum(axis=1)
    difference = np.diff(points, axis=1).reshape(-1)
    result[0] = points[np.argmin(total)]
    result[2] = points[np.argmax(total)]
    result[1] = points[np.argmin(difference)]
    result[3] = points[np.argmax(difference)]
    return result


def detect_document(image_path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    original = image.copy()

    height, width = image.shape[:2]
    max_dimension = 1200
    scale = min(1.0, max_dimension / max(height, width))

    if scale < 1.0:
        image = cv2.resize(
            image, None, fx=scale, fy=scale,
            interpolation=cv2.INTER_AREA
        )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (5, 5)
    )
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, kernel, iterations=2
    )

    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    contours = sorted(
        contours, key=cv2.contourArea, reverse=True
    )

    best_contour = None
    best_score = 0.0
    image_area = image.shape[0] * image.shape[1]

    for contour in contours[:50]:
        area = cv2.contourArea(contour)

        if area < image_area * 0.05:
            continue

        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(
            contour, 0.02 * perimeter, True
        )

        if len(approximation) != 4:
            continue

        area_ratio = area / image_area
        area_score = min(area_ratio / 0.40, 1.0)

        x, y, w, h = cv2.boundingRect(approximation)

        if h == 0:
            continue

        aspect_ratio = w / float(h)

        if aspect_ratio <= 0.80:
            aspect_score = 1.0
        elif aspect_ratio <= 1.0:
            aspect_score = 0.7
        else:
            aspect_score = 0.1

        rectangle_area = w * h
        if rectangle_area == 0:
            continue

        rectangularity = area / rectangle_area
        rectangularity_score = min(rectangularity, 1.0)

        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.drawContours(
            mask, [approximation], -1, 255, -1
        )

        mean_brightness = cv2.mean(gray, mask=mask)[0]

        if mean_brightness >= 170:
            brightness_score = 1.0
        elif mean_brightness >= 120:
            brightness_score = 0.6
        else:
            brightness_score = 0.1

        score = (
            area_score * 0.25
            + aspect_score * 0.35
            + rectangularity_score * 0.15
            + brightness_score * 0.25
        )

        if score > best_score:
            best_score = score
            best_contour = approximation

    if best_contour is None:
        return {
            "document_detected": False,
            "corners": None,
            "confidence": 0.0
        }

    corners = (
        best_contour.reshape(4, 2).astype(np.float32)
    )

    if scale != 1.0:
        corners = corners / scale

    corners = order_points(corners)

    contour_area = cv2.contourArea(best_contour)
    resized_area = image.shape[0] * image.shape[1]
    area_ratio = contour_area / resized_area

    confidence = (
        0.70 * best_score
        + 0.30 * min(area_ratio / 0.40, 1.0)
    ) * 100

    confidence = min(100.0, confidence)

    visualization = original.copy()

    draw_points = (
        corners.astype(np.int32).reshape((-1, 1, 2))
    )

    cv2.polylines(
        visualization, [draw_points], True,
        (0, 255, 0), 5
    )

    for point in corners:
        x, y = point.astype(int)
        cv2.circle(
            visualization, (x, y), 10,
            (0, 0, 255), -1
        )

    output_path = (
        Path(image_path).parent / "document_detected.jpg"
    )

    cv2.imwrite(str(output_path), visualization)

    return {
        "document_detected": True,
        "corners": {
            "top_left": corners[0].tolist(),
            "top_right": corners[1].tolist(),
            "bottom_right": corners[2].tolist(),
            "bottom_left": corners[3].tolist()
        },
        "confidence": round(float(confidence), 2),
        "visualization": str(output_path)
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python module2_detection.py <image>")
        sys.exit(1)

    try:
        result = detect_document(sys.argv[1])
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(f"ERROR: {error}")
        sys.exit(1)
