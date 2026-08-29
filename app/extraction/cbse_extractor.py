import json
import os
import re
import sys


# ============================================================
# CBSE EXTRACTOR
# Coordinate-aware extraction from PaddleOCR output
#
# IMPORTANT:
# - PaddleOCR remains the OCR engine.
# - This file only interprets PaddleOCR output.
# - Field extraction uses semantic labels + coordinates.
# - We do NOT use arbitrary "first matching date/name".
# ============================================================


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_upper(text):
    return clean_text(text).upper()


def get_box(item):
    box = item.get("box") or item.get("points")

    if not box or len(box) < 4:
        return None

    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]

        return {
            "x1": min(xs),
            "x2": max(xs),
            "y1": min(ys),
            "y2": max(ys),
            "cx": sum(xs) / len(xs),
            "cy": sum(ys) / len(ys),
        }

    except Exception:
        return None


# ============================================================
# LOAD PADDLEOCR OUTPUT
# ============================================================

def load_ocr(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = []

    for item in data.get("text", []):
        text = clean_text(item.get("text"))

        if not text:
            continue

        box = get_box(item)

        if not box:
            continue

        items.append({
            "text": text,
            "upper": normalize_upper(text),
            **box,
        })

    return items


# ============================================================
# GENERIC COORDINATE FIELD EXTRACTION
#
# Moved above the field extractors that now depend on it.
# (Python resolves this at call time either way, but keeping
# it up top makes the read-order match the call-order.)
# ============================================================

def extract_labeled_value(
    items,
    label_pattern,
    min_y=-9999,
    max_y=9999,
    right_only=True,
    max_y_distance=30,
):
    """
    Find a label and its value using coordinates.

    The value must:
      1. Be near the label vertically.
      2. Be to the right of the label when right_only=True.
      3. Not be excessively far away.

    This prevents fields from consuming unrelated lines.
    """

    label_regex = re.compile(
        label_pattern,
        re.I
    )

    labels = []

    for item in items:

        if not label_regex.search(item["text"]):
            continue

        if not (
            min_y <= item["cy"] <= max_y
        ):
            continue

        labels.append(item)

    for label in labels:

        candidates = []

        for item in items:

            if item is label:
                continue

            y_distance = abs(
                item["cy"] - label["cy"]
            )

            if y_distance > max_y_distance:
                continue

            if right_only:

                if item["cx"] <= label["x2"]:
                    continue

            else:

                if item["cx"] > label["x2"]:
                    continue

            if len(item["text"]) > 150:
                continue

            candidates.append(
                (
                    y_distance,
                    abs(item["cx"] - label["x2"]),
                    item
                )
            )

        candidates.sort(
            key=lambda x: (x[0], x[1])
        )

        if candidates:
            return candidates[0][2]["text"]

    return None


# ============================================================
# REGISTRATION NUMBER
# ============================================================

def extract_registration(items):

    patterns = [
        r"REGN\.?\s*NO\.?\s*([A-Z0-9/]+)",
        r"REGN\s*NO\s*([A-Z0-9/]+)",
        r"REGISTRATION\s*NO\.?\s*([A-Z0-9/]+)",
    ]

    for item in items:

        text = item["text"].upper()

        for pattern in patterns:

            match = re.search(pattern, text)

            if match:
                return match.group(1)

    # --------------------------------------------------------
    # Fallback: label ("Regn.No.") and the value are separate
    # OCR boxes. Very common — PaddleOCR frequently splits a
    # printed label from a handwritten/filled value even when
    # they sit on the same visual line.
    # --------------------------------------------------------

    value = extract_labeled_value(
        items,
        r"REGN\.?\s*NO\.?|REGISTRATION\s*NO\.?",
        max_y_distance=25,
    )

    if value:

        match = re.search(
            r"([A-Z0-9/]+)",
            value.upper()
        )

        if match:
            return match.group(1)

    return None


# ============================================================
# ROLL NUMBER
# ============================================================

def extract_roll_number(items):

    for item in items:

        match = re.search(
            r"ROLL\s*NO\.?\s*([0-9]{6,10})",
            item["text"],
            re.I
        )

        if match:
            return match.group(1)

    # --------------------------------------------------------
    # Fallback: "Roll No." and the number are separate boxes.
    # --------------------------------------------------------

    value = extract_labeled_value(
        items,
        r"ROLL\s*NO\.?",
        max_y_distance=25,
    )

    if value:

        match = re.search(
            r"([0-9]{6,10})",
            value
        )

        if match:
            return match.group(1)

    return None


# ============================================================
# DATE OF BIRTH
# ============================================================

def extract_dob(items):
    """
    Extract DOB only from the OCR item containing the
    Date of Birth label.

    Example:
        Date of Birth24/03/200424TH MARCH TWO THOUSANDFOUR

    -> 24/03/2004

    IMPORTANT:
    We never search the entire document for the first date,
    because that can incorrectly return the certificate date.

    NOTE: if the "Date of Birth" label never appears in the
    OCR items at all, this is not something a regex fix can
    solve — check the source scan / OCR crop for that field.
    """

    date_pattern = r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})"

    for item in items:

        text = clean_text(item["text"])

        # Normalize common OCR errors.
        normalized = re.sub(
            r"\s+",
            " ",
            text.upper()
        )

        normalized = normalized.replace(
            "0F",
            "OF"
        )

        # Must contain the DOB label.
        if not re.search(
            r"DATE\s*OF\s*BIRTH|DATEOF\s*BIRTH",
            normalized,
            re.I
        ):
            continue

        match = re.search(
            date_pattern,
            text
        )

        if match:
            return match.group(1).replace(
                "-",
                "/"
            )

    return None

# ============================================================
# EXAMINATION YEAR
# ============================================================

def extract_exam_year(items):
    """
    Handles both the Class 10 title ("SECONDARY SCHOOL
    EXAMINATION") and the Class 12 title ("SENIOR SCHOOL
    CERTIFICATE EXAMINATION") — the original pattern only
    covered Class 10.
    """

    title_pattern = re.compile(
        r"SECONDARY\s+SCHOOL\s+EXAMINATION"
        r"|SENIOR\s+SCHOOL\s+CERTIFICATE\s+EXAMINATION",
        re.I
    )

    for item in items:

        text = clean_text(item["text"])

        if title_pattern.search(text):

            years = re.findall(
                r"\b(20\d{2})\b",
                text
            )

            if years:
                return years[-1]

    return None


# ============================================================
# STUDENT NAME
# ============================================================

def extract_student_name(items):
    """
    CBSE certificate normally contains:

        This is to certify that SHREYA THAKUR

    Extract only the text after the certification phrase.
    """

    patterns = [
        r"THIS\s+IS\s+TO\s+CERTIFY\s+THAT\s+(.+)",
        r"CERTIFY\s+THAT\s+(.+)",
    ]

    for item in items:

        text = clean_text(item["text"])

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.I
            )

            if not match:
                continue

            name = clean_text(match.group(1))

            # Remove anything that looks like the beginning
            # of another field.
            name = re.split(
                r"\b(?:ROLL|ROLL\s*NO|MOTHER|FATHER|DATE|SCHOOL)\b",
                name,
                flags=re.I
            )[0]

            name = clean_text(name)

            if 2 <= len(name) <= 80:

                # Avoid obviously non-name OCR garbage.
                if not re.search(
                    r"\d",
                    name
                ):
                    return name.upper()

    # --------------------------------------------------------
    # Fallback: "This is to certify that" and the name are
    # separate OCR boxes (common — the blank is often a
    # differently-styled run of text, so PaddleOCR splits it
    # from the printed label even on the same line).
    # --------------------------------------------------------

    value = extract_labeled_value(
        items,
        r"CERTIFY\s+THAT",
        max_y_distance=25,
    )

    if value:

        name = clean_text(value)

        if (
            2 <= len(name) <= 80
            and not re.search(r"\d", name)
            and not re.search(
                r"\b(?:ROLL|MOTHER|FATHER|DATE|SCHOOL|REGN)\b",
                name,
                re.I
            )
        ):
            return name.upper()

    return None


# ============================================================
# MOTHER NAME
# ============================================================

def extract_mother_name(items):

    # --------------------------------------------------------
    # CASE 1:
    # Mother's Name RENUKA THAKUR
    # --------------------------------------------------------

    for item in items:

        match = re.search(
            r"MOTHER'?S\s+N(?:AME|ANE)\s+(.+)",
            item["text"],
            re.I
        )

        if match:

            value = clean_text(
                match.group(1)
            )

            if value:

                # Stop if another field somehow follows.
                value = re.split(
                    r"\b(?:FATHER|DATE|SCHOOL|ROLL)\b",
                    value,
                    flags=re.I
                )[0]

                value = clean_text(value)

                if value:
                    return value.upper()

    # --------------------------------------------------------
    # CASE 2:
    # Mother's Name
    # RENUKA THAKUR
    # --------------------------------------------------------

    value = extract_labeled_value(
        items,
        r"MOTHER'?S\s+N(?:AME|ANE)"
    )

    if value:
        return clean_text(value).upper()

    return None


# ============================================================
# FATHER NAME
# ============================================================

def extract_father_name(items):

    # --------------------------------------------------------
    # CASE 1:
    #
    # Father's/Guardian's Name SANJEEV KUMAR
    # --------------------------------------------------------

    for item in items:

        text = clean_text(
            item["text"]
        )

        match = re.search(
            r"FATHER'?S\s*/?\s*GUARDIAN'?S\s+NAME\s+(.+)",
            text,
            re.I
        )

        if match:

            value = clean_text(
                match.group(1)
            )

            value = re.split(
                r"\b(?:DATE|SCHOOL|ROLL|MOTHER)\b",
                value,
                flags=re.I
            )[0]

            value = clean_text(value)

            if value:
                return value.upper()

    # --------------------------------------------------------
    # CASE 2:
    #
    # Father's/Guardian's Name
    # SANJEEV KUMAR
    #
    # Coordinate-aware extraction.
    # --------------------------------------------------------

    value = extract_labeled_value(
        items,
        r"FATHER'?S\s*/?\s*GUARDIAN'?S\s+NAME",
        max_y_distance=35
    )

    if value:

        value = clean_text(value)

        # Don't accept another field as father's name.
        if not re.search(
            r"\b(?:DATE|SCHOOL|MOTHER|ROLL|REGN)\b",
            value,
            re.I
        ):
            return value.upper()

    # --------------------------------------------------------
    # CASE 3:
    #
    # OCR may split:
    #
    # Father's/Guardian's Name
    # fa
    # SANJEEV KUMAR
    #
    # Find the nearest useful text on the same
    # approximate horizontal region.
    # --------------------------------------------------------

    father_labels = []

    label_regex = re.compile(
        r"FATHER'?S\s*/?\s*GUARDIAN'?S\s+NAME",
        re.I
    )

    for item in items:

        if label_regex.search(item["text"]):

            father_labels.append(item)

    for label in father_labels:

        candidates = []

        for item in items:

            if item is label:
                continue

            # Father name in this CBSE layout appears
            # immediately to the right of the label.
            if item["cx"] <= label["x2"]:
                continue

            y_distance = abs(
                item["cy"] - label["cy"]
            )

            if y_distance > 45:
                continue

            candidate = clean_text(
                item["text"]
            )

            # Reject obvious labels / unrelated data.
            if re.search(
                r"\b(?:DATE|BIRTH|SCHOOL|MOTHER|ROLL|REGN|CODE)\b",
                candidate,
                re.I
            ):
                continue

            if re.fullmatch(
                r"[A-Z]{1,3}",
                candidate,
                re.I
            ):
                continue

            if len(candidate) < 2:
                continue

            candidates.append(
                (
                    y_distance,
                    abs(item["cx"] - label["x2"]),
                    item
                )
            )

        candidates.sort(
            key=lambda x: (x[0], x[1])
        )

        if candidates:

            value = candidates[0][2]["text"]

            return clean_text(
                value
            ).upper()

    return None


# ============================================================
# SCHOOL NAME
# ============================================================

def extract_school_name(items):

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Do not search for any random capitalized text.
    #
    # First find the actual SCHOOL label.
    #
    # NOTE: exam titles vary by class/year — "SECONDARY SCHOOL
    # EXAMINATION" (Class 10) vs "SENIOR SCHOOL CERTIFICATE
    # EXAMINATION" (Class 12) vs whatever future wording CBSE
    # uses. Rather than chase every wording variant, we reject
    # any "SCHOOL"-containing line that's too long to be the
    # actual field label — a real "School" label is a short
    # word, not a title/sentence.
    # --------------------------------------------------------

    school_labels = []

    school_regex = re.compile(
        r"\bSCHOOL\b",
        re.I
    )

    for item in items:

        text = clean_text(
            item["text"]
        )

        if not school_regex.search(text):
            continue

        # Reject title/sentence-length matches (exam titles,
        # board name, etc.) — keeps this robust across
        # certificate versions without hardcoding every title.
        if len(text) > 15:
            continue

        school_labels.append(item)

    # --------------------------------------------------------
    # CASE 1:
    #
    # School
    # 43138-LORETO CONVENT...
    # --------------------------------------------------------

    for label in school_labels:

        candidates = []

        for item in items:

            if item is label:
                continue

            # School value should normally be to the right.
            if item["cx"] <= label["x2"]:
                continue

            y_distance = abs(
                item["cy"] - label["cy"]
            )

            # School value may be slightly above/below
            # the label due to OCR geometry.
            if y_distance > 45:
                continue

            value = clean_text(
                item["text"]
            )

            if not value:
                continue

            # Reject document-level phrases.
            if re.search(
                r"SECONDARY\s+SCHOOL\s+EXAMINATION"
                r"|SENIOR\s+SCHOOL\s+CERTIFICATE\s+EXAMINATION",
                value,
                re.I
            ):
                continue

            if re.search(
                r"CENTRAL\s+BOARD\s+OF\s+SECONDARY\s+EDUCATION",
                value,
                re.I
            ):
                continue

            # A school name should not be just a year or a date.
            if re.fullmatch(
                r"\d{4}",
                value
            ):
                continue

            if re.fullmatch(
                r"\d{1,2}[/-]\d{1,2}[/-]\d{4}",
                value
            ):
                continue

            if len(value) < 3:
                continue

            candidates.append(
                (
                    y_distance,
                    abs(item["cx"] - label["x2"]),
                    item
                )
            )

        candidates.sort(
            key=lambda x: (x[0], x[1])
        )

        if candidates:

            value = candidates[0][2]["text"]

            return clean_text(
                value
            ).upper()

    # --------------------------------------------------------
    # CASE 2:
    #
    # OCR may combine:
    #
    # School 43138-LORETO CONVENT...
    #
    # --------------------------------------------------------

    for item in items:

        text = clean_text(
            item["text"]
        )

        match = re.search(
            r"\bSCHOOL\b\s+(.+)",
            text,
            re.I
        )

        if not match:
            continue

        value = clean_text(
            match.group(1)
        )

        if re.search(
            r"SECONDARY\s+SCHOOL\s+EXAMINATION"
            r"|SENIOR\s+SCHOOL\s+CERTIFICATE\s+EXAMINATION",
            value,
            re.I
        ):
            continue

        if len(value) >= 3:

            return value.upper()

    return None


# ============================================================
# SUBJECT DEFINITIONS
#
# NOTE: this is only used as a display-name fallback now (see
# extract_marks below). It is NOT used to decide whether a row
# counts as a subject — that used to silently drop every
# Class 12 subject, since Class 12 codes (301 English Core,
# 037 Psychology, 042 Physics, 044 Biology, 500/502/503...)
# aren't in this Class-10-oriented list. Keep adding codes
# here over time, but don't rely on it for gating.
# ============================================================

CBSE_SUBJECTS = {
    "184": "ENGLISH LNG & LIT.",
    "085": "HINDI COURSE-B",
    "041": "MATHEMATICS STANDARD",
    "086": "SCIENCE",
    "087": "SOCIAL SCIENCE",
    "015": "KANNADA",
    "002": "HINDI COURSE-A",
    "043": "SANSKRIT",
    "016": "ARABIC",
    "122": "COMMERCIAL ART",
    "165": "COMPUTER APPLICATIONS",
    "402": "INFORMATION TECHNOLOGY",
    "417": "ARTIFICIAL INTELLIGENCE",
    "301": "ENGLISH CORE",
    "037": "PSYCHOLOGY",
    "042": "PHYSICS",
    "044": "BIOLOGY",
    "500": "WORK EXPERIENCE",
    "502": "HEALTH & PHYSICAL EDUCATION",
    "503": "GENERAL STUDIES",
}


# ============================================================
# INTEGER HELPERS
# ============================================================

def number_from_text(text):

    match = re.search(
        r"\b(\d{1,3})\b",
        text
    )

    if match:
        return int(match.group(1))

    return None


def get_items_near_y(items, y, tolerance=14):

    result = []

    for item in items:

        if abs(item["cy"] - y) <= tolerance:
            result.append(item)

    return result


# ============================================================
# MARKS EXTRACTION
# ============================================================

def extract_marks(items):
    """
    Extract CBSE marks using the actual PaddleOCR coordinates.

    CBSE layout:

        CODE
        SUBJECT
                         THEORY   IA/PR   TOTAL   WORDS   GRADE

    For the documents tested, the columns are approximately:

        THEORY       x = 408-434
        IA/PR        x = 463-488
        TOTAL        x = 511-537
        GRADE        x = 685-707

    We therefore map values by their X position instead of
    simply taking the first three numbers found on a row.

    A row is treated as a real subject row when we find an
    actual subject-name text next to the code (from OCR) OR
    the code is a known CBSE_SUBJECTS key. Previously this
    required the code to be a CBSE_SUBJECTS key regardless of
    what was actually printed next to it, which silently
    dropped every subject whose code wasn't in that (Class-10
    oriented) dict — e.g. an entire Class 12 marksheet.
    """

    # --------------------------------------------------------
    # Find subject-code candidates: any bare 3-digit OCR item.
    # --------------------------------------------------------

    subject_items = []

    for item in items:

        text = item["text"].strip()

        if not re.fullmatch(
            r"\d{3}",
            text
        ):
            continue

        subject_items.append(item)

    results = []

    used_codes = set()

    # --------------------------------------------------------
    # Process each subject
    # --------------------------------------------------------

    for code_item in subject_items:

        code = code_item["text"].strip()

        if code in used_codes:
            continue

        row_y = code_item["cy"]

        # ----------------------------------------------------
        # Get items belonging to this row
        # ----------------------------------------------------

        row_items = []

        for item in items:

            if abs(item["cy"] - row_y) <= 13:

                row_items.append(item)

        # ----------------------------------------------------
        # SUBJECT
        # ----------------------------------------------------

        subject = None

        subject_candidates = []

        for item in row_items:

            if item is code_item:
                continue

            text = item["text"].strip()

            # Subject is between code and marks.
            if (
                item["x1"] > code_item["x2"]
                and item["x1"] < 330
            ):

                if not re.fullmatch(
                    r"\d+",
                    text
                ):

                    subject_candidates.append(
                        item
                    )

        if subject_candidates:

            subject_candidates.sort(
                key=lambda x: abs(
                    x["cy"] - row_y
                )
            )

            subject = subject_candidates[0][
                "text"
            ]

        if not subject:

            subject = CBSE_SUBJECTS.get(
                code
            )

        # ----------------------------------------------------
        # Guard against false positives: a bare 3-digit number
        # elsewhere on the page (page numbers, unrelated codes,
        # noise) should not become a fake subject row unless we
        # actually found or know a subject name for it.
        # ----------------------------------------------------

        if not subject:
            continue

        # ----------------------------------------------------
        # NUMERIC COLUMN EXTRACTION
        # ----------------------------------------------------

        theory = None
        internal = None
        total = None

        for item in row_items:

            text = item["text"].strip()

            if not re.fullmatch(
                r"\d{2,3}",
                text
            ):
                continue

            value = int(text)

            # Ignore impossible marks.
            if value > 100:
                continue

            # Ignore subject code.
            if value == int(code):
                continue

            x = item["cx"]

            # ------------------------------------------------
            # THEORY
            # ------------------------------------------------
            #
            # Actual PaddleOCR coordinates:
            # ~420
            #
            if 395 <= x < 450:

                if theory is None:
                    theory = value

            # ------------------------------------------------
            # INTERNAL / PRACTICAL
            # ------------------------------------------------
            #
            # Actual coordinates:
            # ~475
            #
            elif 450 <= x < 500:

                if internal is None:
                    internal = value

            # ------------------------------------------------
            # TOTAL
            # ------------------------------------------------
            #
            # Actual coordinates:
            # ~525
            #
            elif 500 <= x < 555:

                if total is None:
                    total = value

        # ----------------------------------------------------
        # GRADE
        # ----------------------------------------------------

        grade = None

        for item in row_items:

            text = item["text"].strip().upper()

            if re.fullmatch(
                r"A1|A2|B1|B2|C1|C2|D|E1|E2",
                text
            ):

                if item["cx"] >= 620:

                    grade = text
                    break

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        # If all three values are present, verify:
        #
        # theory + internal == total
        #
        # This is important for document verification.
        if (
            theory is not None
            and internal is not None
            and total is not None
        ):

            expected = (
                theory +
                internal
            )

            if expected != total:

                # Do NOT silently modify the OCR result.
                #
                # Leave the extracted values intact.
                # Validation can flag this later.
                pass

        # ----------------------------------------------------
        # Only create a marks row if actual marks exist.
        #
        # NOTE: grade-only subjects (e.g. Work Experience,
        # Health & Physical Education, General Studies) print
        # no theory/internal/total numbers at all — they are
        # correctly skipped here rather than counted with a
        # phantom total.
        # ----------------------------------------------------

        if (
            theory is None
            and internal is None
            and total is None
        ):
            continue

        results.append({
            "subject_code": code,
            "subject": clean_text(subject),
            "theory": theory,
            "internal_or_practical": internal,
            "total": total,
            "grade": grade,
        })

        used_codes.add(code)

    return results
# ============================================================
# MARKS SUMMARY
# ============================================================

def calculate_summary(marks):

    valid_rows = []

    for row in marks:

        total = row.get("total")

        if isinstance(total, int):

            valid_rows.append(row)

    total_marks = sum(
        row["total"]
        for row in valid_rows
    )

    maximum_marks = len(
        valid_rows
    ) * 100

    percentage = None

    if maximum_marks:

        percentage = round(
            total_marks / maximum_marks * 100,
            2
        )

    return {
        "total_marks": total_marks,
        "maximum_marks": maximum_marks,
        "percentage": percentage,
        "subjects": len(valid_rows),
    }


# ============================================================
# RESULT
# ============================================================

def extract_result(items):

    for item in items:

        text = item["upper"]

        match = re.search(
            r"\bRESULT\s+(PASS|FAIL)\b",
            text
        )

        if match:
            return match.group(1)

        if re.fullmatch(
            r"PASS|FAIL",
            text
        ):
            return text

    return None


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_cbse(ocr_path):

    items = load_ocr(
        ocr_path
    )

    # --------------------------------------------------------
    # Student information
    # --------------------------------------------------------

    name = extract_student_name(
        items
    )

    roll_number = extract_roll_number(
        items
    )

    registration_number = extract_registration(
        items
    )

    dob = extract_dob(
        items
    )

    mother_name = extract_mother_name(
        items
    )

    father_name = extract_father_name(
        items
    )

    school_name = extract_school_name(
        items
    )

    # --------------------------------------------------------
    # Academic information
    # --------------------------------------------------------

    exam_year = extract_exam_year(
        items
    )

    result = extract_result(
        items
    )

    marks = extract_marks(
        items
    )

    summary = calculate_summary(
        marks
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    return {
        "student": {
            "name": name,
            "roll_number": roll_number,
            "registration_number": registration_number,
            "date_of_birth": dob,
            "mother_name": mother_name,
            "father_name": father_name,
        },

        "school": {
            "name": school_name,
        },

        "academic_summary": summary,

        "marks": marks,

        "exam_year": exam_year,

        "result": result,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) < 2:

        print(
            "Usage: python cbse_extractor.py <ocr_result.json>"
        )

        sys.exit(1)

    ocr_path = sys.argv[1]

    if not os.path.exists(
        ocr_path
    ):

        print(
            f"ERROR: OCR file not found: {ocr_path}"
        )

        sys.exit(1)

    output = extract_cbse(
        ocr_path
    )

    # --------------------------------------------------------
    # Output path
    # --------------------------------------------------------

    output_path = os.path.join(
        os.path.dirname(ocr_path),
        "extracted_data.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
    )

    print()
    print(
        "Output saved to:",
        output_path
    )


if __name__ == "__main__":
    main()