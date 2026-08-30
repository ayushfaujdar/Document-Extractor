"""Shared OCR adapter used by the document-processing pipeline.

The application uses PaddleOCR 3.x with its native ONNX Runtime engine.
Keeping the PaddleOCR call and result conversion here gives the rest of the
application a stable, small OCR schema while allowing the engine to evolve.

GPU / accelerator support
--------------------------
Set ``OCR_USE_GPU`` to control which ONNX Runtime execution provider is used:

* ``auto``  (default) — try CUDA or DirectML and fall back to CPU.
  CoreML is excluded from auto-detection: PP-OCRv6 has ~21 unsupported ops
  which split the graph into ~20 partitions, making CPU<->CoreML transfers
  3-5x slower than running everything on CPU.
* ``coreml`` — force CoreML on Apple Silicon (experimental; expect slowdown).
* ``true``   — require a GPU provider (CUDA/DirectML); raise if none found.
* ``false``  — always use CPUExecutionProvider regardless of hardware.
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

# OCR_USE_GPU controls which ONNX Runtime execution provider is used.
# Values: "auto" (default), "true" (require GPU), "false" (force CPU).
OCR_USE_GPU = os.getenv("OCR_USE_GPU", "auto").strip().lower()


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer setting, falling back safely on bad input."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


def _detect_gpu_provider() -> tuple[str | None, str]:
    """Return the best available GPU execution provider and a reason string.

    Returns a ``(provider_name, reason)`` tuple where ``provider_name`` is
    ``None`` when no GPU provider is available.
    """
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
    except Exception:
        return None, "onnxruntime not importable"

    # Priority order: CUDA (Linux/Windows) → DirectML (Windows)
    # CoreML is intentionally excluded from auto-detection: PP-OCRv6 has
    # ~21 ops unsupported by CoreML which causes ONNX Runtime to split the
    # graph into ~20 partitions, making CPU↔CoreML tensor transfers far
    # slower than running everything on CPU. Force it with OCR_USE_GPU=coreml
    # if you want to experiment.
    candidates = [
        ("CUDAExecutionProvider", "NVIDIA CUDA GPU"),
        ("DmlExecutionProvider",  "DirectML GPU (Windows)"),
    ]

    for provider, label in candidates:
        if provider in available:
            return provider, label

    return None, "no GPU provider found in: " + ", ".join(available)


def _build_engine_config() -> tuple[dict, str, int, int]:
    """Build the ONNX Runtime engine_config dict.

    Returns ``(engine_config, active_provider, intra_op_threads, batch_size)``.
    The caller uses the latter two values to set PaddleOCR parameters so that
    CPU threads and recognition batch size are tuned to the chosen backend.
    """
    cpu_count = os.cpu_count() or 1

    # ------------------------------------------------------------------ #
    # Determine provider list based on OCR_USE_GPU                        #
    # ------------------------------------------------------------------ #
    if OCR_USE_GPU == "false":
        # User explicitly wants CPU — skip detection entirely.
        providers = ["CPUExecutionProvider"]
        active_provider = "CPUExecutionProvider"
        reason = "OCR_USE_GPU=false (forced CPU)"

    elif OCR_USE_GPU == "coreml":
        # User explicitly wants CoreML — useful for experimentation on Apple
        # Silicon even though auto-mode skips it due to graph partitioning.
        providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        active_provider = "CoreMLExecutionProvider"
        reason = "OCR_USE_GPU=coreml (forced, expect graph-partition warnings)"

    elif OCR_USE_GPU == "true":
        # User requires GPU — raise if none available.
        gpu_provider, reason = _detect_gpu_provider()
        if gpu_provider is None:
            raise RuntimeError(
                f"[OCR] OCR_USE_GPU=true but no GPU provider found. "
                f"Reason: {reason}. "
                "Set OCR_USE_GPU=auto or OCR_USE_GPU=false to fall back to CPU."
            )
        providers = [gpu_provider, "CPUExecutionProvider"]
        active_provider = gpu_provider

    else:  # "auto" (default)
        gpu_provider, reason = _detect_gpu_provider()
        if gpu_provider is not None:
            providers = [gpu_provider, "CPUExecutionProvider"]
            active_provider = gpu_provider
        else:
            providers = ["CPUExecutionProvider"]
            active_provider = "CPUExecutionProvider"

    # ------------------------------------------------------------------ #
    # Tune threads and batch size to the chosen backend                   #
    # ------------------------------------------------------------------ #
    using_gpu = active_provider != "CPUExecutionProvider"

    if using_gpu:
        # GPU handles the heavy inference; CPU threads are only for pre/post-
        # processing, so a small number avoids oversubscription.
        default_threads = min(2, cpu_count)
        default_batch = 16
    else:
        # CPU-only: use more threads to saturate multi-core machines.
        default_threads = min(8, max(1, cpu_count))
        default_batch = 6

    intra_op_threads = _positive_int_env("OCR_INTRA_OP_THREADS", default_threads)
    batch_size = _positive_int_env("OCR_RECOGNITION_BATCH_SIZE", default_batch)

    engine_config = {
        "onnxruntime": {
            "providers": providers,
            "intra_op_num_threads": intra_op_threads,
            "inter_op_num_threads": 1,
            "execution_mode": "sequential",
            # ONNX Runtime's ORT_ENABLE_ALL enum is represented by 99.
            "graph_optimization_level": 99,
        }
    }

    return engine_config, active_provider, intra_op_threads, batch_size, reason


# ------------------------------------------------------------------ #
# Build engine config and log the chosen backend before model load    #
# ------------------------------------------------------------------ #
(
    _ENGINE_CONFIG,
    _ACTIVE_PROVIDER,
    OCR_INTRA_OP_THREADS,
    _BATCH_SIZE,
    _PROVIDER_REASON,
) = _build_engine_config()

print(
    f"[OCR] Backend  : {_ACTIVE_PROVIDER} — {_PROVIDER_REASON}\n"
    f"[OCR] Threads  : {OCR_INTRA_OP_THREADS} intra-op CPU thread(s)\n"
    f"[OCR] Batch    : {_BATCH_SIZE} recognition crops per batch\n"
    f"[OCR] Loading PaddleOCR {OCR_VERSION} ..."
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
    text_recognition_batch_size=_BATCH_SIZE,
    engine_config=_ENGINE_CONFIG,
)

print(f"[OCR] PaddleOCR model loaded. Active provider: {_ACTIVE_PROVIDER}")


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



def _build_response(
    image,
    result: Any,
    source_name: str,
    started: float,
) -> dict[str, Any]:
    """Build the stable response consumed by classifiers and extractors."""

    height, width = image.shape[:2]
    text_items = _normalize_v3_result(result)
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
        "ocr_engine": f"paddleocr-3.7-onnxruntime-{_ACTIVE_PROVIDER.lower().replace('executionprovider', '')}",
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
