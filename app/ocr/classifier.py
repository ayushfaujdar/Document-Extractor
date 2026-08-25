import re
import json
import sys
from pathlib import Path


def normalize_text(text):
    text = text.upper()

    replacements = {
        "CENTRAL BOARD OFSECONDARY EDUCATION":
            "CENTRAL BOARD OF SECONDARY EDUCATION",

        "BOARD OFSECONDARY EDUCATION":
            "BOARD OF SECONDARY EDUCATION",

        "SECONDARYSCHOOL":
            "SECONDARY SCHOOL",

        "SENIORSCHOOL":
            "SENIOR SCHOOL",

        "CERTIFICATEEXAMINATION":
            "CERTIFICATE EXAMINATION",

        "SCHOOLCERTIFICATE":
            "SCHOOL CERTIFICATE",

        "BOARD OF SECONDARYEDUCATION":
            "BOARD OF SECONDARY EDUCATION",

        "INCOMETAXDEPARTMENT":
            "INCOME TAX DEPARTMENT",

        "PERMANENTACCOUNTNUMBERCARD":
            "PERMANENT ACCOUNT NUMBER CARD",

        "UNIQUEIDENTIFICATIONAUTHORITYOFINDIA":
            "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
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


def contains_any(text, patterns):
    return [
        pattern
        for pattern in patterns
        if pattern in text
    ]


# =========================================================
# DOCUMENT RULES
# =========================================================

RULES = {

    # -----------------------------------------------------
    # CBSE 10TH
    # -----------------------------------------------------

    "CBSE_10TH_MARKSHEET": {

        "board": [
            "CENTRAL BOARD OF SECONDARY EDUCATION",
        ],

        "exam": [
            "SECONDARY SCHOOL EXAMINATION",
        ],

        "negative_exam": [
            "SENIOR SCHOOL CERTIFICATE EXAMINATION",
        ],

        "supporting": [
            "MARKS STATEMENT CUM CERTIFICATE",
            "ROLL NO",
            "MOTHER S NAME",
            "FATHER GUARDIAN S NAME",
            "SUBJECT CODE",
            "TOTAL",
            "GRADE",
        ],
    },

    # -----------------------------------------------------
    # CBSE 12TH
    # -----------------------------------------------------

    "CBSE_12TH_MARKSHEET": {

        "board": [
            "CENTRAL BOARD OF SECONDARY EDUCATION",
        ],

        "exam": [
            "SENIOR SCHOOL CERTIFICATE EXAMINATION",
        ],

        "negative_exam": [
            "SECONDARY SCHOOL EXAMINATION",
        ],

        "supporting": [
            "MARKS STATEMENT CUM CERTIFICATE",
            "ROLL NO",
            "MOTHER S NAME",
            "FATHER GUARDIAN S NAME",
            "SUBJECT CODE",
            "TOTAL",
            "GRADE",
        ],
    },

    # -----------------------------------------------------
    # UP BOARD 10TH
    # -----------------------------------------------------

    "UP_BOARD_10TH_MARKSHEET": {

        "board": [
            "BOARD OF HIGH SCHOOL AND INTERMEDIATE EDUCATION",
            "UTTAR PRADESH",
            "MADHYAMIK SHIKSHA PARISHAD",
        ],

        "exam": [
            "HIGH SCHOOL EXAMINATION",
            "HIGH SCHOOL",
        ],

        "negative_exam": [
            "INTERMEDIATE EXAMINATION",
        ],

        "supporting": [
            "ROLL NO",
            "SUBJECT",
            "TOTAL",
            "RESULT",
        ],
    },

    # -----------------------------------------------------
    # UP BOARD 12TH
    # -----------------------------------------------------

    "UP_BOARD_12TH_MARKSHEET": {

        "board": [
            "BOARD OF HIGH SCHOOL AND INTERMEDIATE EDUCATION",
            "UTTAR PRADESH",
            "MADHYAMIK SHIKSHA PARISHAD",
        ],

        "exam": [
            "INTERMEDIATE EXAMINATION",
            "INTERMEDIATE",
        ],

        "negative_exam": [
            "HIGH SCHOOL EXAMINATION",
        ],

        "supporting": [
            "ROLL NO",
            "SUBJECT",
            "TOTAL",
            "RESULT",
        ],
    },

    # -----------------------------------------------------
    # AADHAAR
    # -----------------------------------------------------

    "AADHAAR": {

        "board": [],

        "exam": [],

        "negative_exam": [],

        "supporting": [
            "AADHAAR",
            "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
            "GOVERNMENT OF INDIA",
            "DATE OF BIRTH",
            "YEAR OF BIRTH",
            "ADDRESS",
        ],
    },

    # -----------------------------------------------------
    # PAN
    # -----------------------------------------------------

    "PAN_CARD": {

        "board": [],

        "exam": [],

        "negative_exam": [],

        "supporting": [
            "INCOME TAX DEPARTMENT",
            "PERMANENT ACCOUNT NUMBER CARD",
            "PERMANENT ACCOUNT NUMBER",
            "FATHER S NAME",
            "DATE OF BIRTH",
        ],
    },
}


def detect_years(text):

    years = re.findall(
        r"\b(?:19|20)\d{2}\b",
        text
    )

    return list(
        dict.fromkeys(years)
    )


def classify_document(raw_text):

    text = normalize_text(
        raw_text
    )

    candidates = []

    for document_type, rules in RULES.items():

        board_matches = contains_any(
            text,
            rules["board"]
        )

        exam_matches = contains_any(
            text,
            rules["exam"]
        )

        negative_matches = contains_any(
            text,
            rules["negative_exam"]
        )

        supporting_matches = contains_any(
            text,
            rules["supporting"]
        )

        score = 0

        # -------------------------------------------------
        # Board identity
        # -------------------------------------------------

        score += (
            len(board_matches) * 40
        )

        # -------------------------------------------------
        # Exam identity
        # -------------------------------------------------

        score += (
            len(exam_matches) * 50
        )

        # -------------------------------------------------
        # Supporting evidence
        # -------------------------------------------------

        score += (
            len(supporting_matches) * 4
        )

        # -------------------------------------------------
        # Contradiction
        # -------------------------------------------------

        score -= (
            len(negative_matches) * 60
        )

        # -------------------------------------------------
        # Special identity-document protection
        # -------------------------------------------------

        if document_type == "AADHAAR":

            if (
                "UNIQUE IDENTIFICATION AUTHORITY OF INDIA"
                in text
            ):
                score += 80

            if "AADHAAR" in text:
                score += 60

        if document_type == "PAN_CARD":

            if (
                "INCOME TAX DEPARTMENT"
                in text
            ):
                score += 80

            if (
                "PERMANENT ACCOUNT NUMBER CARD"
                in text
            ):
                score += 80

        candidates.append({
            "document_type": document_type,
            "score": score,
            "board_matches": board_matches,
            "exam_matches": exam_matches,
            "supporting_matches": supporting_matches,
            "negative_matches": negative_matches,
        })

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    best = candidates[0]

    score = best["score"]

    if score >= 120:
        confidence = 98

    elif score >= 90:
        confidence = 95

    elif score >= 70:
        confidence = 90

    elif score >= 50:
        confidence = 75

    elif score >= 30:
        confidence = 55

    else:
        confidence = 30

    # -----------------------------------------------------
    # Additional ambiguity protection
    # -----------------------------------------------------

    if len(candidates) > 1:

        second = candidates[1]

        score_difference = (
            best["score"]
            - second["score"]
        )

        if score_difference < 15:

            confidence = min(
                confidence,
                70
            )

    # -----------------------------------------------------
    # Decision
    # -----------------------------------------------------

    if confidence >= 85:
        decision = "AUTO_ACCEPT"

    elif confidence >= 60:
        decision = "REVIEW_REQUIRED"

    else:
        decision = "UNKNOWN"

    document_type = (
        best["document_type"]
    )

    if decision == "UNKNOWN":

        document_type = "UNKNOWN"

    return {

        "document_type":
            document_type,

        "confidence":
            confidence,

        "decision":
            decision,

        "exam_years":
            detect_years(text),

        "signals": {

            "board":
                best["board_matches"],

            "exam":
                best["exam_matches"],

            "supporting":
                best["supporting_matches"],

            "contradictions":
                best["negative_matches"],
        },

        "alternatives":
            candidates[1:4],
    }


def main():

    if len(sys.argv) < 2:

        print(
            "Usage: python classifier.py <ocr_result.json>"
        )

        sys.exit(1)

    path = Path(
        sys.argv[1]
    )

    if not path.exists():

        print(
            json.dumps({
                "success": False,
                "error":
                    f"File not found: {path}"
            })
        )

        sys.exit(1)

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    raw_text = (
        data.get(
            "raw_text",
            ""
        )
    )

    result = classify_document(
        raw_text
    )

    output_path = (
        path.parent /
        "classification.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()