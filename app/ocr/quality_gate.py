import re
import sys

# ============================================================
# NORMALIZATION
# ============================================================

def normalize(text):
    if not text:
        return ""

    text = str(text).upper()

    text = re.sub(r"[^A-Z0-9\s/.-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# HELPERS
# ============================================================

def contains_any(text, patterns):
    text = normalize(text)

    return any(
        normalize(pattern) in text
        for pattern in patterns
    )


def count_matches(text, patterns):
    text = normalize(text)

    return sum(
        1
        for pattern in patterns
        if normalize(pattern) in text
    )


# ============================================================
# DOCUMENT-SPECIFIC QUALITY
# ============================================================

def check_cbse(text):

    text = normalize(text)

    score = 0
    reasons = []
    critical_failures = []

    # --------------------------------------------------------
    # Board
    # --------------------------------------------------------

    if (
        "CENTRAL BOARD OF SECONDARY EDUCATION" in text
        or
        "CENTRAL BOARD OF SECONDARY" in text
        and "EDUCATION" in text
    ):
        score += 25
        reasons.append("CBSE board detected")

    else:
        critical_failures.append(
            "CBSE board not detected"
        )

    # --------------------------------------------------------
    # Examination
    # --------------------------------------------------------

    if (
        "SECONDARY SCHOOL EXAMINATION" in text
        or
        "SENIOR SCHOOL CERTIFICATE EXAMINATION" in text
        or
        (
            "SECONDARY" in text
            and
            "SCHOOL" in text
            and
            "EXAMINATION" in text
        )
    ):
        score += 20
        reasons.append(
            "CBSE examination detected"
        )

    else:
        critical_failures.append(
            "CBSE examination title not detected"
        )

    # --------------------------------------------------------
    # Marks statement
    # --------------------------------------------------------

    marks_statement = (
        "MARKS STATEMENT" in text
        or
        (
            "MARKS" in text
            and
            "STATEMENT" in text
        )
    )

    if marks_statement:

        score += 10

        reasons.append(
            "Marks statement detected"
        )

    # --------------------------------------------------------
    # Roll number
    # --------------------------------------------------------

    if (
        re.search(r"\bROLL\s*NO\b", text)
        or
        "ROLL" in text
        and "NO" in text
    ):
        score += 10

        reasons.append(
            "Roll number field detected"
        )

    else:

        critical_failures.append(
            "Roll number field not detected"
        )

    # --------------------------------------------------------
    # DOB
    # --------------------------------------------------------

    dob_found = (
        "DATE OF BIRTH" in text
        or
        (
            "DATE" in text
            and
            "BIRTH" in text
        )
    )

    date_found = re.search(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
        text
    )

    if dob_found and date_found:

        score += 5

        reasons.append(
            "DOB detected"
        )

    else:

        critical_failures.append(
            "DOB not confidently detected"
        )

    # --------------------------------------------------------
    # Student name context
    #
    # Tesseract can produce:
    #
    # THIS IS TO CERTIFY THAT
    # THIS STO CERTIFY THAT
    # CERTIFY THAT
    # --------------------------------------------------------

    name_context = False

    if "CERTIFY THAT" in text:
        name_context = True

    elif "CERTIFY" in text and "THAT" in text:
        name_context = True

    elif "THIS" in text and "CERTIFY" in text:
        name_context = True

    elif "CERTIFY" in text:
        name_context = True

    if name_context:

        score += 10

        reasons.append(
            "Student-name context detected"
        )

    else:

        critical_failures.append(
            "Student-name context not detected"
        )

    # --------------------------------------------------------
    # Subject codes
    # --------------------------------------------------------

    subject_codes = re.findall(
        r"\b(?:0[0-9]{2}|[1-9][0-9]{2})\b",
        text
    )

    unique_codes = set(
        subject_codes
    )

    # Require several codes because one 3-digit number could
    # simply be a roll/school/reference number.

    if len(unique_codes) >= 3:

        score += 10

        reasons.append(
            f"{len(unique_codes)} subject-code candidates detected"
        )

    else:

        critical_failures.append(
            "Insufficient subject codes"
        )

    # --------------------------------------------------------
    # Marks-table detection
    #
    # Don't depend on exact ordering.
    # OCR frequently separates table headers.
    # --------------------------------------------------------

    table_keywords = [
        "SUBJECT",
        "THEORY",
        "TOTAL",
        "GRADE",
        "CODE",
        "MARKS",
        "POSITIONAL"
    ]

    found_table_keywords = [
        keyword
        for keyword in table_keywords
        if keyword in text
    ]

    # 3+ table signals = strong evidence
    if len(found_table_keywords) >= 3:

        score += 10

        reasons.append(
            "Marks table detected: "
            + ", ".join(found_table_keywords)
        )

    elif len(found_table_keywords) >= 2:

        score += 5

        reasons.append(
            "Partial marks-table detected: "
            + ", ".join(found_table_keywords)
        )

    else:

        critical_failures.append(
            "Marks-table terminology insufficient"
        )

    # --------------------------------------------------------
    # Final decision
    # --------------------------------------------------------

    if score >= 75 and len(critical_failures) <= 1:

        decision = "ACCEPT"

    elif score >= 55:

        decision = "REVIEW"

    else:

        decision = "FALLBACK"

    return {
        "document_type": "CBSE_MARKSHEET",
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "critical_failures": critical_failures
    }

# ============================================================
# PAN
# ============================================================

def check_pan(text):

    text = normalize(text)

    score = 0
    reasons = []
    failures = []

    # --------------------------------------------------------
    # PAN number
    # --------------------------------------------------------

    pan_candidates = re.findall(
        r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        text
    )

    if pan_candidates:
        score += 40
        reasons.append(
            "Valid PAN-format number detected"
        )

    else:
        failures.append(
            "PAN number not detected"
        )

    # --------------------------------------------------------
    # Income Tax
    # --------------------------------------------------------

    if (
        "INCOME TAX DEPARTMENT" in text
        or
        "INCOME TAX" in text
    ):
        score += 25
        reasons.append(
            "Income Tax Department detected"
        )

    else:
        failures.append(
            "Income Tax identity not detected"
        )

    # --------------------------------------------------------
    # PAN card
    # --------------------------------------------------------

    if (
        "PERMANENT ACCOUNT NUMBER" in text
        or
        "PAN CARD" in text
    ):
        score += 20
        reasons.append(
            "PAN card terminology detected"
        )

    # --------------------------------------------------------
    # DOB
    # --------------------------------------------------------

    if (
        "DATE OF BIRTH" in text
        and
        re.search(
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
            text
        )
    ):
        score += 15
        reasons.append(
            "DOB detected"
        )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    if score >= 80:
        decision = "ACCEPT"

    elif score >= 55:
        decision = "REVIEW"

    else:
        decision = "FALLBACK"

    return {
        "document_type": "PAN_CARD",
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "critical_failures": failures
    }


# ============================================================
# AADHAAR
# ============================================================

def check_aadhaar(text):

    text = normalize(text)

    score = 0
    reasons = []
    failures = []

    # --------------------------------------------------------
    # Aadhaar number
    # --------------------------------------------------------

    aadhaar_candidates = re.findall(
        r"\b\d{4}\s\d{4}\s\d{4}\b",
        text
    )

    if aadhaar_candidates:

        score += 35

        reasons.append(
            "12-digit Aadhaar-format number detected"
        )

    else:

        # OCR may remove spaces
        compact_candidates = re.findall(
            r"\b\d{12}\b",
            text
        )

        if compact_candidates:

            score += 30

            reasons.append(
                "12-digit Aadhaar candidate detected"
            )

        else:

            failures.append(
                "Aadhaar number not detected"
            )

    # --------------------------------------------------------
    # UIDAI
    # --------------------------------------------------------

    if (
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA"
        in text
    ):
        score += 30

        reasons.append(
            "UIDAI detected"
        )

    elif "UIDAI" in text:

        score += 25

        reasons.append(
            "UIDAI detected"
        )

    else:

        failures.append(
            "UIDAI identity not detected"
        )

    # --------------------------------------------------------
    # Government of India
    # --------------------------------------------------------

    if "GOVERNMENT OF INDIA" in text:

        score += 15

        reasons.append(
            "Government of India detected"
        )

    # --------------------------------------------------------
    # DOB
    # --------------------------------------------------------

    if (
        "DATE OF BIRTH" in text
        or
        "YEAR OF BIRTH" in text
    ):
        score += 10

        reasons.append(
            "DOB/YOB field detected"
        )

    # --------------------------------------------------------
    # Address
    # --------------------------------------------------------

    if "ADDRESS" in text:

        score += 10

        reasons.append(
            "Address field detected"
        )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    if score >= 75:

        decision = "ACCEPT"

    elif score >= 50:

        decision = "REVIEW"

    else:

        decision = "FALLBACK"

    return {
        "document_type": "AADHAAR",
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "critical_failures": failures
    }


# ============================================================
# GENERIC QUALITY CHECK
# ============================================================

def check_generic(text):

    text = normalize(text)

    score = 0

    if len(text) > 30:
        score += 30

    if len(text.split()) > 10:
        score += 30

    if re.search(
        r"\b\d{4}\b",
        text
    ):
        score += 20

    if re.search(
        r"[A-Z]{3,}",
        text
    ):
        score += 20

    if score >= 70:
        decision = "ACCEPT"

    elif score >= 40:
        decision = "REVIEW"

    else:
        decision = "FALLBACK"

    return {
        "document_type": "GENERIC",
        "score": score,
        "decision": decision,
        "reasons": [],
        "critical_failures": []
    }


# ============================================================
# MAIN QUALITY GATE
# ============================================================

def evaluate(text, document_type):

    document_type = (
        document_type or ""
    ).upper()

    if "CBSE" in document_type:

        return check_cbse(text)

    if "PAN" in document_type:

        return check_pan(text)

    if "AADHAAR" in document_type:

        return check_aadhaar(text)

    return check_generic(text)


# ============================================================
# CLI TEST
# ============================================================

def main():

    if len(sys.argv) < 3:

        print(
            "Usage:\n"
            "python app/ocr/quality_gate.py "
            "<document_type> <ocr_text_file>"
        )

        sys.exit(1)

    document_type = sys.argv[1]

    text_file = Path(
        sys.argv[2]
    )

    if not text_file.exists():

        print(
            f"File not found: {text_file}"
        )

        sys.exit(1)

    text = text_file.read_text(
        encoding="utf-8"
    )

    result = evaluate(
        text,
        document_type
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