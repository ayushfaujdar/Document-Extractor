import json
import re
import sys
from pathlib import Path


# ============================================================
# AADHAAR EXTRACTOR
# ============================================================
#
# Extracts ONLY:
#
#   Name
#   Father's Name
#   Date of Birth
#   Gender
#   Aadhaar Number
#   Address
#
# Input:
#   Module 3 ocr_result.json
#
# Output:
#   aadhaar_extracted_data.json
#
# ============================================================


# ============================================================
# HELPERS
# ============================================================

def clean(value):
    if value is None:
        return None

    value = str(value)

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize(value):
    value = clean(value)

    if not value:
        return ""

    return value.upper()


def get_lines(ocr_result):
    """
    Preserve OCR reading order.
    """

    lines = []

    for item in ocr_result.get(
        "text",
        []
    ):

        if not isinstance(
            item,
            dict
        ):
            continue

        text = item.get(
            "text"
        )

        if not text:
            continue

        text = clean(text)

        if text:
            lines.append({
                "text": text,
                "page": item.get(
                    "page_number"
                ),
                "confidence": item.get(
                    "confidence"
                ),
                "box": item.get(
                    "box"
                )
            })

    return lines


# ============================================================
# AADHAAR NUMBER
# ============================================================

def extract_aadhaar_number(text):

   
    match = re.search(
        r"\b(\d{4})[\s\-]+(\d{4})[\s\-]+(\d{4})\b",
        text
    )

    if match:

        return (
            f"{match.group(1)} "
            f"{match.group(2)} "
            f"{match.group(3)}"
        )

    # 871136883254
    match = re.search(
        r"\b(\d{12})\b",
        text
    )

    if match:

        number = match.group(1)

        return (
            f"{number[:4]} "
            f"{number[4:8]} "
            f"{number[8:]}"
        )

    return None


# ============================================================
# DATE OF BIRTH
# ============================================================

def extract_dob(text):


    # --------------------------------------------------------
    # Normal date pattern
    #
    # IMPORTANT:
    # Do NOT use \b before the day because OCR may produce:
    #
    #     
    #
    # --------------------------------------------------------

    pattern = (
        r"(?<!\d)"
        r"(\d{1,2})"
        r"[\/\-.]"
        r"(\d{1,2})"
        r"[\/\-.]"
        r"(\d{4})"
        r"(?!\d)"
    )

    matches = re.finditer(
        pattern,
        text
    )

    for match in matches:

        day = int(
            match.group(1)
        )

        month = int(
            match.group(2)
        )

        year = int(
            match.group(3)
        )

        # Validate date components
        if not (
            1 <= day <= 31
        ):
            continue

        if not (
            1 <= month <= 12
        ):
            continue

        if not (
            1900 <= year <= 2100
        ):
            continue

        return (
            f"{day:02d}/"
            f"{month:02d}/"
            f"{year:04d}"
        )

    return None

# ============================================================
# YEAR OF BIRTH
# ============================================================

def extract_year_of_birth(text):

    match = re.search(
        r"(?:YEAR\s+OF\s+BIRTH|YOB)"
        r"\s*[:\-]?\s*"
        r"(19\d{2}|20\d{2})",
        text,
        flags=re.I
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# GENDER
# ============================================================

def extract_gender(text):

    upper = normalize(text)

    # Handles:
   

    match = re.search(
        r"\b(MALE|FEMALE|TRANSGENDER)\b",
        upper
    )

    if match:

        return match.group(1)

    # Hindi OCR

    if "पुरुष" in text:
        return "MALE"

    if "महिला" in text:
        return "FEMALE"

    return None


# ============================================================
# NAME VALIDATION
# ============================================================

def is_name(value):

    if not value:
        return False

    value = clean(value)

    if len(value) < 3:
        return False

    if len(value) > 60:
        return False

    if not re.fullmatch(
        r"[A-Za-z][A-Za-z .'\-]*",
        value
    ):
        return False

    forbidden = [

        "GOVERNMENT",

        "INDIA",

        "AADHAAR",

        "UIDAI",

        "AUTHORITY",

        "ADDRESS",

        "DATE",

        "BIRTH",

        "YEAR",

        "MALE",

        "FEMALE",

        "HELP",

    ]

    upper = normalize(
        value
    )

    for word in forbidden:

        if word in upper:
            return False

    return True


# ============================================================
# NAME
# ============================================================

def extract_name(lines):

    # --------------------------------------------------------
    # Explicit NAME label
    # --------------------------------------------------------

    for index, item in enumerate(
        lines
    ):

        line = item["text"]

        upper = normalize(
            line
        )

       
        match = re.search(
            r"\bNAME\b\s*[:\-]\s*(.+)",
            upper
        )

        if match:

            candidate = clean(
                match.group(1)
            )

            if is_name(candidate):

                return candidate

        # NAME
       
        if upper in {
            "NAME",
            "NAME OF HOLDER",
        }:

            if index + 1 < len(lines):

                candidate = clean(
                    lines[index + 1]["text"]
                )

                if is_name(candidate):

                    return candidate

    # --------------------------------------------------------
    # Specific Aadhaar sample pattern
    #
    #
    # --------------------------------------------------------

    for item in lines:

        candidate = clean(
            item["text"]
        )

        if is_name(candidate):

            return candidate

    return None


# ============================================================
# FATHER'S NAME
# ============================================================

def extract_father_name(lines):

    # --------------------------------------------------------
    # Same-line format:
    #
    # Father:PREM SHANKAR
    # --------------------------------------------------------

    for item in lines:

        line = item["text"]

        match = re.search(
            r"\bFATHER\s*[:\-]\s*(.+)",
            line,
            flags=re.I
        )

        if match:

            candidate = clean(
                match.group(1)
            )

            if is_name(candidate):

                return candidate

    # --------------------------------------------------------
    # Other common formats
    # --------------------------------------------------------

    for item in lines:

        line = item["text"]

        match = re.search(
            r"\bFATHER(?:'S)?\s+NAME\s*[:\-]\s*(.+)",
            line,
            flags=re.I
        )

        if match:

            candidate = clean(
                match.group(1)
            )

            if is_name(candidate):

                return candidate

    # --------------------------------------------------------
    # Separate lines:
    #
    # Father
    # --------------------------------------------------------

    for index, item in enumerate(
        lines
    ):

        upper = normalize(
            item["text"]
        )

        if upper in {
            "FATHER",
            "FATHER NAME",
            "FATHERS NAME",
            "FATHER'S NAME",
            "GUARDIAN",
            "GUARDIAN NAME",
        }:

            if index + 1 < len(lines):

                candidate = clean(
                    lines[index + 1]["text"]
                )

                if is_name(candidate):

                    return candidate

    return None


# ============================================================
# ADDRESS
# ============================================================

def extract_address(lines):

    """
    Aadhaar back side in this OCR:

        BAGHAI, Bajna Dehat, Mathura
        Bajna,Uttar Pradesh,281201
        Address

    Because OCR reading order can place the ADDRESS label
    after the actual address, we search for address-like
    lines rather than requiring ADDRESS to come first.
    """

    address_lines = []

    # --------------------------------------------------------
    # First find explicit ADDRESS position
    # --------------------------------------------------------

    address_index = None

    for index, item in enumerate(
        lines
    ):

        if "ADDRESS" in normalize(
            item["text"]
        ):

            address_index = index

            break

    # --------------------------------------------------------
    # Look around ADDRESS label.
    #
    # In this OCR, address text appears BEFORE the label.
    # --------------------------------------------------------

    if address_index is not None:

        start = max(
            0,
            address_index - 5
        )

        end = min(
            len(lines),
            address_index + 4
        )

        nearby = lines[
            start:end
        ]

        for item in nearby:

            text = clean(
                item["text"]
            )

            upper = normalize(
                text
            )

            if not text:
                continue

            if upper == "ADDRESS":
                continue

            if (
                "UIDAI" in upper
                or
                "HELP@" in upper
                or
                "WWW." in upper
                or
                "GOVERNMENT OF INDIA" in upper
            ):
                continue

            # Address indicators
            if looks_like_address(
                text
            ):

                address_lines.append(
                    text
                )

    # --------------------------------------------------------
    # If that didn't work, scan the whole document.
    # --------------------------------------------------------

    if not address_lines:

        for item in lines:

            text = clean(
                item["text"]
            )

            if looks_like_address(
                text
            ):

                address_lines.append(
                    text
                )

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique = []

    for line in address_lines:

        if line not in unique:

            unique.append(
                line
            )

    if not unique:
        return None

    return ", ".join(
        unique
    )


def looks_like_address(text):

    upper = normalize(
        text
    )

    # Never treat these as address
    forbidden = [

        "AADHAAR",

        "UIDAI",

        "UNIQUE IDENTIFICATION",

        "GOVERNMENT OF INDIA",

        "HELP@UIDAI",

        "WWW.UIDAI",

        "MALE",

        "FEMALE",

        "DATE OF BIRTH",

        "YEAR OF BIRTH",

        "ADDRESS",

    ]

    for word in forbidden:

        if word in upper:

            return False

    # Strong address indicators

    indicators = [

        "UTTAR PRADESH",

        "RAJASTHAN",

        "DELHI",

        "MATHURA",

        "BAJNA",

        "BIHAR",

        "HARYANA",

        "MAHARASHTRA",

        "KARNATAKA",

        "GUJARAT",

        "MADHYA PRADESH",

        "WEST BENGAL",

        "PIN",

    ]

    for word in indicators:

        if word in upper:

            return True

    # PIN code

    if re.search(
        r"\b\d{6}\b",
        text
    ):

        return True

    # Comma-separated locality
    if text.count(",") >= 1:

        return True

    return False


# ============================================================
# SIGNALS
# ============================================================

def get_signals(text):

    upper = normalize(
        text
    )

    signals = []

    if "AADHAAR" in upper:
        signals.append(
            "AADHAAR"
        )

    if "UIDAI" in upper:
        signals.append(
            "UIDAI"
        )

    if (
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA"
        in upper
    ):
        signals.append(
            "UNIQUE IDENTIFICATION AUTHORITY OF INDIA"
        )

    if "GOVERNMENT OF INDIA" in upper:
        signals.append(
            "GOVERNMENT OF INDIA"
        )

    if "ADDRESS" in upper:
        signals.append(
            "ADDRESS"
        )

    return signals


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_aadhaar(
    ocr_result
):

    lines = get_lines(
        ocr_result
    )

    raw_text = ocr_result.get(
        "raw_text",
        ""
    )

    combined_text = "\n".join(
        item["text"]
        for item in lines
    )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    name = extract_name(
        lines
    )

    father_name = extract_father_name(
        lines
    )

    dob = extract_dob(
        combined_text
    )

    year_of_birth = extract_year_of_birth(
        combined_text
    )

    gender = extract_gender(
        combined_text
    )

    aadhaar_number = extract_aadhaar_number(
        combined_text
    )

    address = extract_address(
        lines
    )

    signals = get_signals(
        combined_text
    )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = 0

    if "AADHAAR" in signals:
        confidence += 25

    if (
        "UIDAI" in signals
        or
        "UNIQUE IDENTIFICATION AUTHORITY OF INDIA"
        in signals
    ):
        confidence += 25

    if aadhaar_number:
        confidence += 20

    if name:
        confidence += 10

    if father_name:
        confidence += 5

    if gender:
        confidence += 5

    if dob or year_of_birth:
        confidence += 5

    if address:
        confidence += 5

    confidence = min(
        confidence,
        100
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {

        "success": True,

        "document_type": "AADHAAR",

        "confidence": confidence,

        "data": {

            "name": name,

            "father_name": father_name,

            "date_of_birth": dob,

            "year_of_birth": year_of_birth,

            "gender": gender,

            "aadhaar_number": aadhaar_number,

            "address": address,

        },

        "signals": signals,
    }


# ============================================================
# CLI
# ============================================================

def main():

    if len(sys.argv) != 2:

        print(
            "Usage:"
        )

        print(
            "python app/extraction/aadhaar_extractor.py "
            "<ocr_result.json>"
        )

        sys.exit(1)

    ocr_path = Path(
        sys.argv[1]
    )

    if not ocr_path.exists():

        print(
            f"ERROR: OCR file not found: {ocr_path}"
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

        result = extract_aadhaar(
            ocr_result
        )

        output_path = (
            ocr_path.parent /
            "aadhaar_extracted_data.json"
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

        print()
        print(
            f"Output saved to: {output_path}"
        )

    except Exception as error:

        print(
            f"ERROR: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()