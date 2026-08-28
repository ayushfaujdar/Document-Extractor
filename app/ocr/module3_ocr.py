"""Shared OCR adapter used by the document-processing pipeline.

The application uses PaddleOCR 3.x with its native ONNX Runtime engine.
Keeping the PaddleOCR call and result conversion here gives the rest of the
application a stable, small OCR schema while allowing the engine to evolve.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# PaddleX reads this variable during import/model construction. A project
# local default keeps downloaded models out of the user's global cache, while
# still allowing deployments to override it with an environment variable.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault(
    "PADDLE_PDX_CACHE_HOME",
    str(PROJECT_ROOT / ".paddlex"),
)

import cv2
from paddleocr import PaddleOCR


OCR_VERSION = os.getenv("OCR_VERSION", "PP-OCRv6")
OCR_USE_TEXTLINE_ORIENTATION = (
    os.getenv("OCR_USE_TEXTLINE_ORIENTATION", "false").lower()
    in {"1", "true", "yes", "on"}
)


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer setting, falling back safely on bad input."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


# A single OCR session lets ONNX Runtime manage CPU parallelism without
# oversubscribing the machine. Override this after benchmarking a target Mac.
DEFAULT_THREADS = min(4, max(1, os.cpu_count() or 1))
OCR_INTRA_OP_THREADS = _positive_int_env(
    "OCR_INTRA_OP_THREADS",
    DEFAULT_THREADS,
)


print(
    "[OCR] Loading PaddleOCR "
    f"{OCR_VERSION} with ONNX Runtime "
    f"({OCR_INTRA_OP_THREADS} CPU threads)..."
)

OCR_ENGINE = PaddleOCR(
    lang="en",
    ocr_version=OCR_VERSION,
    engine="onnxruntime",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=OCR_USE_TEXTLINE_ORIENTATION,
    text_det_limit_side_len=1280,
    text_det_limit_type="max",
    text_det_thresh=0.3,
    text_det_box_thresh=0.5,
    text_det_unclip_ratio=1.6,
    text_rec_score_thresh=0.0,
    text_recognition_batch_size=6,
    engine_config={
        "onnxruntime": {
            "providers": ["CPUExecutionProvider"],
            "intra_op_num_threads": OCR_INTRA_OP_THREADS,
            "inter_op_num_threads": 1,
            "execution_mode": "sequential",
            # ONNX Runtime's ORT_ENABLE_ALL enum is represented by 99.
            "graph_optimization_level": 99,
        }
    },
)

print("[OCR] PaddleOCR model loaded.")


def prepare_image(image_path: str | os.PathLike[str]):
    """Load the original image without discarding document detail."""

    image = cv2.imread(os.fspath(image_path))

    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    return image


def _as_list(value: Any) -> list[Any]:
    """Convert NumPy-like arrays and sequences into ordinary Python lists."""

    if value is None:
        return []

    if hasattr(value, "tolist"):
        value = value.tolist()

    if isinstance(value, (list, tuple)):
        return list(value)

    return []


def _result_payload(result: Any) -> dict[str, Any]:
    """Extract the JSON-like payload from a PaddleOCR 3.x result object."""

    if isinstance(result, dict):
        payload = result
    else:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {}

    if not isinstance(payload, dict):
        return {}

    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _normalize_box(box: Any) -> list[list[float]]:
    """Convert a polygon or rectangle into the project's box format."""

    points = _as_list(box)

    # PaddleOCR 3.x normally returns four polygon points.
    if points and all(
        isinstance(point, (list, tuple))
        or hasattr(point, "tolist")
        for point in points
    ):
        normalized = []
        for point in points:
            coordinates = _as_list(point)
            if len(coordinates) >= 2:
                normalized.append([
                    float(coordinates[0]),
                    float(coordinates[1]),
                ])
        return normalized

    # Also accept PaddleOCR's rectangular [x1, y1, x2, y2] form.
    if len(points) >= 4:
        x1, y1, x2, y2 = (float(value) for value in points[:4])
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

    return []


def _normalize_v3_result(result: Any) -> list[dict[str, Any]]:
    """Normalize one or more PaddleOCR 3.x results."""

    pages = result if isinstance(result, (list, tuple)) else [result]
    output = []

    for page in pages:
        payload = _result_payload(page)
        if not payload or "rec_texts" not in payload:
            continue

        texts = _as_list(payload.get("rec_texts"))
        scores = _as_list(payload.get("rec_scores"))
        boxes_value = (
            payload.get("rec_polys")
            if payload.get("rec_polys") is not None
            else payload.get("dt_polys")
        )
        boxes = _as_list(boxes_value)

        for index, raw_text in enumerate(texts):
            text = str(raw_text).strip()
            if not text:
                continue

            try:
                confidence = float(scores[index])
            except (IndexError, TypeError, ValueError):
                confidence = 0.0

            box = boxes[index] if index < len(boxes) else []
            output.append({
                "text": text,
                "confidence": confidence,
                "box": _normalize_box(box),
            })

    return output


def _normalize_legacy_result(result: Any) -> list[dict[str, Any]]:
    """Keep compatibility with old saved 2.x-shaped OCR data."""

    output = []
    pages = result if isinstance(result, (list, tuple)) else [result]

    for page in pages:
        if not isinstance(page, (list, tuple)):
            continue

        for item in page:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue

            box, recognition = item[0], item[1]
            if not isinstance(recognition, (list, tuple)) or len(recognition) < 2:
                continue

            text = str(recognition[0]).strip()
            if not text:
                continue

            try:
                confidence = float(recognition[1])
            except (TypeError, ValueError):
                confidence = 0.0

            output.append({
                "text": text,
                "confidence": confidence,
                "box": _normalize_box(box),
            })

    return output


def normalize_ocr_result(result: Any) -> list[dict[str, Any]]:
    """Return OCR lines with stable text, confidence, and polygon fields."""

    normalized = _normalize_v3_result(result)
    return normalized if normalized else _normalize_legacy_result(result)


def _build_response(
    image,
    result: Any,
    source_name: str,
    started: float,
) -> dict[str, Any]:
    """Build the stable response consumed by classifiers and extractors."""

    height, width = image.shape[:2]
    text_items = normalize_ocr_result(result)
    raw_text = "\n".join(item["text"] for item in text_items)

    confidences = [
        item["confidence"]
        for item in text_items
        if item["confidence"] >= 0
    ]
    average_confidence = (
        sum(confidences) / len(confidences)
        if confidences
        else 0.0
    )
    minimum_confidence = min(confidences) if confidences else 0.0
    elapsed = time.perf_counter() - started

    print(
        f"[OCR] {os.path.basename(source_name)} → "
        f"{len(text_items)} lines in {elapsed:.2f}s"
    )

    return {
        "success": True,
        "image": {"width": width, "height": height},
        "text": text_items,
        "raw_text": raw_text,
        "ocr_engine": "paddleocr-3.7-onnxruntime",
        "ocr_model": OCR_VERSION,
        "ocr_quality": {
            "average_confidence": round(average_confidence, 4),
            "minimum_confidence": round(minimum_confidence, 4),
            "confidence_count": len(confidences),
            "text_lines": len(text_items),
        },
        "timing": {"ocr_seconds": round(elapsed, 4)},
    }


def _run_engine(input_value: Any) -> Any:
    """Run one page through the PaddleOCR 3.x predictor."""

    # PaddleOCR 3.x returns an iterator; materialize it before normalization.
    return list(OCR_ENGINE.predict(input_value))


def extract_text(image_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Run OCR on one ingested page path."""

    started = time.perf_counter()
    image_path = os.fspath(image_path)
    image = prepare_image(image_path)
    result = _run_engine(image_path)
    return _build_response(image, result, image_path, started)


def extract_text_from_array(image, source_name: str = "image") -> dict[str, Any]:
    """Run OCR on an in-memory BGR image for standalone utilities."""

    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise ValueError("Expected a readable image array.")

    started = time.perf_counter()
    result = _run_engine(image)
    return _build_response(image, result, source_name, started)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python app/ocr/module3_ocr.py image.jpg")
        raise SystemExit(1)

    print(json.dumps(extract_text(sys.argv[1]), indent=2, ensure_ascii=False))
