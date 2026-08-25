from __future__ import annotations
from app.ocr.module3_ocr import extract_text
import json
import re
import subprocess
import sys
import uuid
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from app.common.image_quality import check_image_quality
from app.ingestion.module1_ingestion import ingest_document
from app.extraction.generic_extractor import extract_generic


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = (
    BASE_DIR /
    "storage" /
    "input"
)

STORAGE_DIR = (
    BASE_DIR /
    "storage"
)


UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

STORAGE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "bmp",
    "tif",
    "tiff",
    "pdf",
    "docx",
}


MAX_FILE_SIZE = 50 * 1024 * 1024

app.config[
    "MAX_CONTENT_LENGTH"
] = MAX_FILE_SIZE


# ------------------------------------------------------------
# OCR workers
#
# 1 = safest / lowest memory
# 2 = faster for multi-page PDFs
#
# Your Aadhaar PDF has 2 pages, so 2 is useful.
# ------------------------------------------------------------

OCR_WORKERS = 2


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(
    filename: str
) -> bool:

    return (
        "." in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# JSON SAFETY
# ============================================================

def make_json_safe(value):

    if isinstance(value, dict):

        return {
            str(key):
            make_json_safe(val)
            for key, val in value.items()
        }


    if isinstance(value, list):

        return [
            make_json_safe(item)
            for item in value
        ]


    if isinstance(value, tuple):

        return [
            make_json_safe(item)
            for item in value
        ]


    if hasattr(value, "item"):

        try:

            return value.item()

        except (
            ValueError,
            TypeError
        ):

            pass


    return value


# ============================================================
# RUN PYTHON MODULE
# ============================================================

def run_python_script(
    script: Path,
    *args: str
):

    command = [
        sys.executable,
        str(script),
        *[
            str(arg)
            for arg in args
        ],
    ]


    print(
        "[Pipeline] Running:",
        " ".join(command)
    )


    started = time.perf_counter()


    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )


    elapsed = (
        time.perf_counter()
        - started
    )


    if completed.stdout:

        print(
            completed.stdout,
            end=""
        )


    if completed.returncode != 0:

        if completed.stderr:

            print(
                completed.stderr,
                end=""
            )


        raise RuntimeError(
            f"{script.name} failed "
            f"with exit code "
            f"{completed.returncode}"
        )


    print(
        f"[Timing] {script.name}: "
        f"{elapsed:.2f}s"
    )


    return completed


# ============================================================
# LOAD JSON
# ============================================================

def load_json(
    path: Path
):

    if not path.exists():

        return None


    try:

        with path.open(
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)


    except (
        json.JSONDecodeError,
        OSError
    ) as error:

        print(
            "[JSON Error]",
            path,
            repr(error)
        )

        return None


# ============================================================
# PARSE JSON FROM OCR STDOUT
# ============================================================

def parse_json_stdout(
    stdout: str
):

    stdout = (
        stdout or ""
    ).strip()


    if not stdout:

        raise RuntimeError(
            "OCR returned empty output."
        )


    # --------------------------------------------------------
    # module3_ocr.py may print log lines before JSON.
    # Find the first JSON object.
    # --------------------------------------------------------

    json_start = (
        stdout.find("{")
    )


    if json_start < 0:

        raise RuntimeError(
            "OCR did not return JSON data."
        )


    json_text = (
        stdout[
            json_start:
        ]
    )


    try:

        return json.loads(
            json_text
        )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            "OCR returned invalid JSON: "
            f"{error}"
        )


# ============================================================
# OCR — ONE PAGE
# ============================================================

def run_ocr_page(
    page_number: int,
    page: Path,
):

    print(
        f"[Pipeline] Module 3 — OCR "
        f"Page {page_number}: {page.name}"
    )


    started = time.perf_counter()


    try:

        result = extract_text(
            page
        )

    except Exception as error:

        raise RuntimeError(
            f"Page {page_number} OCR failed: "
            f"{error}"
        )


    elapsed = (
        time.perf_counter()
        - started
    )


    print(
        f"[Timing] OCR page "
        f"{page_number}: "
        f"{elapsed:.2f}s"
    )


    return (
        page_number,
        result
    )

# ============================================================
# OCR — COMPLETE JOB
# ============================================================

def run_ocr_for_job(
    job_directory: Path
):

    started = time.perf_counter()


    ocr_directory = (
        job_directory /
        "ocr"
    )


    ocr_directory.mkdir(
        parents=True,
        exist_ok=True
    )


    pages_directory = (
        job_directory /
        "pages"
    )


    pages = sorted(
        pages_directory.glob(
            "page_*.jpg"
        )
    )


    if not pages:

        pages = sorted(
            pages_directory.glob("*")
        )


    if not pages:

        raise RuntimeError(
            "No ingested pages were created."
        )


    print(
        f"[OCR] Total pages: "
        f"{len(pages)}"
    )


    page_results = {}


    # ========================================================
    # SINGLE PAGE
    # ========================================================

    if len(pages) == 1:

        page_number, result = (
            run_ocr_page(
                1,
                pages[0]
            )
        )


        output_path = (
            ocr_directory /
            "ocr_result.json"
        )


        with output_path.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=2,
                ensure_ascii=False,
            )


        elapsed = (
            time.perf_counter()
            - started
        )


        print(
            f"[Timing] Complete OCR: "
            f"{elapsed:.2f}s"
        )


        return (
            result,
            output_path
        )


    # ========================================================
    # MULTI-PAGE OCR
    #
    # IMPORTANT:
    # We DO NOT run OCR twice anymore.
    #
    # Each page is processed exactly once.
    # ========================================================

    workers = min(
        OCR_WORKERS,
        len(pages)
    )


    print(
        f"[OCR] Parallel workers: "
        f"{workers}"
    )


    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:

        futures = {

            executor.submit(
                run_ocr_page,
                index,
                page,
            ): index

            for index, page in enumerate(
                pages,
                start=1
            )
        }


        for future in as_completed(
            futures
        ):

            page_number, result = (
                future.result()
            )


            page_results[
                page_number
            ] = result


    # ========================================================
    # SAVE PAGE RESULTS
    # ========================================================

    for page_number in sorted(
        page_results
    ):

        result = (
            page_results[
                page_number
            ]
        )


        output_path = (
            ocr_directory /
            f"ocr_result_{page_number:04d}.json"
        )


        with output_path.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=2,
                ensure_ascii=False,
            )


    # ========================================================
    # MERGE PAGES
    # ========================================================

    merged_text = []

    merged_items = []


    for page_number in sorted(
        page_results
    ):

        result = (
            page_results[
                page_number
            ]
        )


        for item in result.get(
            "text",
            []
        ):

            item = dict(
                item
            )


            item[
                "page_number"
            ] = page_number


            merged_items.append(
                item
            )


        raw = result.get(
            "raw_text",
            ""
        )


        if raw:

            merged_text.append(
                raw
            )


    merged = {

        "success":
            True,

        "image":
            "multiple_pages",

        "line_count":
            len(merged_items),

        "text":
            merged_items,

        "raw_text":
            "\n".join(
                merged_text
            ),
    }


    merged_path = (
        ocr_directory /
        "ocr_result.json"
    )


    with merged_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            merged,
            file,
            indent=2,
            ensure_ascii=False,
        )


    elapsed = (
        time.perf_counter()
        - started
    )


    print(
        f"[Timing] Complete OCR: "
        f"{elapsed:.2f}s"
    )


    return (
        merged,
        merged_path
    )


# ============================================================
# CLASSIFIER
# ============================================================

def run_classification(
    ocr_path: Path
):

    print(
        "[Pipeline] Classifier"
    )


    script = (
        BASE_DIR /
        "app" /
        "ocr" /
        "classifier.py"
    )


    if not script.exists():

        raise RuntimeError(
            "classifier.py not found."
        )


    run_python_script(
        script,
        str(ocr_path)
    )


    return load_json(
        ocr_path.parent /
        "classification.json"
    )


# ============================================================
# CBSE EXTRACTOR
# ============================================================

def run_cbse_extraction(
    ocr_path: Path
):

    print(
        "[Pipeline] CBSE Extraction"
    )


    script = (
        BASE_DIR /
        "app" /
        "extraction" /
        "cbse_extractor.py"
    )


    if not script.exists():

        raise RuntimeError(
            "cbse_extractor.py not found."
        )


    run_python_script(
        script,
        str(ocr_path)
    )


    return load_json(
        ocr_path.parent /
        "extracted_data.json"
    )


# ============================================================
# MARKS PARSER
# ============================================================

def run_marks_parser(
    ocr_path: Path
):

    print(
        "[Pipeline] Marks Parser"
    )


    script = (
        BASE_DIR /
        "app" /
        "extraction" /
        "marks_parser.py"
    )


    if not script.exists():

        raise RuntimeError(
            "marks_parser.py not found."
        )


    run_python_script(
        script,
        str(ocr_path)
    )


    return load_json(
        ocr_path.parent /
        "marks_result.json"
    )


# ============================================================
# AADHAAR EXTRACTOR
# ============================================================

def run_aadhaar_extraction(
    ocr_path: Path
):

    print(
        "[Pipeline] Aadhaar Extraction"
    )


    script = (
        BASE_DIR /
        "app" /
        "extraction" /
        "aadhaar_extractor.py"
    )


    if not script.exists():

        raise RuntimeError(
            "aadhaar_extractor.py not found."
        )


    run_python_script(
        script,
        str(ocr_path)
    )


    return load_json(
        ocr_path.parent /
        "aadhaar_extracted_data.json"
    )


# ============================================================
# PAN EXTRACTOR
# ============================================================

def run_pan_extraction(
    ocr_path: Path
):

    print(
        "[Pipeline] PAN Extraction"
    )


    script = (
        BASE_DIR /
        "app" /
        "extraction" /
        "pan_extractor.py"
    )


    if not script.exists():

        raise RuntimeError(
            "pan_extractor.py not found."
        )


    run_python_script(
        script,
        str(ocr_path)
    )


    return load_json(
        ocr_path.parent /
        "pan_extracted_data.json"
    )


# ============================================================
# GENERIC EXTRACTION
# ============================================================

def run_generic_extraction(
    ocr_result,
    classification,
    ocr_path: Path
):

    print(
        "[Pipeline] Generic Extraction"
    )


    extraction = extract_generic(
        ocr_result,
        classification,
    )


    extraction = make_json_safe(
        extraction
    )


    output_path = (
        ocr_path.parent /
        "generic_extracted_data.json"
    )


    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            extraction,
            file,
            indent=2,
            ensure_ascii=False,
        )


    return extraction


# ============================================================
# DOCUMENT SPECIFIC ROUTER
# ============================================================

def run_document_specific_extraction(
    ocr_path: Path,
    classification: dict
):

    document_type = (
        (classification or {})
        .get(
            "document_type"
        )
    )


    print(
        "[Pipeline] Document Type:",
        document_type
    )


    # ========================================================
    # CBSE
    #
    # IMPORTANT OPTIMIZATION:
    #
    # cbse_extractor.py and marks_parser.py are independent.
    # Run them at the same time.
    # ========================================================

    if document_type in {

        "CBSE_10TH_MARKSHEET",

        "CBSE_12TH_MARKSHEET",

    }:

        print(
            "[Pipeline] Route → CBSE"
        )


        started = time.perf_counter()


        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:

            cbse_future = (
                executor.submit(
                    run_cbse_extraction,
                    ocr_path
                )
            )


            marks_future = (
                executor.submit(
                    run_marks_parser,
                    ocr_path
                )
            )


            cbse_data = (
                cbse_future.result()
            )


            marks_data = (
                marks_future.result()
            )


        elapsed = (
            time.perf_counter()
            - started
        )


        print(
            f"[Timing] CBSE extraction "
            f"+ marks parser: "
            f"{elapsed:.2f}s"
        )


        return {

            "extractor":
                "CBSE",

            "cbse":
                cbse_data,

            "marks":
                marks_data,
        }


    # ========================================================
    # AADHAAR
    # ========================================================

    if document_type == "AADHAAR":

        print(
            "[Pipeline] Route → Aadhaar"
        )


        aadhaar_data = (
            run_aadhaar_extraction(
                ocr_path
            )
        )


        return {

            "extractor":
                "AADHAAR",

            "aadhaar":
                aadhaar_data,
        }


    # ========================================================
    # PAN
    # ========================================================

    if document_type == "PAN_CARD":

        print(
            "[Pipeline] Route → PAN"
        )


        pan_data = (
            run_pan_extraction(
                ocr_path
            )
        )


        return {

            "extractor":
                "PAN",

            "pan":
                pan_data,
        }


    # ========================================================
    # UNKNOWN / OTHER
    # ========================================================

    print(
        "[Pipeline] Route → Generic"
    )


    return {

        "extractor":
            "GENERIC",

    }


# ============================================================
# BUILD FINAL WEBSITE EXTRACTION
# ============================================================

def build_extraction(
    job_directory: Path,
    ocr_result: dict,
    ocr_path: Path,
    classification: dict,
    specific_data: dict | None,
    generic_data: dict | None,
):

    classification = (
        classification or {}
    )


    document_type = (
        classification.get(
            "document_type"
        )
        or
        "UNKNOWN"
    )


    confidence = (
        classification.get(
            "confidence"
        )
    )


    # ========================================================
    # BASE RESULT
    # ========================================================

    extraction = {

        "success":
            True,

        "document_type":
            document_type,

        "classification_confidence":
            confidence,

        "student":
            {},

        "school":
            {},

        "academic_summary":
            {},

        "marks":
            [],

        "document_data":
            {},

        "generic_fields":
            {},

        # Kept for your existing generic/debug UI.
        "all_text":
            [
                item.get(
                    "text",
                    ""
                )
                for item in
                ocr_result.get(
                    "text",
                    []
                )
            ],

        "raw_text":
            ocr_result.get(
                "raw_text",
                ""
            ),

        "job_id":
            job_directory.name,
    }


    # ========================================================
    # CBSE
    # ========================================================

    if document_type in {

        "CBSE_10TH_MARKSHEET",

        "CBSE_12TH_MARKSHEET",

    }:

        cbse_data = (
            specific_data or {}
        ).get(
            "cbse"
        ) or {}


        marks_data = (
            specific_data or {}
        ).get(
            "marks"
        ) or {}


        student = (
            cbse_data.get(
                "student"
            )
            or {}
        )


        school = (
            cbse_data.get(
                "school"
            )
            or {}
        )


        summary = (
            marks_data.get(
                "summary"
            )
            or {}
        )


        extraction[
            "student"
        ] = {

            "name":
                student.get(
                    "name"
                ),

            "roll_number":
                student.get(
                    "roll_number"
                ),

            "registration_number":
                student.get(
                    "registration_number"
                ),

            "date_of_birth":
                student.get(
                    "date_of_birth"
                ),

            "mother_name":
                student.get(
                    "mother_name"
                ),

            "father_name":
                student.get(
                    "father_name"
                ),
        }


        extraction[
            "school"
        ] = {

            "name":
                school.get(
                    "name"
                ),
        }


        extraction[
            "academic_summary"
        ] = {

            "total_marks":
                summary.get(
                    "total_marks"
                ),

            "maximum_marks":
                summary.get(
                    "maximum_marks"
                ),

            "percentage":
                summary.get(
                    "percentage"
                ),

            "subjects":
                summary.get(
                    "subjects_found"
                ),
        }


        extraction[
            "marks"
        ] = (
            marks_data.get(
                "academic_subjects"
            )
            or []
        )


        extraction[
            "document_data"
        ] = {

            "result":
                cbse_data.get(
                    "result"
                ),

            "exam_year":
                cbse_data.get(
                    "exam_year"
                ),
        }


    # ========================================================
    # AADHAAR
    # ========================================================

    elif document_type == "AADHAAR":

        aadhaar = (
            specific_data or {}
        ).get(
            "aadhaar"
        ) or {}


        data = (
            aadhaar.get(
                "data"
            )
            or {}
        )


        extraction[
            "student"
        ] = {

            "name":
                data.get(
                    "name"
                ),

            "father_name":
                data.get(
                    "father_name"
                ),

            "date_of_birth":
                data.get(
                    "date_of_birth"
                ),

            "gender":
                data.get(
                    "gender"
                ),
        }


        extraction[
            "document_data"
        ] = {

            "aadhaar_number":
                data.get(
                    "aadhaar_number"
                ),

            "address":
                data.get(
                    "address"
                ),

            "year_of_birth":
                data.get(
                    "year_of_birth"
                ),
        }


    # ========================================================
    # PAN
    # ========================================================

    elif document_type == "PAN_CARD":

        pan = (
            specific_data or {}
        ).get(
            "pan"
        ) or {}


        data = (
            pan.get(
                "data"
            )
            or {}
        )


        extraction[
            "student"
        ] = {

            "name":
                data.get(
                    "name"
                ),

            "father_name":
                data.get(
                    "father_name"
                ),

            "date_of_birth":
                data.get(
                    "date_of_birth"
                ),
        }


        extraction[
            "document_data"
        ] = {

            "pan_number":
                data.get(
                    "pan_number"
                ),
        }


    # ========================================================
    # GENERIC
    # ========================================================

    else:

        generic_data = (
            generic_data or {}
        )


        extraction[
            "generic_fields"
        ] = (
            generic_data.get(
                "fields"
            )
            or {}
        )


        extraction[
            "document_data"
        ] = generic_data


    # ========================================================
    # EXAM YEAR FALLBACK
    # ========================================================

    raw_upper = (
        extraction[
            "raw_text"
        ].upper()
    )


    if (
        document_type.startswith(
            "CBSE"
        )
        and
        not extraction[
            "document_data"
        ].get(
            "exam_year"
        )
    ):

        match = re.search(

            r"(?:EXAMINATION|EXAM|YEAR)"
            r"[,\s:/-]*(20\d{2})",

            raw_upper,
        )


        if match:

            extraction[
                "document_data"
            ][
                "exam_year"
            ] = match.group(1)


    # ========================================================
    # RESULT FALLBACK
    # ========================================================

    if document_type.startswith(
        "CBSE"
    ):

        if not extraction[
            "document_data"
        ].get(
            "result"
        ):

            match = re.search(

                r"\b"
                r"(PASS|FAIL|COMPARTMENT)"
                r"\b",

                raw_upper,
            )


            if match:

                extraction[
                    "document_data"
                ][
                    "result"
                ] = match.group(1)


    # ========================================================
    # SAVE WEBSITE RESULT
    # ========================================================

    output_path = (
        ocr_path.parent /
        "website_extraction.json"
    )


    safe_extraction = (
        make_json_safe(
            extraction
        )
    )


    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            safe_extraction,
            file,
            indent=2,
            ensure_ascii=False,
        )


    print(
        "[Pipeline] Website extraction:",
        output_path
    )


    return safe_extraction


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# UPLOAD API
# ============================================================

@app.route(
    "/api/upload",
    methods=["POST"]
)
def upload():

    total_started = (
        time.perf_counter()
    )


    try:

        # ====================================================
        # FILE
        # ====================================================

        if "file" not in request.files:

            return jsonify({

                "success":
                    False,

                "error":
                    "No file uploaded.",

            }), 400


        file = request.files[
            "file"
        ]


        if not file.filename:

            return jsonify({

                "success":
                    False,

                "error":
                    "No file selected.",

            }), 400


        if not allowed_file(
            file.filename
        ):

            return jsonify({

                "success":
                    False,

                "error":
                    (
                        "Unsupported file type. "
                        "Use JPG, JPEG, PNG, WEBP, "
                        "TIFF, PDF or DOCX."
                    ),

            }), 400


        # ====================================================
        # UPLOAD JOB
        # ====================================================

        upload_job_id = (
            uuid.uuid4().hex
        )


        filename = secure_filename(
            file.filename
        )


        input_directory = (
            UPLOAD_DIR /
            upload_job_id
        )


        input_directory.mkdir(
            parents=True,
            exist_ok=True
        )


        input_path = (
            input_directory /
            filename
        )


        file.save(
            str(input_path)
        )


        print(
            "[Pipeline] Upload:",
            filename
        )


        # ====================================================
        # IMAGE QUALITY
        # ====================================================

        quality = None


        if input_path.suffix.lower() in {

            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",

        }:

            quality_started = (
                time.perf_counter()
            )


            quality = make_json_safe(
                check_image_quality(
                    input_path
                )
            )


            quality_elapsed = (
                time.perf_counter()
                - quality_started
            )


            print(
                f"[Timing] Image quality: "
                f"{quality_elapsed:.2f}s"
            )


            if not quality.get(
                "acceptable",
                False
            ):

                return jsonify({

                    "success":
                        False,

                    "status":
                        "QUALITY_REJECTED",

                    "message":
                        (
                            "The uploaded document "
                            "is not clear enough "
                            "for reliable extraction."
                        ),

                    "quality":
                        quality,

                }), 422


        # ====================================================
        # MODULE 1 — INGESTION
        # ====================================================

        ingestion_started = (
            time.perf_counter()
        )


        print(
            "[Pipeline] Module 1 — Ingestion"
        )


        ingestion_result = (
            ingest_document(

                input_file=
                    str(input_path),

                storage_root=
                    str(STORAGE_DIR),

            )
        )


        ingestion_elapsed = (
            time.perf_counter()
            - ingestion_started
        )


        print(
            f"[Timing] Ingestion: "
            f"{ingestion_elapsed:.2f}s"
        )


        ingestion_data = asdict(
            ingestion_result
        )


        # ====================================================
        # EXACT MODULE 1 JOB
        # ====================================================

        job_directory = (
            STORAGE_DIR /
            ingestion_result.job_id
        ).resolve()


        if not job_directory.exists():

            raise RuntimeError(

                "Module 1 returned a job_id, "
                "but the corresponding "
                "storage directory does not exist: "

                f"{job_directory}"

            )


        print(
            "[Pipeline] Job:",
            job_directory
        )


        # ====================================================
        # MODULE 3 — OCR
        # ====================================================

        ocr_result, ocr_path = (
            run_ocr_for_job(
                job_directory
            )
        )


        # ====================================================
        # CLASSIFICATION
        # ====================================================

        classification_started = (
            time.perf_counter()
        )


        classification = (
            run_classification(
                ocr_path
            )
        )


        classification_elapsed = (
            time.perf_counter()
            - classification_started
        )


        print(
            f"[Timing] Classification: "
            f"{classification_elapsed:.2f}s"
        )


        if classification is None:

            classification = {

                "document_type":
                    "UNKNOWN",

                "confidence":
                    0,

                "decision":
                    "UNKNOWN",

            }


        print(
            "[Pipeline] Classification:",
            classification.get(
                "document_type"
            )
        )


        # ====================================================
        # DOCUMENT-SPECIFIC ROUTING
        # ====================================================

        specific_data = (
            run_document_specific_extraction(

                ocr_path,

                classification,

            )
        )


        # ====================================================
        # GENERIC EXTRACTION
        #
        # Only for documents without a
        # dedicated extractor.
        # ====================================================

        document_type = (
            classification.get(
                "document_type"
            )
        )


        dedicated_types = {

            "CBSE_10TH_MARKSHEET",

            "CBSE_12TH_MARKSHEET",

            "AADHAAR",

            "PAN_CARD",

        }


        generic_data = None


        if document_type not in dedicated_types:

            generic_data = (
                run_generic_extraction(

                    ocr_result,

                    classification,

                    ocr_path,

                )
            )


        # ====================================================
        # BUILD FINAL WEBSITE RESULT
        # ====================================================

        extraction_started = (
            time.perf_counter()
        )


        extraction = build_extraction(

            job_directory,

            ocr_result,

            ocr_path,

            classification,

            specific_data,

            generic_data,

        )


        extraction_elapsed = (
            time.perf_counter()
            - extraction_started
        )


        print(
            f"[Timing] Website result: "
            f"{extraction_elapsed:.2f}s"
        )


        # ====================================================
        # TOTAL TIME
        # ====================================================

        total_elapsed = (
            time.perf_counter()
            - total_started
        )


        print(
            "=========================================="
        )

        print(
            f"[Timing] TOTAL REQUEST: "
            f"{total_elapsed:.2f}s"
        )

        print(
            "=========================================="
        )


        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "success":
                True,

            "status":
                "EXTRACTED",

            "message":
                (
                    "Document processed successfully. "
                    "Data extraction is complete."
                ),

            "upload_job_id":
                upload_job_id,

            "job_id":
                ingestion_result.job_id,

            "classification":
                make_json_safe(
                    classification
                ),

            "ingestion":
                make_json_safe(
                    ingestion_data
                ),

            "quality":
                quality,

            "extraction":
                extraction,

        }), 200


    except Exception as error:

        print(
            "[Upload Error]",
            repr(error)
        )


        return jsonify({

            "success":
                False,

            "status":
                "ERROR",

            "error":
                str(error),

        }), 500


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=8000,

        debug=True,

    )