from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SUBJECT_CODE_PATTERN = re.compile(r"^\d{3}$")
GRADE_PATTERN = re.compile(r"^[A-F][0-9]?$")


# =========================================================
# BASIC HELPERS
# =========================================================

def get_center(item):
    box = item.get("box", [])

    if not box:
        return 0.0, 0.0

    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]

    return (
        sum(xs) / len(xs),
        sum(ys) / len(ys),
    )


def prepare_items(ocr_result):

    items = []

    for item in ocr_result.get("text", []):

        text = str(
            item.get("text", "")
        ).strip()

        if not text:
            continue

        x, y = get_center(item)

        items.append({
            "text": text,
            "confidence": float(
                item.get("confidence", 0)
            ),
            "x": x,
            "y": y,
            "box": item.get("box", []),
        })

    return items


def numeric(text):

    text = str(text).strip()

    if not re.fullmatch(
        r"\d{1,3}",
        text
    ):
        return None

    value = int(text)

    if 0 <= value <= 100:
        return value

    return None


# =========================================================
# TABLE START
# =========================================================

def find_table_start(items):

    # -----------------------------------------------------
    # First try normal English OCR headers.
    # -----------------------------------------------------

    header_names = {
        "SUBJECT",
        "CODE",
        "THEORY",
        "TOTAL",
        "GRADE",
        "MARKS",
    }

    header_positions = []

    for item in items:

        text = item["text"].upper().strip()

        if text in header_names:
            header_positions.append(
                item["y"]
            )

    if header_positions:
        return min(header_positions)

    # -----------------------------------------------------
    # IMPORTANT FALLBACK
    #
    # CBSE headers are frequently OCR'd incorrectly.
    #
    # Instead of depending on the header text, locate the
    # first valid subject-code column entry.
    # -----------------------------------------------------

    code_candidates = []

    for item in items:

        if not (
            40 <= item["x"] <= 120
        ):
            continue

        if not SUBJECT_CODE_PATTERN.fullmatch(
            item["text"].strip()
        ):
            continue

        code_candidates.append(item)

    if code_candidates:

        return min(
            item["y"]
            for item in code_candidates
        ) - 25

    return None


def _header_x(items, table_start_y, predicate):
    """Return the x-center of the nearest matching table header."""

    candidates = [
        item
        for item in items
        if table_start_y - 35 <= item["y"] <= table_start_y + 115
        and predicate(item["text"])
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda item: abs(item["y"] - table_start_y),
    )["x"]


def find_column_centers(items, table_start_y):
    """Infer table columns from OCR'd headers instead of fixed image pixels."""

    def exact_header(name):
        return lambda text: text.upper().strip() == name

    def internal_header(text):
        normalized = re.sub(
            r"[^A-Z]",
            "",
            text.upper().replace("1", "I"),
        )
        return (
            "IA" in normalized
            or normalized == "PR"
            or "PR" in normalized
        )

    centers = {
        "code": _header_x(
            items,
            table_start_y,
            exact_header("CODE"),
        ),
        "subject": _header_x(
            items,
            table_start_y,
            exact_header("SUBJECT"),
        ),
        "theory": _header_x(
            items,
            table_start_y,
            exact_header("THEORY"),
        ),
        "internal_or_practical": _header_x(
            items,
            table_start_y,
            internal_header,
        ),
        "total": _header_x(
            items,
            table_start_y,
            exact_header("TOTAL"),
        ),
        "grade": _header_x(
            items,
            table_start_y,
            exact_header("GRADE"),
        ),
    }

    return {
        name: center
        for name, center in centers.items()
        if center is not None
    }


# =========================================================
# SUBJECT CODES
# =========================================================

def is_code(item, code_x=None, max_x=None):

    text = item["text"].strip()

    if SUBJECT_CODE_PATTERN.fullmatch(text) is None:
        return False

    if code_x is not None:
        return abs(item["x"] - code_x) <= max(40, code_x * 0.2)

    if max_x is not None:
        return item["x"] <= max_x * 0.2

    return 40 <= item["x"] <= 120


def find_subject_codes(
    items,
    table_start_y,
    code_x=None,
):

    codes = []

    max_x = max(
        (item["x"] for item in items),
        default=0,
    )

    for item in items:

        if item["y"] < table_start_y:
            continue

        if not is_code(item, code_x, max_x):
            continue

        codes.append(item)

    codes.sort(
        key=lambda item: item["y"]
    )

    # -----------------------------------------------------
    # Remove accidental duplicate detections at almost the
    # same location.
    # -----------------------------------------------------

    unique = []

    for item in codes:

        duplicate = False

        for existing in unique:

            if (
                existing["text"]
                == item["text"]
                and
                abs(
                    existing["y"]
                    - item["y"]
                ) < 5
            ):
                duplicate = True
                break

        if not duplicate:
            unique.append(item)

    return unique


# =========================================================
# SUBJECT NAME
# =========================================================

def get_subject_name(
    items,
    code,
    row_upper,
    row_lower,
    column_centers=None,
):

    candidates = []

    for item in items:

        if not (
            row_upper
            <= item["y"]
            <= row_lower
        ):
            continue

        centers = column_centers or {}
        subject_x = centers.get("subject")
        code_x = centers.get("code", code["x"])
        theory_x = centers.get("theory")

        if subject_x is not None and theory_x is not None:
            # Subject text is usually left-aligned, while the header is
            # centered. Use a wider column than a strict midpoint so short
            # names such as SCIENCE are not discarded.
            subject_left = code_x + (
                subject_x - code_x
            ) * 0.15
            subject_right = subject_x + (
                theory_x - subject_x
            ) * 0.8
        else:
            # Compatibility fallback for old OCR files without headers.
            subject_left = 110
            subject_right = 340

        if not subject_left <= item["x"] < subject_right:
            continue

        text = item["text"].strip()

        if not re.search(
            r"[A-Za-z]",
            text
        ):
            continue

        upper = text.upper()

        if upper in {
            "SUBJECT",
            "ADDITIONAL SUBJECT",
            "CODE",
        }:
            continue

        candidates.append(item)

    candidates.sort(
        key=lambda item: (
            item["y"],
            item["x"]
        )
    )

    if not candidates:
        return ""

    return " ".join(
        item["text"]
        for item in candidates
    ).strip()


# =========================================================
# ROW BOUNDARIES
# =========================================================

def _row_anchor_y(code, codes, items, column_centers):
    """Estimate a row's visual center despite OCR baseline differences."""

    if not column_centers:
        return code["y"]

    code_y = code["y"]
    index = codes.index(code)
    neighboring_distances = []

    if index > 0:
        neighboring_distances.append(
            code_y - codes[index - 1]["y"]
        )
    if index + 1 < len(codes):
        neighboring_distances.append(
            codes[index + 1]["y"] - code_y
        )

    search_window = max(
        50,
        *neighboring_distances,
    )
    offsets = []

    for column in (
        "subject",
        "theory",
        "internal_or_practical",
        "total",
        "grade",
    ):
        center = column_centers.get(column)
        if center is None:
            continue

        tolerance = max(45, center * 0.05)
        candidates = [
            item
            for item in items
            if code_y - search_window <= item["y"] <= code_y
            and abs(item["x"] - center) <= tolerance
        ]

        if candidates:
            nearest = max(candidates, key=lambda item: item["y"])
            offsets.append(code_y - nearest["y"])

    if not offsets:
        return code_y

    offsets.sort()
    middle = len(offsets) // 2
    if len(offsets) % 2:
        offset = offsets[middle]
    else:
        offset = (offsets[middle - 1] + offsets[middle]) / 2

    return code_y - offset

def get_row_boundaries(
    codes,
    index,
    items=None,
    column_centers=None,
):

    code = codes[index]

    row_anchors = [
        _row_anchor_y(
            current,
            codes,
            items or [],
            column_centers or {},
        )
        for current in codes
    ]

    y = row_anchors[index]

    previous_y = (
        row_anchors[index - 1]
        if index > 0
        else None
    )

    next_y = (
        row_anchors[index + 1]
        if index + 1 < len(codes)
        else None
    )

    # -----------------------------------------------------
    # First row
    # -----------------------------------------------------

    if previous_y is None:
        upper = y - 20
    else:
        upper = (
            previous_y + y
        ) / 2

    # -----------------------------------------------------
    # Last row
    # -----------------------------------------------------

    if next_y is None:
        lower = y + 25
    else:
        lower = (
            y + next_y
        ) / 2

    return upper, lower


def build_row(
    code,
    items,
    previous_code_y,
    next_code_y
):

    y = code["y"]

    if previous_code_y is None:
        upper = y - 20
    else:
        upper = (
            previous_code_y + y
        ) / 2

    if next_code_y is None:
        lower = y + 25
    else:
        lower = (
            y + next_code_y
        ) / 2

    return [
        item
        for item in items
        if upper <= item["y"] <= lower
    ]


# =========================================================
# MARK EXTRACTION
# =========================================================

def extract_marks(
    row_items,
    row_y,
    column_centers=None,
):

    theory = []
    internal = []
    total = []
    grades = []

    for item in row_items:

        text = item["text"].strip()
        x = item["x"]

        value = numeric(text)

        if value is not None:
            centers = column_centers or {}
            mark_centers = {
                key: centers[key]
                for key in (
                    "theory",
                    "internal_or_practical",
                    "total",
                )
                if key in centers
            }

            if mark_centers:
                nearest = min(
                    mark_centers,
                    key=lambda key: abs(x - mark_centers[key]),
                )
                sorted_centers = sorted(mark_centers.values())
                nearest_distance = abs(
                    x - mark_centers[nearest]
                )

                if len(sorted_centers) == 1:
                    tolerance = 60
                else:
                    nearest_gap = min(
                        abs(mark_centers[nearest] - other)
                        for other in sorted_centers
                        if other != mark_centers[nearest]
                    )
                    tolerance = max(60, nearest_gap * 0.48)

                if nearest_distance > tolerance:
                    continue

                if nearest == "theory":
                    theory.append(item)
                elif nearest == "internal_or_practical":
                    internal.append(item)
                else:
                    total.append(item)

            else:
                # Compatibility fallback for older OCR files without headers.
                if 340 <= x < 410:
                    theory.append(item)
                elif 410 <= x < 470:
                    internal.append(item)
                elif 470 <= x < 530:
                    total.append(item)

        # -----------------------------------------------------
        # Grade column
        # -----------------------------------------------------

        grade_x = (column_centers or {}).get("grade")
        grade_tolerance = 90
        if grade_x is not None:
            grade_tolerance = max(90, grade_x * 0.08)

        if (
            (grade_x is None and 620 <= x <= 720)
            or (
                grade_x is not None
                and abs(x - grade_x) <= grade_tolerance
            )
        ):

            if GRADE_PATTERN.fullmatch(
                text.upper()
            ):

                grades.append(item)

    def closest(values):

        if not values:
            return None

        return min(
            values,
            key=lambda item:
                abs(
                    item["y"]
                    - row_y
                )
        )

    theory_item = closest(theory)
    internal_item = closest(internal)
    total_item = closest(total)
    grade_item = closest(grades)

    return {

        "theory":
            numeric(
                theory_item["text"]
            )
            if theory_item
            else None,

        "internal_or_practical":
            numeric(
                internal_item["text"]
            )
            if internal_item
            else None,

        "total":
            numeric(
                total_item["text"]
            )
            if total_item
            else None,

        "grade":
            grade_item["text"].upper()
            if grade_item
            else None,
    }


# =========================================================
# PARSE ONE SUBJECT
# =========================================================

def parse_row(
    code,
    row_items,
    all_items,
    row_upper,
    row_lower,
    column_centers=None,
):

    code_y = code["y"]

    subject = get_subject_name(
        all_items,
        code,
        row_upper,
        row_lower,
        column_centers,
    )

    marks = extract_marks(
        row_items,
        code_y,
        column_centers,
    )

    theory = marks["theory"]
    internal = marks[
        "internal_or_practical"
    ]
    total = marks["total"]
    grade = marks["grade"]

    expected_total = None
    valid = False

    if (
        theory is not None
        and internal is not None
        and total is not None
    ):

        expected_total = (
            theory + internal
        )

        valid = (
            expected_total
            == total
        )

    return {

        "subject_code":
            code["text"].strip(),

        "subject":
            subject,

        "theory":
            theory,

        "internal_or_practical":
            internal,

        "total":
            total,

        "grade":
            grade,

        "raw_text":
            " ".join(
                item["text"]
                for item in row_items
            ),

        "validation": {

            "valid":
                valid,

            "expected_total":
                expected_total,

            "actual_total":
                total,
        },
    }


# =========================================================
# ADDITIONAL / CO-SCHOLASTIC
# =========================================================

def is_co_scholastic_subject(
    subject
):

    name = (
        subject.get("subject")
        or ""
    ).upper()

    return False


# =========================================================
# MAIN MARKS PARSER
# =========================================================

def parse_marks_table(
    ocr_result
):

    items = prepare_items(
        ocr_result
    )

    table_start_y = (
        find_table_start(
            items
        )
    )

    if table_start_y is None:

        return {

            "success": False,

            "error":
                "Marks table could not be located",

            "table_start_y":
                None,

            "academic_subjects":
                [],

            "co_scholastic":
                [],

            "summary": {

                "subjects_found": 0,

                "complete_subjects": 0,

                "total_marks": 0,

                "maximum_marks": 0,

                "percentage": None,
            },

            "validation": {

                "all_marks_valid": False,

                "errors": [],
            },
        }

    column_centers = find_column_centers(
        items,
        table_start_y,
    )

    codes = find_subject_codes(
        items,
        table_start_y,
        column_centers.get("code"),
    )

    if not codes:

        return {

            "success": False,

            "error":
                "No subject codes found",

            "table_start_y":
                round(
                    table_start_y,
                    2
                ),

            "academic_subjects":
                [],

            "co_scholastic":
                [],

            "summary": {

                "subjects_found": 0,

                "complete_subjects": 0,

                "total_marks": 0,

                "maximum_marks": 0,

                "percentage": None,
            },

            "validation": {

                "all_marks_valid": False,

                "errors": [],
            },
        }

    subjects = []

    for index, code in enumerate(
        codes
    ):

        row_upper, row_lower = (
            get_row_boundaries(
                codes,
                index,
                items,
                column_centers,
            )
        )

        row_items = [
            item
            for item in items
            if (
                row_upper
                <= item["y"]
                <= row_lower
            )
        ]

        parsed = parse_row(
            code,
            row_items,
            items,
            row_upper,
            row_lower,
            column_centers,
        )

        # -------------------------------------------------
        # Keep only actual subject rows.
        # -------------------------------------------------

        if (
            parsed["subject"]
            or
            parsed["theory"]
            is not None
            or
            parsed[
                "internal_or_practical"
            ]
            is not None
            or
            parsed["total"]
            is not None
        ):

            subjects.append(
                parsed
            )

    # =====================================================
    # SEPARATE ACADEMIC SUBJECTS
    # =====================================================

    academic_subjects = []
    co_scholastic = []

    for subject in subjects:

        if is_co_scholastic_subject(
            subject
        ):

            co_scholastic.append(
                subject
            )

        else:

            academic_subjects.append(
                subject
            )

    # =====================================================
    # SUMMARY
    # =====================================================

    total_marks = sum(
        subject["total"]
        for subject in academic_subjects
        if subject["total"] is not None
    )

    maximum_marks = (
        len(academic_subjects)
        * 100
    )

    complete_subjects = [

        subject

        for subject
        in academic_subjects

        if (
            subject["theory"]
            is not None

            and
            subject[
                "internal_or_practical"
            ]
            is not None

            and
            subject["total"]
            is not None
        )
    ]

    # =====================================================
    # VALIDATION
    # =====================================================

    validation_errors = []

    for subject in academic_subjects:

        missing_fields = []

        for field in [
            "theory",
            "internal_or_practical",
            "total",
        ]:

            if subject[field] is None:

                missing_fields.append(
                    field
                )

        if missing_fields:

            validation_errors.append({

                "subject_code":
                    subject[
                        "subject_code"
                    ],

                "subject":
                    subject[
                        "subject"
                    ],

                "error":
                    "missing_marks",

                "missing_fields":
                    missing_fields,
            })

            continue

        if not subject[
            "validation"
        ]["valid"]:

            validation_errors.append({

                "subject_code":
                    subject[
                        "subject_code"
                    ],

                "subject":
                    subject[
                        "subject"
                    ],

                "error":
                    "total_mismatch",

                "expected":
                    subject[
                        "validation"
                    ][
                        "expected_total"
                    ],

                "actual":
                    subject[
                        "validation"
                    ][
                        "actual_total"
                    ],
            })

    all_marks_valid = (

        len(
            complete_subjects
        )
        ==
        len(
            academic_subjects
        )

        and

        all(
            subject[
                "validation"
            ]["valid"]

            for subject
            in academic_subjects
        )
    )

    # -----------------------------------------------------
    # Percentage should still be calculated when marks
    # were successfully extracted, even if validation finds
    # an OCR mismatch.
    #
    # This is useful for the website because the user needs
    # to SEE the extracted data rather than lose the entire
    # table because of one OCR error.
    # -----------------------------------------------------

    percentage = None

    if maximum_marks > 0:

        percentage = round(
            (
                total_marks
                / maximum_marks
            )
            * 100,
            2,
        )

    return {

        "success":
            True,

        "table_start_y":
            round(
                table_start_y,
                2
            ),

        "academic_subjects":
            academic_subjects,

        "co_scholastic":
            co_scholastic,

        "summary": {

            "subjects_found":
                len(
                    academic_subjects
                ),

            "complete_subjects":
                len(
                    complete_subjects
                ),

            "total_marks":
                total_marks,

            "maximum_marks":
                maximum_marks,

            "percentage":
                percentage,
        },

        "validation": {

            "all_marks_valid":
                all_marks_valid,

            "errors":
                validation_errors,
        },
    }


# =========================================================
# CLI
# =========================================================

def main():

    if len(sys.argv) != 2:

        print(
            "Usage:"
        )

        print(
            "python app/extraction/"
            "marks_parser.py "
            "<ocr_result.json>"
        )

        sys.exit(1)

    ocr_path = Path(
        sys.argv[1]
    )

    if not ocr_path.exists():

        print(
            json.dumps({
                "success": False,
                "error":
                    f"OCR file not found: "
                    f"{ocr_path}"
            }, indent=2)
        )

        sys.exit(1)

    try:

        with ocr_path.open(
            "r",
            encoding="utf-8"
        ) as file:

            ocr_result = json.load(
                file
            )

        result = parse_marks_table(
            ocr_result
        )

        output_path = (
            ocr_path.parent
            / "marks_result.json"
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

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

    except Exception as error:

        error_result = {

            "success":
                False,

            "error":
                str(error),
        }

        print(
            json.dumps(
                error_result,
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)


if __name__ == "__main__":

    main()
