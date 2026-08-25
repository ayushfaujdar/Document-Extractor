from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ============================================================
# CBSE DOCUMENT EXTRACTION
# ============================================================
#
# Extracts identity/details from OCR output.
#
# This module extracts:
#   - Student name
#   - Roll number
#   - Registration number
#   - Date of birth
#   - Mother's name
#   - Father's / Guardian's name
#   - School name
#
# Marks are handled separately by marks_parser.py.
#
# Expected OCR JSON:
# {
#     "raw_text": "...",
#     "text": [
#         {
#             "text": "...",
#             "box": [...],
#             "confidence": ...
#         }
#     ]
# }
#
# Output:
# {
#     "student": {
#         "name": ...,
#         "roll_number": ...,
#         "registration_number": ...,
#         "date_of_birth": ...,
#         "mother_name": ...,
#         "father_name": ...
#     },
#     "school": {
#         "name": ...
#     }
# }
# ============================================================


# ============================================================
# REGEX PATTERNS
# ============================================================

DATE_PATTERN = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b"
)

ROLL_PATTERN = re.compile(
    r"\b\d{7,10}\b"
)

REG_PATTERN = re.compile(
    r"\b[A-Z]\d{2,4}/\d{4,7}/\d{3,5}\b",
    re.IGNORECASE,
)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    if value is None:
        return ""

    value = str(value)

    value = value.replace("\n", " ")

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def clean_name(value: str | None) -> str | None:
    value = clean_text(value)

    if not value:
        return None

    # Remove OCR punctuation/noise around names.
    value = re.sub(
        r"^[^A-Za-z]+",
        "",
        value,
    )

    value = re.sub(
        r"[^A-Za-z .'-]+$",
        "",
        value,
    )

    value = clean_text(value)

    if not value:
        return None

    return value.upper()


def clean_school(value: str | None) -> str | None:
    value = clean_text(value)

    if not value:
        return None

    # Remove OCR versions of "School" label.
    value = re.sub(
        r"^(?:SCHOOL|SCHOO|SCHOOI|SCH0OL)"
        r"\s*(?:NAME)?\s*[:\-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Remove common certification text accidentally
    # captured before the actual school name.
    value = re.sub(
        r"^(?:EXAMINATION\s*,?\s*\d{4}\s*)?"
        r"(?:THIS\s+IS\s+TO\s+CERTIFY\s+THAT\s+)?",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = clean_text(value)

    if not value:
        return None

    return value.upper()


def get_center(item):
    box = item.get("box") or []

    if not box:
        return 0.0, 0.0

    xs = [
        point[0]
        for point in box
    ]

    ys = [
        point[1]
        for point in box
    ]

    return (
        sum(xs) / len(xs),
        sum(ys) / len(ys),
    )


def prepare_items(ocr_result):
    items = []

    for item in ocr_result.get("text", []):

        text = clean_text(
            item.get("text")
        )

        if not text:
            continue

        x, y = get_center(item)

        items.append({
            "text": text,
            "x": x,
            "y": y,
            "confidence": float(
                item.get(
                    "confidence",
                    0,
                )
            ),
        })

    return items


# ============================================================
# LINE RECONSTRUCTION
# ============================================================

def build_lines(
    items,
    y_tolerance=12,
):
    """
    Reconstruct OCR objects into visual lines.

    OCR frequently splits a field into multiple objects.

    Example:

        Mother's Name
        MANJULA

    or:

        Date 0fBirth
        31/05/2005

    This function groups objects by their vertical position.
    """

    if not items:
        return []

    sorted_items = sorted(
        items,
        key=lambda item: (
            item["y"],
            item["x"],
        ),
    )

    lines = []

    for item in sorted_items:

        target = None

        for line in reversed(lines):

            if abs(
                line["y"] - item["y"]
            ) <= y_tolerance:

                target = line
                break

            if (
                item["y"] - line["y"]
                > y_tolerance
            ):
                break

        if target is None:

            lines.append({
                "y": item["y"],
                "items": [item],
            })

        else:

            target["items"].append(
                item
            )

            target["y"] = (
                sum(
                    x["y"]
                    for x in target["items"]
                )
                /
                len(target["items"])
            )

    result = []

    for line in lines:

        line["items"].sort(
            key=lambda item: item["x"]
        )

        line["text"] = clean_text(
            " ".join(
                item["text"]
                for item in line["items"]
            )
        )

        result.append(line)

    result.sort(
        key=lambda line: line["y"]
    )

    return result


# ============================================================
# REGISTRATION NUMBER
# ============================================================

def extract_registration_number(
    raw_text,
):
    if not raw_text:
        return None

    match = REG_PATTERN.search(
        raw_text.upper()
    )

    if match:
        return match.group(0).upper()

    # More tolerant fallback.
    match = re.search(
        r"\b[A-Z]\d{2,4}"
        r"\s*/\s*"
        r"\d{4,7}"
        r"\s*/\s*"
        r"\d{3,5}\b",
        raw_text,
        re.IGNORECASE,
    )

    if match:

        return re.sub(
            r"\s+",
            "",
            match.group(0).upper(),
        )

    return None


# ============================================================
# ROLL NUMBER
# ============================================================

def extract_roll_number(
    raw_text,
):
    if not raw_text:
        return None

    patterns = [

        r"Roll\s*No\.?\s*[:\-]?\s*"
        r"(\d{7,10})",

        r"RollNo\.?\s*[:\-]?\s*"
        r"(\d{7,10})",

        r"Roll\s*Number\s*[:\-]?\s*"
        r"(\d{7,10})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            raw_text,
            re.IGNORECASE,
        )

        if match:

            return match.group(1)

    return None


# ============================================================
# DATE OF BIRTH
# ============================================================

def extract_date_of_birth(
    raw_text,
    lines,
):
    """
    Extract DOB specifically from the Date of Birth field.

    Handles OCR variations such as:

        Date of Birth 31/05/2005
        Date 0f Birth 31/05/2005
        Date 0fBirth 31/05/2005
        Date OfBirth 31-05-2005
        DateofBirth 31/05/2005

    IMPORTANT:
    We never simply take the first date in the document because
    CBSE documents contain other dates such as examination dates.
    """

    # --------------------------------------------------------
    # Flexible DOB label
    # --------------------------------------------------------

    dob_label = (
        r"Date\s*"
        r"(?:0|o)?f\s*"
        r"(?:Birth|B1rth)"
    )

    # --------------------------------------------------------
    # 1. Search reconstructed visual lines.
    # --------------------------------------------------------

    for index, line in enumerate(lines):

        text = line["text"]

        if re.search(
            dob_label,
            text,
            re.IGNORECASE,
        ):

            # Date on the same line.
            match = DATE_PATTERN.search(
                text
            )

            if match:

                return match.group(
                    0
                ).replace(
                    "-",
                    "/",
                )

            # Date may be on the next visual line.
            for next_index in range(
                index + 1,
                min(
                    index + 3,
                    len(lines),
                ),
            ):

                next_text = lines[
                    next_index
                ]["text"]

                match = DATE_PATTERN.search(
                    next_text
                )

                if match:

                    return match.group(
                        0
                    ).replace(
                        "-",
                        "/",
                    )

    # --------------------------------------------------------
    # 2. Search raw OCR text.
    #
    # This handles:
    #
    # Date 0fBirth 31/05/2005
    #
    # which is present in the current OCR.
    # --------------------------------------------------------

    if raw_text:

        patterns = [

            rf"{dob_label}"
            rf".{{0,120}}?"
            rf"(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}})",

            r"Date\s*"
            r".{0,20}?"
            r"Birth"
            r".{0,120}?"
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                raw_text,
                re.IGNORECASE,
            )

            if match:

                return match.group(
                    1
                ).replace(
                    "-",
                    "/",
                )

    # --------------------------------------------------------
    # 3. Spatial fallback.
    #
    # Find the OCR object containing "Date...Birth",
    # then find the closest date around it.
    # --------------------------------------------------------

    dob_labels = []

    for line in lines:

        for item in line["items"]:

            if re.search(
                dob_label,
                item["text"],
                re.IGNORECASE,
            ):

                dob_labels.append(
                    item
                )

    if dob_labels:

        label = dob_labels[0]

        candidates = []

        for line in lines:

            for item in line["items"]:

                match = DATE_PATTERN.search(
                    item["text"]
                )

                if not match:
                    continue

                vertical_distance = abs(
                    item["y"] -
                    label["y"]
                )

                horizontal_distance = abs(
                    item["x"] -
                    label["x"]
                )

                # DOB should be physically close
                # to its label.
                if (
                    vertical_distance <= 100
                    and horizontal_distance <= 700
                ):

                    candidates.append(
                        (
                            vertical_distance
                            + (
                                horizontal_distance
                                * 0.05
                            ),
                            match.group(0),
                        )
                    )

        if candidates:

            candidates.sort(
                key=lambda item: item[0]
            )

            return candidates[0][1].replace(
                "-",
                "/",
            )

    return None


# ============================================================
# STUDENT NAME
# ============================================================

def extract_name(
    raw_text,
    lines,
):
    """
    Extract student name after:

        This is to certify that

    Handles both:

        This is to certify that KHUsHI GULI

    and:

        This is to certify that
        KHUsHI GULI
    """

    # --------------------------------------------------------
    # Reconstructed visual lines
    # --------------------------------------------------------

    for index, line in enumerate(lines):

        text = line["text"]

        match = re.search(
            r"This\s+is\s+to\s+certify\s+that\s+"
            r"(.+?)"
            r"(?=\s+Roll\s*No\.?|\s+RollNo|$)",
            text,
            re.IGNORECASE,
        )

        if match:

            name = clean_name(
                match.group(1)
            )

            if name:
                return name

        if re.search(
            r"This\s+is\s+to\s+certify\s+that",
            text,
            re.IGNORECASE,
        ):

            if index + 1 < len(lines):

                candidate = lines[
                    index + 1
                ]["text"]

                if (
                    candidate
                    and not re.search(
                        r"Roll\s*No"
                        r"|Mother"
                        r"|Father"
                        r"|Date",
                        candidate,
                        re.IGNORECASE,
                    )
                ):

                    name = clean_name(
                        candidate
                    )

                    if name:
                        return name

    # --------------------------------------------------------
    # Raw OCR fallback
    # --------------------------------------------------------

    if raw_text:

        match = re.search(
            r"This\s+is\s+to\s+certify\s+that\s+"
            r"(.+?)"
            r"(?=\s+Roll\s*No\.?|\s+RollNo)",
            raw_text,
            re.IGNORECASE,
        )

        if match:

            name = clean_name(
                match.group(1)
            )

            if name:
                return name

    return None


# ============================================================
# GENERIC LABELED FIELD
# ============================================================

def extract_labeled_value(
    raw_text,
    label_pattern,
    stop_patterns,
):
    """
    Extract a value following a field label.

    Example:

        Mother's Name MANJULA
        Father's/Guardian's Name RAVI
    """

    if not raw_text:
        return None

    stop = "|".join(
        f"(?:{pattern})"
        for pattern in stop_patterns
    )

    pattern = (
        rf"{label_pattern}"
        rf"\s*[:\-]?\s*"
        rf"(.+?)"
        rf"(?=\s+(?:{stop})|$)"
    )

    match = re.search(
        pattern,
        raw_text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return clean_text(
        match.group(1)
    )


# ============================================================
# MOTHER NAME
# ============================================================

def extract_mother_name(
    raw_text,
    lines,
):
    """
    Extract mother's name without consuming DOB,
    father name or school information.
    """

    value = extract_labeled_value(
        raw_text,
        r"Mother['’]s\s+Name",
        [
            r"Father(?:['’]s)?"
            r"\s*/?\s*Guardian['’]s?\s+Name",

            r"Father['’]s?\s+Name",

            r"Date\s*0?f\s*Birth",

            r"School",
            r"SchOO",
        ],
    )

    if value:

        value = re.sub(
            r"^[^A-Za-z]+",
            "",
            value,
        )

        return clean_name(
            value
        )

    # Visual fallback.
    for index, line in enumerate(lines):

        if re.search(
            r"Mother['’]s\s+Name",
            line["text"],
            re.IGNORECASE,
        ):

            match = re.search(
                r"Mother['’]s\s+Name\s+(.+)$",
                line["text"],
                re.IGNORECASE,
            )

            if match:

                value = clean_name(
                    match.group(1)
                )

                if value:
                    return value

            if index + 1 < len(lines):

                value = clean_name(
                    lines[index + 1]["text"]
                )

                if value:

                    return value

    return None


# ============================================================
# FATHER NAME
# ============================================================

def extract_father_name(
    raw_text,
    lines,
):
    value = extract_labeled_value(
        raw_text,

        r"Father['’]s\s*/?\s*"
        r"(?:Guardian['’]s\s+)?Name",

        [
            r"Date\s*0?f\s*Birth",
            r"School",
            r"SchOO",
        ],
    )

    if value:

        value = re.sub(
            r"^[^A-Za-z]+",
            "",
            value,
        )

        return clean_name(
            value
        )

    # Alternative OCR label.
    value = extract_labeled_value(
        raw_text,

        r"Father['’]s\s*/\s*"
        r"Guardian['’]s\s+Name",

        [
            r"Date\s*0?f\s*Birth",
            r"School",
            r"SchOO",
        ],
    )

    if value:

        return clean_name(
            value
        )

    # Visual fallback.
    for index, line in enumerate(lines):

        if re.search(
            r"Father|Guardian",
            line["text"],
            re.IGNORECASE,
        ):

            match = re.search(
                r"(?:Father|Guardian)"
                r".*?Name\s+(.+)$",
                line["text"],
                re.IGNORECASE,
            )

            if match:

                value = clean_name(
                    match.group(1)
                )

                if value:
                    return value

            if index + 1 < len(lines):

                value = clean_name(
                    lines[index + 1]["text"]
                )

                if value:

                    return value

    return None


# ============================================================
# SCHOOL NAME
# ============================================================

def extract_school(
    raw_text,
    lines,
):
    """
    Extract ONLY the actual school name.

    CBSE OCR frequently produces:

        School 43138-LORETO CONVENT TARA HALL
        UPPER KAITHU SHIMLA HP
        has achieved Scholastic Achievements...

    or:

        SchOO 45259-B S CENTRAL SCHOOL
        MUDDEBIHALLI BIJAPURDIST KK
        ...

    The old implementation could accidentally return a large
    certification sentence. This implementation first looks for
    the school-to-"has achieved" region and then cleans it.
    """

    # --------------------------------------------------------
    # OCR label variants.
    # --------------------------------------------------------

    school_label = (
        r"(?:School|SchOO|SCHOOI|Sch0ol)"
    )

    # --------------------------------------------------------
    # 1. Best method:
    #
    # Find SCHOOL and stop before "has achieved".
    # --------------------------------------------------------

    if raw_text:

        pattern = (
            rf"\b{school_label}\b"
            rf"(?:\s+Name)?"
            rf"\s*[:\-]?\s*"
            rf"(.+?)"
            rf"(?=\s+has\s+achieved\b)"
        )

        matches = list(
            re.finditer(
                pattern,
                raw_text,
                re.IGNORECASE,
            )
        )

        if matches:

            # Usually the last match is the actual
            # school field rather than a heading.
            match = matches[-1]

            value = match.group(1)

            value = clean_school(
                value
            )

            if value:

                # Remove accidental certification
                # sentence if OCR merged it before school.
                value = re.sub(
                    r"^.*?"
                    r"(?:Date\s*0?f\s*Birth"
                    r".*?)?"
                    r"(?:\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b)"
                    r"\s*",
                    "",
                    value,
                    count=1,
                    flags=re.IGNORECASE,
                )

                # If OCR still includes the student
                # certification sentence, start from a
                # school-code-looking token.
                school_code_match = re.search(
                    r"\b\d{4,6}-[A-Z]",
                    value,
                    re.IGNORECASE,
                )

                if school_code_match:

                    value = value[
                        school_code_match.start():
                    ]

                value = clean_school(
                    value
                )

                if value:
                    return value

    # --------------------------------------------------------
    # 2. Visual-line method.
    # --------------------------------------------------------

    for index, line in enumerate(lines):

        text = line["text"]

        if not re.search(
            school_label,
            text,
            re.IGNORECASE,
        ):

            continue

        # Text after School / School Name.
        match = re.search(
            rf"\b{school_label}\b"
            rf"(?:\s+Name)?"
            rf"\s*[:\-]?\s*(.+)$",
            text,
            re.IGNORECASE,
        )

        if match:

            value = match.group(1)

            # Stop if "has achieved" is present.
            value = re.split(
                r"\s+has\s+achieved\b",
                value,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]

            value = clean_school(
                value
            )

            if value:

                school_code_match = re.search(
                    r"\b\d{4,6}-[A-Z]",
                    value,
                    re.IGNORECASE,
                )

                if school_code_match:

                    value = value[
                        school_code_match.start():
                    ]

                value = clean_school(
                    value
                )

                if value:
                    return value

        # School name may be on next visual line.
        if index + 1 < len(lines):

            candidate = lines[
                index + 1
            ]["text"]

            candidate = re.split(
                r"\s+has\s+achieved\b",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]

            value = clean_school(
                candidate
            )

            if value:

                school_code_match = re.search(
                    r"\b\d{4,6}-[A-Z]",
                    value,
                    re.IGNORECASE,
                )

                if school_code_match:

                    value = value[
                        school_code_match.start():
                    ]

                value = clean_school(
                    value
                )

                if value:
                    return value

    return None


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_cbse_data(
    ocr_result,
):
    raw_text = clean_text(
        ocr_result.get(
            "raw_text",
            "",
        )
    )

    items = prepare_items(
        ocr_result
    )

    lines = build_lines(
        items
    )

    name = extract_name(
        raw_text,
        lines,
    )

    roll_number = extract_roll_number(
        raw_text
    )

    registration_number = (
        extract_registration_number(
            raw_text
        )
    )

    date_of_birth = (
        extract_date_of_birth(
            raw_text,
            lines,
        )
    )

    mother_name = (
        extract_mother_name(
            raw_text,
            lines,
        )
    )

    father_name = (
        extract_father_name(
            raw_text,
            lines,
        )
    )

    school_name = (
        extract_school(
            raw_text,
            lines,
        )
    )

    return {
        "student": {
            "name": name,
            "roll_number": roll_number,
            "registration_number":
                registration_number,
            "date_of_birth":
                date_of_birth,
            "mother_name":
                mother_name,
            "father_name":
                father_name,
        },

        "school": {
            "name": school_name,
        },
    }


# ============================================================
# COMMAND LINE
# ============================================================

def main():

    if len(sys.argv) != 2:

        print(
            "Usage: "
            "python app/extraction/"
            "cbse_extractor.py <ocr_json>"
        )

        sys.exit(1)

    input_file = Path(
        sys.argv[1]
    )

    if not input_file.exists():

        print(
            f"ERROR: File not found: "
            f"{input_file}"
        )

        sys.exit(1)

    try:

        with input_file.open(
            "r",
            encoding="utf-8",
        ) as file:

            ocr_result = json.load(
                file
            )

        result = extract_cbse_data(
            ocr_result
        )

        output_file = (
            input_file.parent /
            "extracted_data.json"
        )

        with output_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                result,
                file,
                indent=2,
                ensure_ascii=False,
            )

        result["output_file"] = str(
            output_file
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

    except Exception as error:

        print(
            f"ERROR: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()