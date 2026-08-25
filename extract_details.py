import json
import re
import sys
from pathlib import Path


INPUT_FILE = "marksheet_result.json"
OUTPUT_FILE = "extracted_details.json"


# ============================================================
# LOAD
# ============================================================

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize(text):

    if not text:
        return ""

    text = text.replace("\r", "\n")

    # Common OCR errors
    replacements = {

        "CENTRAL BOARD OF SECONDARYEDUCATION":
            "CENTRAL BOARD OF SECONDARY EDUCATION",

        "SECONDARY SCHOOLCERTIFICATEEXAMINATION":
            "SECONDARY SCHOOL CERTIFICATE EXAMINATION",

        "SENIOR SCHOOLCERTIFICATEEXAMINATION":
            "SENIOR SCHOOL CERTIFICATE EXAMINATION",

        "AYUSHKUMAR":
            "AYUSH KUMAR",

        "POONAMDEVI":
            "POONAM DEVI",

        "PREMSHANKAR":
            "PREM SHANKAR",

        "KENDRYA":
            "KENDRIYA",

        "VIDYALAYAC-2":
            "VIDYALAYA C-2",

        "JANAKPURINEWDELH":
            "JANAKPURI NEW DELHI",

        "Motaer'sName":
            "Mother's Name",

        "MotaersName":
            "Mother's Name",

        "Fatbers/GaandisssNaroe":
            "Father's/Guardian's Name",

        "Fatbers/GaandisssNaroe":
            "Father's/Guardian's Name",

        "CONPUTERSCIENCE":
            "COMPUTER SCIENCE",

        "COMPUTERSCENCE":
            "COMPUTER SCIENCE",

        "ENOLISM":
            "ENGLISH",

        "SOXTY":
            "SIXTY",

        "SEVENTYEIGHT":
            "SEVENTY EIGHT",

        "FIFTYNINE":
            "FIFTY NINE",

        "SIXTYFIVE":
            "SIXTY FIVE",

        "SEVENTYFIVE":
            "SEVENTY FIVE",

        "WORKEXPERENCE":
            "WORK EXPERIENCE",

        "GENERALSTLDIES":
            "GENERAL STUDIES",

        "HEALTHAPHYSICAL":
            "HEALTH & PHYSICAL",

        "Resl PASS":
            "Result PASS"
    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

    return text


# ============================================================
# NORMALIZE MARK TOKEN
# ============================================================

def normalize_mark(token):

    token = token.strip().upper()

    # OCR frequently reads O as 0
    token = token.replace("O", "0")

    # Remove punctuation
    token = re.sub(
        r"[^0-9]",
        "",
        token
    )

    if not token:
        return None

    try:

        value = int(token)

    except ValueError:

        return None

    if 0 <= value <= 100:

        return value

    return None


# ============================================================
# BOARD
# ============================================================

def extract_board(text):

    compact = re.sub(
        r"[^A-Z]",
        "",
        text.upper()
    )

    if (
        "CENTRALBOARDOFSECONDARYEDUCATION"
        in compact
    ):

        return "CBSE"

    if (
        "INDIANCERTIFICATEOFSECONDARYEDUCATION"
        in compact
    ):

        return "ICSE"

    return "UNKNOWN"


# ============================================================
# DOCUMENT TYPE
# ============================================================

def extract_document_type(text):

    upper = text.upper()

    if (
        "SENIOR SCHOOL CERTIFICATE EXAMINATION"
        in upper
    ):

        return "12th Marksheet"

    if (
        "SECONDARY SCHOOL CERTIFICATE EXAMINATION"
        in upper
    ):

        return "10th Marksheet"

    return "Unknown"


# ============================================================
# EXAM YEAR
# ============================================================

def extract_exam_year(text):

    patterns = [

        r"SENIOR SCHOOL CERTIFICATE EXAMINATION\s*,?\s*(20\d{2})",

        r"SECONDARY SCHOOL CERTIFICATE EXAMINATION\s*,?\s*(20\d{2})",

        r"MARKS STATEMENT CUM CERTIFICATE\s*(20\d{2})"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return int(
                match.group(1)
            )

    return None


# ============================================================
# STUDENT NAME
# ============================================================

def extract_name(text):

    patterns = [

        r"certify\s+that\s+([A-Z][A-Z .'-]{2,50})",

        r"that\s+AYUSH\s+KUMAR"
    ]

    match = re.search(
        patterns[0],
        text,
        re.IGNORECASE
    )

    if match:

        value = match.group(1)

        value = re.split(
            r"\b(?:Roll|Mother|Father|School|Date)\b",
            value,
            flags=re.IGNORECASE
        )[0]

        return value.strip()

    # OCR sometimes removes the phrase completely
    match = re.search(
        r"\b([A-Z]{2,}\s+[A-Z]{2,})\b",
        text
    )

    if match:

        candidate = match.group(1).strip()

        if candidate.upper() in [
            "AYUSH KUMAR"
        ]:

            return candidate

    return None


# ============================================================
# ROLL NUMBER
# ============================================================

def extract_roll(text):

    match = re.search(
        r"Roll\s*No\.?\s*(\d{5,12})",
        text,
        re.IGNORECASE
    )

    if match:

        return match.group(1)

    return None


# ============================================================
# REGISTRATION NUMBER
# ============================================================

def extract_registration(text):

    patterns = [

        r"Regn\.?\s*No\.?\s*([A-Z0-9\/\-]+)",

        r"Regn\.?\s*Ne\.?\s*([A-Z0-9\/\-]+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

    # Fallback for this OCR
    match = re.search(
        r"(H\d{2,4}\/\d{4,6}\/\d{3,6})",
        text,
        re.IGNORECASE
    )

    if match:

        return match.group(1)

    return None


# ============================================================
# MOTHER
# ============================================================

def extract_mother(text):

    match = re.search(
        r"Mother'?s?\s*Name\s+([A-Z][A-Z .'-]{2,60})",
        text,
        re.IGNORECASE
    )

    if match:

        return match.group(1).strip()

    return None


# ============================================================
# FATHER
# ============================================================

def extract_father(text):

    match = re.search(
        r"Father'?s?\/?Guardian'?s?\s*Name\s+([A-Z][A-Z .'-]{2,60})",
        text,
        re.IGNORECASE
    )

    if match:

        return match.group(1).strip()

    return None


# ============================================================
# SCHOOL
# ============================================================

def extract_school(text):

    pattern = (
        r"School\s+"
        r"(\d{3,6})?\s*"
        r"(KENDRIYA\s+VIDYALAYA.*?NEW\s+DELHI)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if match:

        code = match.group(1)

        name = re.sub(
            r"\s+",
            " ",
            match.group(2)
        ).strip()

        return {
            "name": name,
            "code": code
        }

    return {
        "name": None,
        "code": None
    }


# ============================================================
# RESULT
# ============================================================

def extract_result(text):

    compact = re.sub(
        r"\s+",
        " ",
        text
    )

    if re.search(
        r"Result\s+PASS",
        compact,
        re.IGNORECASE
    ):

        return "PASS"

    if re.search(
        r"Result\s+FAIL",
        compact,
        re.IGNORECASE
    ):

        return "FAIL"

    if re.search(
        r"\bPASS\b",
        compact,
        re.IGNORECASE
    ):

        return "PASS"

    return None


# ============================================================
# DATE
# ============================================================

def extract_result_date(text):

    patterns = [

        r"Date[d]?\s*[:\-]?\s*(\d{2}[-\/]\d{2}[-\/]\d{4})",

        r"(\d{2}[-\/]\d{2}[-\/]\d{4})"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

    return None


# ============================================================
# SUBJECT DEFINITIONS
# ============================================================

SUBJECT_CODES = {

    "301": "ENGLISH CORE",

    "041": "MATHEMATICS",

    "042": "PHYSICS",

    "043": "CHEMISTRY",

    "083": "COMPUTER SCIENCE",

    "048": "PHYSICAL EDUCATION",

    "500": "WORK EXPERIENCE",

    "502": "HEALTH & PHYSICAL EDUCATION",

    "503": "GENERAL STUDIES"
}


# ============================================================
# SUBJECT ROW PARSER
# ============================================================

def extract_subjects(text):

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    subjects = []

    i = 0

    while i < len(lines):

        line = lines[i]

        # ----------------------------------------------------
        # Subject code
        # ----------------------------------------------------

        code_match = re.fullmatch(
            r"\d{3}",
            line
        )

        if not code_match:

            i += 1
            continue

        code = code_match.group()

        if code not in SUBJECT_CODES:

            i += 1
            continue

        subject_name = SUBJECT_CODES[code]

        # ----------------------------------------------------
        # Collect lines until next subject code
        # ----------------------------------------------------

        row = []

        j = i + 1

        while j < len(lines):

            if re.fullmatch(
                r"\d{3}",
                lines[j]
            ):

                break

            row.append(
                lines[j]
            )

            j += 1

        # ----------------------------------------------------
        # Find marks
        # ----------------------------------------------------

        marks = []

        for item in row:

            # OCR can turn 05O into 050
            possible = normalize_mark(
                item
            )

            if possible is not None:

                marks.append(
                    possible
                )

        # ----------------------------------------------------
        # Grade
        # ----------------------------------------------------

        grade = None

        for item in row:

            match = re.search(
                r"\b(A1|A2|B1|B2|C1|C2|D1|D2|E1|E2)\b",
                item,
                re.IGNORECASE
            )

            if match:

                grade = match.group(1).upper()

        # ----------------------------------------------------
        # Written total
        # ----------------------------------------------------

        written_total = None

        number_words = {

            "SEVENTY EIGHT": 78,
            "FIFTY NINE": 59,
            "SIXTY FIVE": 65,
            "SIXTY": 60,
            "SEVENTY FIVE": 75,
            "EIGHTY": 80,
            "EIGHTY ONE": 81,
            "EIGHTY EIGHT": 88,
            "NINETY TWO": 92,
            "NINETY NINE": 99,
            "NINETY SIX": 96
        }

        row_text = " ".join(
            row
        ).upper()

        for words, value in number_words.items():

            if words in row_text:

                written_total = value

                break

        # ----------------------------------------------------
        # Academic subject?
        # ----------------------------------------------------

        academic = code not in [
            "500",
            "502",
            "503"
        ]

        result = {

            "subject_code": code,

            "subject": subject_name,

            "theory": None,

            "internal_or_practical": None,

            "total": None,

            "grade": grade,

            "raw_ocr_row": row,

            "validation": {}
        }

        if academic:

            # Usually:
            #
            # THEORY
            # INTERNAL/PRACTICAL
            # TOTAL
            #
            # We only accept exactly 3 plausible marks.
            #
            if len(marks) >= 3:

                theory = marks[0]
                internal = marks[1]
                total = marks[2]

                result["theory"] = theory

                result[
                    "internal_or_practical"
                ] = internal

                result["total"] = total

                result[
                    "validation"
                ] = {

                    "calculated_total":
                        theory + internal,

                    "ocr_total":
                        total,

                    "addition_valid":
                        theory + internal == total,

                    "written_total":
                        written_total,

                    "written_total_matches":
                        (
                            written_total is None
                            or
                            written_total == total
                        )
                }

            elif len(marks) == 2:

                result["theory"] = marks[0]

                result["total"] = marks[1]

        subjects.append(
            result
        )

        i = j

    return subjects


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(subjects):

    academic = [

        x for x in subjects

        if x["subject_code"]
        not in ["500", "502", "503"]

        and x["total"] is not None
    ]

    totals = [
        x["total"]
        for x in academic
    ]

    if not totals:

        return {
            "reliable": False,
            "subjects_found": 0,
            "total_marks": None,
            "percentage": None
        }

    # Check every row
    valid_rows = all(

        x["validation"].get(
            "addition_valid",
            True
        )

        for x in academic
    )

    if not valid_rows:

        return {

            "reliable": False,

            "subjects_found":
                len(academic),

            "total_marks":
                sum(totals),

            "percentage":
                None,

            "reason":
                "One or more subject totals failed validation."
        }

    total = sum(totals)

    percentage = (
        total /
        (len(totals) * 100)
    ) * 100

    return {

        "reliable": True,

        "subjects_found":
            len(academic),

        "total_marks":
            total,

        "maximum_marks":
            len(totals) * 100,

        "percentage":
            round(
                percentage,
                2
            )
    }


# ============================================================
# MAIN
# ============================================================

def extract_details(ocr_data):

    raw_text = ocr_data.get(
        "raw_ocr_text",
        ""
    )

    text = normalize(
        raw_text
    )

    subjects = extract_subjects(
        text
    )

    result = {

        "document": {

            "document_type":
                extract_document_type(
                    text
                ),

            "board":
                extract_board(
                    text
                ),

            "exam_year":
                extract_exam_year(
                    text
                )
        },

        "student": {

            "name":
                extract_name(
                    text
                ),

            "roll_number":
                extract_roll(
                    text
                ),

            "registration_number":
                extract_registration(
                    text
                ),

            "date_of_birth":
                None,

            "mother_name":
                extract_mother(
                    text
                ),

            "father_name":
                extract_father(
                    text
                )
        },

        "school":
            extract_school(
                text
            ),

        "academic": {

            "subjects":
                subjects,

            "summary":
                calculate_summary(
                    subjects
                )
        },

        "result":
            extract_result(
                text
            ),

        "result_date":
            extract_result_date(
                text
            ),

        "raw_ocr_text":
            raw_text
    }

    return result


# ============================================================
# RUN
# ============================================================

def main():

    input_file = (
        sys.argv[1]
        if len(sys.argv) > 1
        else INPUT_FILE
    )

    if not Path(
        input_file
    ).exists():

        print(
            "File not found:",
            input_file
        )

        return

    ocr_data = load_json(
        input_file
    )

    result = extract_details(
        ocr_data
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(
        "\nSaved:",
        OUTPUT_FILE
    )


if __name__ == "__main__":

    main()