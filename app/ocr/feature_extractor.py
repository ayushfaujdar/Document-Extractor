"""
Document Verification - OCR Feature Extractor

Phase 1 / 2 foundation:
- Does NOT classify documents.
- Does NOT call any document-specific extractor.
- Does NOT modify the existing OCR output.
- Reads the existing PaddleOCR JSON format and produces reusable signals.

Input:
    ocr_result.json

Output:
    ocr_features.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import mean


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:

    text = str(text or "").upper()

    replacements = {
        "CENTRAL BOARD OFSECONDARY EDUCATION":
            "CENTRAL BOARD OF SECONDARY EDUCATION",

        "CENTRAL BOARD OF SECONDARYEDUCATION":
            "CENTRAL BOARD OF SECONDARY EDUCATION",

        "BOARD OFSECONDARY EDUCATION":
            "BOARD OF SECONDARY EDUCATION",

        "BOARD OF SECONDARYEDUCATION":
            "BOARD OF SECONDARY EDUCATION",

        "SECONDARYSCHOOL":
            "SECONDARY SCHOOL",

        "SENIORSCHOOL":
            "SENIOR SCHOOL",

        "CERTIFICATEEXAMINATION":
            "CERTIFICATE EXAMINATION",

        "SCHOOLCERTIFICATE":
            "SCHOOL CERTIFICATE",

        "MOTHER S NAME":
            "MOTHER'S NAME",

        "FATHER GUARDIAN S NAME":
            "FATHER/GUARDIAN'S NAME",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[^A-Z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# SIGNAL DICTIONARIES
# ============================================================

KEYWORD_GROUPS = {

    "cbse": [
        "CENTRAL BOARD OF SECONDARY EDUCATION",
        "CBSE",
    ],

    "up_board": [
        "BOARD OF HIGH SCHOOL AND INTERMEDIATE EDUCATION",
        "MADHYAMIK SHIKSHA PARISHAD",
        "UTTAR PRADESH",
        "UP BOARD",
    ],

    "bihar_board": [
        "BIHAR SCHOOL EXAMINATION BOARD",
        "BSEB",
        "BIHAR BOARD",
    ],

    "rbse": [
        "BOARD OF SECONDARY EDUCATION RAJASTHAN",
        "RAJASTHAN BOARD",
        "RBSE",
    ],

    "mp_board": [
        "BOARD OF SECONDARY EDUCATION MADHYA PRADESH",
        "MADHYA PRADESH BOARD",
        "MP BOARD",
    ],

    "karnataka_board": [
        "KARNATAKA SECONDARY EDUCATION EXAMINATION BOARD",
        "KARNATAKA BOARD",
        "KSEAB",
    ],

    "icse": [
        "COUNCIL FOR THE INDIAN SCHOOL CERTIFICATE EXAMINATIONS",
        "INDIAN CERTIFICATE OF SECONDARY EDUCATION",
        "ICSE",
    ],

    "aadhaar": [
        "AADHAAR",
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
        "UIDAI",
        "GOVERNMENT OF INDIA",
    ],

    "pan": [
        "PERMANENT ACCOUNT NUMBER",
        "INCOME TAX DEPARTMENT",
        "INCOME TAX DEPARTMENT GOVERNMENT OF INDIA",
        "PAN",
    ],

    "marksheet": [
        "MARKS STATEMENT",
        "MARKS STATEMENT CUM CERTIFICATE",
        "MARKSHEET",
        "STATEMENT OF MARKS",
        "SUBJECT",
        "SUBJECT CODE",
        "THEORY",
        "TOTAL",
        "GRADE",
        "RESULT",
        "ROLL NO",
        "ROLL NUMBER",
    ],

    "identity": [
        "DATE OF BIRTH",
        "DOB",
        "NAME",
        "GOVERNMENT OF INDIA",
        "FATHER",
        "MOTHER",
    ],
}


EXAM_PHRASES = [

    "SECONDARY SCHOOL EXAMINATION",

    "SENIOR SCHOOL CERTIFICATE EXAMINATION",

    "HIGH SCHOOL EXAMINATION",

    "INTERMEDIATE EXAMINATION",

    "SECONDARY SCHOOL CERTIFICATE",

    "SENIOR SCHOOL CERTIFICATE",
]


# ============================================================
# OCR ITEM HELPERS
# ============================================================

def get_ocr_items(
    ocr_result: dict
) -> list[dict]:

    items = ocr_result.get(
        "text",
        []
    )

    if not isinstance(
        items,
        list
    ):
        return []

    return [
        item
        for item in items
        if isinstance(item, dict)
        and str(
            item.get(
                "text",
                ""
            )
        ).strip()
    ]


def item_text(
    item: dict
) -> str:

    return str(
        item.get(
            "text",
            ""
        )
    ).strip()


def item_confidence(
    item: dict
) -> float | None:

    try:

        value = float(
            item.get(
                "confidence"
            )
        )

        if 0 <= value <= 1:
            return value

    except (
        TypeError,
        ValueError
    ):

        pass

    return None


def item_box(
    item: dict
):

    box = item.get(
        "box"
    )

    if (
        not isinstance(
            box,
            list
        )
        or not box
    ):
        return None

    return box


def box_bounds(
    box
):

    if not box:
        return None

    points = []

    for point in box:

        if (
            isinstance(
                point,
                (list, tuple)
            )
            and len(point) >= 2
        ):

            try:

                points.append(
                    (
                        float(point[0]),
                        float(point[1])
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                continue

    if not points:
        return None

    xs = [
        point[0]
        for point in points
    ]

    ys = [
        point[1]
        for point in points
    ]

    return (
        min(xs),
        min(ys),
        max(xs),
        max(ys),
    )


# ============================================================
# KEYWORD SIGNALS
# ============================================================

def find_keyword_matches(
    text: str
) -> dict:

    matches = {}

    for group, patterns in KEYWORD_GROUPS.items():

        found = [
            pattern
            for pattern in patterns
            if pattern in text
        ]

        if found:
            matches[group] = found

    return matches


def find_exam_phrases(
    text: str
) -> list[str]:

    return [
        phrase
        for phrase in EXAM_PHRASES
        if phrase in text
    ]


# ============================================================
# NUMBER / ID PATTERNS
# ============================================================

def detect_patterns(
    text: str
) -> dict:

    aadhaar_candidates = re.findall(
        r"(?<!\d)(?:\d[\s-]?){12}(?!\d)",
        text
    )

    pan_candidates = re.findall(
        r"\b[A-Z]{5}\d{4}[A-Z]\b",
        text
    )

    date_candidates = re.findall(
        r"\b(?:0?[1-9]|[12]\d|3[01])"
        r"[/-]"
        r"(?:0?[1-9]|1[0-2])"
        r"[/-]"
        r"(?:19|20)\d{2}\b",
        text
    )

    year_candidates = re.findall(
        r"\b(?:19|20)\d{2}\b",
        text
    )

    long_number_candidates = re.findall(
        r"\b\d{6,12}\b",
        text
    )

    short_number_candidates = re.findall(
        r"\b\d{2,4}\b",
        text
    )

    return {

        "aadhaar_candidates":
            list(
                dict.fromkeys(
                    aadhaar_candidates
                )
            ),

        "pan_candidates":
            list(
                dict.fromkeys(
                    pan_candidates
                )
            ),

        "date_candidates":
            list(
                dict.fromkeys(
                    date_candidates
                )
            ),

        "year_candidates":
            list(
                dict.fromkeys(
                    year_candidates
                )
            ),

        "long_number_candidates":
            list(
                dict.fromkeys(
                    long_number_candidates
                )
            ),

        "short_number_candidates":
            list(
                dict.fromkeys(
                    short_number_candidates
                )
            ),
    }


# ============================================================
# LAYOUT SIGNALS
# ============================================================

def detect_layout_signals(
    items: list[dict]
) -> dict:

    bounds = []

    for item in items:

        result = box_bounds(
            item_box(item)
        )

        if result:
            bounds.append(result)

    if not bounds:

        return {
            "item_count": len(items),
            "has_coordinates": False,
            "document_width_estimate": None,
            "document_height_estimate": None,
            "row_count_estimate": 0,
            "has_multiple_rows": False,
            "has_table_like_alignment": False,
        }

    x1 = min(
        item[0]
        for item in bounds
    )

    y1 = min(
        item[1]
        for item in bounds
    )

    x2 = max(
        item[2]
        for item in bounds
    )

    y2 = max(
        item[3]
        for item in bounds
    )

    centers = []

    for bx in bounds:

        centers.append(
            (bx[1] + bx[3]) / 2
        )

    centers.sort()

    rows = []

    for center in centers:

        if (
            not rows
            or abs(
                center -
                rows[-1][-1]
            ) > 12
        ):

            rows.append(
                [center]
            )

        else:

            rows[-1].append(
                center
            )

    row_item_counts = []

    for row in rows:

        row_y = mean(row)

        count = 0

        for bx in bounds:

            item_center = (
                bx[1] + bx[3]
            ) / 2

            if abs(
                item_center -
                row_y
            ) <= 12:

                count += 1

        row_item_counts.append(
            count
        )

    table_like = (
        len(rows) >= 4
        and sum(
            count >= 3
            for count in row_item_counts
        ) >= 3
    )

    return {

        "item_count":
            len(items),

        "has_coordinates":
            True,

        "document_width_estimate":
            round(
                x2 - x1,
                2
            ),

        "document_height_estimate":
            round(
                y2 - y1,
                2
            ),

        "row_count_estimate":
            len(rows),

        "has_multiple_rows":
            len(rows) >= 3,

        "has_table_like_alignment":
            table_like,
    }


# ============================================================
# MARKS STRUCTURE
# ============================================================

def detect_marks_structure(
    text: str,
    items: list[dict]
) -> dict:

    subject_terms = [
        "SUBJECT",
        "SUBJECT CODE",
        "SUBJECTS",
    ]

    mark_terms = [
        "THEORY",
        "INTERNAL",
        "INTERNAL ASSESSMENT",
        "PRACTICAL",
        "TOTAL",
        "GRADE",
    ]

    found_subject_terms = [
        term
        for term in subject_terms
        if term in text
    ]

    found_mark_terms = [
        term
        for term in mark_terms
        if term in text
    ]

    numeric_items = 0

    for item in items:

        value = item_text(
            item
        )

        if re.fullmatch(
            r"\d{1,3}",
            value
        ):

            try:

                number = int(value)

                if 0 <= number <= 100:
                    numeric_items += 1

            except ValueError:

                pass

    return {

        "has_subject_terms":
            bool(
                found_subject_terms
            ),

        "subject_terms":
            found_subject_terms,

        "mark_terms":
            found_mark_terms,

        "has_marks_terms":
            bool(
                found_mark_terms
            ),

        "numeric_mark_like_items":
            numeric_items,

        "likely_marks_table":
            (
                len(
                    found_subject_terms
                ) > 0

                and

                len(
                    found_mark_terms
                ) >= 2

                and

                numeric_items >= 3
            ),
    }


# ============================================================
# OCR QUALITY
# ============================================================

def detect_ocr_quality(
    items: list[dict]
) -> dict:

    confidences = [
        confidence

        for confidence in (
            item_confidence(item)
            for item in items
        )

        if confidence is not None
    ]

    if confidences:

        average = round(
            mean(confidences),
            4
        )

        minimum = round(
            min(confidences),
            4
        )

    else:

        average = None
        minimum = None

    return {

        "item_count":
            len(items),

        "confidence_count":
            len(confidences),

        "average_confidence":
            average,

        "minimum_confidence":
            minimum,

        "low_confidence_items":
            sum(
                confidence < 0.60
                for confidence in confidences
            ),
    }


# ============================================================
# FAMILY HINTS
# ============================================================

def build_family_hints(
    text: str,
    keyword_matches: dict,
    patterns: dict,
    marks_structure: dict
) -> dict:

    hints = {

        "education":
            0,

        "identity":
            0,

        "marksheet":
            0,
    }

    if "marksheet" in keyword_matches:

        hints["education"] += 2

    if marks_structure[
        "likely_marks_table"
    ]:

        hints["education"] += 3

        hints["marksheet"] += 4

    if "cbse" in keyword_matches:

        hints["education"] += 5

        hints["marksheet"] += 5

    if "up_board" in keyword_matches:

        hints["education"] += 5

        hints["marksheet"] += 5

    if "bihar_board" in keyword_matches:

        hints["education"] += 5

        hints["marksheet"] += 5

    if "aadhaar" in keyword_matches:

        hints["identity"] += 8

    if "pan" in keyword_matches:

        hints["identity"] += 8

    if patterns[
        "aadhaar_candidates"
    ]:

        hints["identity"] += 8

    if patterns[
        "pan_candidates"
    ]:

        hints["identity"] += 8

    return hints


# ============================================================
# MAIN FEATURE EXTRACTION
# ============================================================

def extract_features(
    ocr_result: dict
) -> dict:

    items = get_ocr_items(
        ocr_result
    )

    raw_text = ocr_result.get(
        "raw_text"
    )

    if not raw_text:

        raw_text = "\n".join(
            item_text(item)
            for item in items
        )

    normalized = normalize_text(
        raw_text
    )

    keyword_matches = (
        find_keyword_matches(
            normalized
        )
    )

    patterns = detect_patterns(
        normalized
    )

    layout = detect_layout_signals(
        items
    )

    marks_structure = (
        detect_marks_structure(
            normalized,
            items
        )
    )

    quality = detect_ocr_quality(
        items
    )

    exam_phrases = (
        find_exam_phrases(
            normalized
        )
    )

    family_hints = (
        build_family_hints(
            normalized,
            keyword_matches,
            patterns,
            marks_structure
        )
    )

    return {

        "success":
            True,

        "source": {

            "image":
                ocr_result.get(
                    "image"
                ),

            "line_count":
                len(items),
        },

        "normalized_text":
            normalized,

        "keyword_matches":
            keyword_matches,

        "exam_phrases":
            exam_phrases,

        "patterns":
            patterns,

        "marks_structure":
            marks_structure,

        "layout":
            layout,

        "ocr_quality":
            quality,

        "family_hints":
            family_hints,
    }


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(
    path: Path
) -> dict:

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


def save_json(
    path: Path,
    data: dict
):

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) not in {
        2,
        3
    }:

        print(
            "Usage: "
            "python app/ocr/feature_extractor.py "
            "<ocr_result.json> [output.json]"
        )

        sys.exit(1)

    input_path = Path(
        sys.argv[1]
    )

    try:

        ocr_result = load_json(
            input_path
        )

        features = extract_features(
            ocr_result
        )

        if len(sys.argv) == 3:

            output_path = Path(
                sys.argv[2]
            )

        else:

            output_path = (
                input_path.parent /
                "ocr_features.json"
            )

        save_json(
            output_path,
            features
        )

        print(
            json.dumps(
                features,
                indent=2,
                ensure_ascii=False
            )
        )

        print(
            f"\nFeatures saved to: "
            f"{output_path}"
        )

    except Exception as error:

        print(
            f"ERROR: {error}"
        )

        sys.exit(1)