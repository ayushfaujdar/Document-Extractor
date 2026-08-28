import os
import re
import json
import sys
import cv2
import numpy as np
import pymupdf

from app.ocr.module3_ocr import extract_text_from_array


# ============================================================
# LOAD DOCUMENT
# ============================================================

def load_document(file_path):

    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":

        doc = pymupdf.open(file_path)

        if len(doc) == 0:
            raise ValueError("PDF contains no pages.")

        page = doc[0]

        # High resolution rendering
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(3, 3),
            alpha=False
        )

        img = np.frombuffer(
            pix.samples,
            dtype=np.uint8
        )

        img = img.reshape(
            pix.height,
            pix.width,
            3
        )

        return cv2.cvtColor(
            img,
            cv2.COLOR_RGB2BGR
        )

    image = cv2.imread(file_path)

    if image is None:
        raise ValueError(
            f"Could not read image: {file_path}"
        )

    return image


# ============================================================
# IMAGE QUALITY
# ============================================================

def check_image_quality(image):

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    blur_score = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    brightness = float(np.mean(gray))

    height, width = image.shape[:2]

    return {
        "width": width,
        "height": height,
        "blur_score": round(blur_score, 2),
        "brightness": round(brightness, 2),
        "resolution_ok": (
            width >= 1200 and
            height >= 800
        ),
        "likely_blurry": blur_score < 80,
        "likely_dark": brightness < 50,
        "likely_overexposed": brightness > 235
    }


# ============================================================
# OCR
# ============================================================

def run_ocr(image):
    """Use the shared PaddleOCR 3.x/ONNX adapter for this legacy CLI."""

    return extract_text_from_array(image, "marksheet_extractor")["text"]


# ============================================================
# TEXT
# ============================================================

def get_full_text(lines):

    return "\n".join(
        item["text"]
        for item in lines
        if item["text"]
    )


# ============================================================
# VALUE FINDER
# ============================================================

def find_value(text, patterns):

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1).strip()

    return None


# ============================================================
# NAME
# ============================================================

def extract_name(text):

    patterns = [

        r"(?:student'?s?\s+name|candidate'?s?\s+name)"
        r"\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{2,60})",

        r"\bname\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{2,60})"
    ]

    return find_value(
        text,
        patterns
    )


# ============================================================
# DATE OF BIRTH
# ============================================================

def extract_dob(text):

    patterns = [

        r"(?:date\s+of\s+birth|dob|birth\s+date)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})",

        r"(?:date\s+of\s+birth|dob)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
    ]

    return find_value(
        text,
        patterns
    )


# ============================================================
# ROLL NUMBER
# ============================================================

def extract_roll_number(text):

    patterns = [

        r"(?:roll\s*(?:no|number))"
        r"\s*[:\-]?\s*"
        r"([A-Za-z0-9\/\-]{4,30})",

        r"(?:registration\s*(?:no|number))"
        r"\s*[:\-]?\s*"
        r"([A-Za-z0-9\/\-]{4,30})"
    ]

    return find_value(
        text,
        patterns
    )


# ============================================================
# BOARD
# ============================================================

def detect_board(text):

    t = text.lower()
    compact = re.sub(
        r"[^a-z]",
        "",
        t,
    )

    if (
        "centralboardofsecondaryeducation"
        in compact
    ):
        return "CBSE"

    if "cbse" in compact:
        return "CBSE"

    if (
        "madhyamikshikshaparishad"
        in compact
    ):
        return "UP Board"

    if (
        "uttarpradesh" in compact
        and "board" in compact
    ):
        return "UP Board"

    if "icse" in compact:
        return "ICSE"

    if "cisce" in compact:
        return "CISCE"

    return "Unknown"


# ============================================================
# YEAR
# ============================================================

def extract_years(text):

    years = re.findall(
        r"\b20\d{2}\b",
        text
    )

    return list(dict.fromkeys(years))


# ============================================================
# SUBJECT MARKS
# ============================================================

SUBJECTS = [

    "English",
    "Hindi",
    "Mathematics",
    "Math",
    "Science",
    "Social Science",
    "Social Studies",
    "Physics",
    "Chemistry",
    "Biology",
    "Computer",
    "Information Technology",
    "Sanskrit",
    "Punjabi",
    "Urdu"
]


def extract_subject_marks(lines):

    results = []

    for line in lines:

        text = line["text"]

        lower = text.lower()

        subject_found = None

        for subject in SUBJECTS:

            if subject.lower() in lower:

                subject_found = subject

                break

        if not subject_found:
            continue

        numbers = re.findall(
            r"\b(?:100|[0-9]{1,2})\b",
            text
        )

        valid_marks = []

        for number in numbers:

            value = int(number)

            if 0 <= value <= 100:

                valid_marks.append(value)

        if not valid_marks:
            continue

        results.append({

            "subject": subject_found,

            "marks": valid_marks[-1],

            "confidence": round(
                line["confidence"] * 100,
                2
            ),

            "raw_text": text
        })

    # Remove duplicates
    unique = {}

    for item in results:

        key = item["subject"].lower()

        if key not in unique:

            unique[key] = item

        elif (
            item["confidence"]
            >
            unique[key]["confidence"]
        ):

            unique[key] = item

    return list(unique.values())


# ============================================================
# TOTAL
# ============================================================

def extract_total(text):

    patterns = [

        r"(?:total\s+marks|total)"
        r"\s*[:\-]?\s*(\d{2,4})",

        r"(\d{2,4})\s*/\s*(?:500|600|700)"
    ]

    value = find_value(
        text,
        patterns
    )

    if value:

        try:
            return int(value)

        except ValueError:
            pass

    return None


# ============================================================
# PERCENTAGE
# ============================================================

def extract_percentage(text):

    patterns = [

        r"(?:percentage|percent)"
        r"\s*[:\-]?\s*"
        r"(\d{1,3}(?:\.\d+)?)\s*%",

        r"(\d{1,3}(?:\.\d+)?)\s*%"
    ]

    value = find_value(
        text,
        patterns
    )

    if value:

        try:
            return float(value)

        except ValueError:
            pass

    return None


# ============================================================
# CALCULATED MARKS
# ============================================================

def calculate_marks(subjects):

    marks = [
        item["marks"]
        for item in subjects
        if isinstance(
            item["marks"],
            int
        )
    ]

    if not marks:

        return None

    total = sum(marks)

    percentage = (
        total /
        (len(marks) * 100)
    ) * 100

    return {

        "subjects_count":
            len(marks),

        "calculated_total":
            total,

        "calculated_percentage":
            round(
                percentage,
                2
            )
    }


# ============================================================
# CONFIDENCE
# ============================================================

def field_confidence(
    lines,
    value
):

    if not value:
        return 0

    value_lower = value.lower()

    scores = []

    for line in lines:

        text = line["text"].lower()

        if (
            value_lower in text
            or
            text in value_lower
        ):

            scores.append(
                line["confidence"]
            )

    if not scores:
        return 0

    return round(
        max(scores) * 100,
        2
    )


# ============================================================
# MAIN
# ============================================================

def extract_marksheet(file_path):

    print("\nLoading document...")

    image = load_document(
        file_path
    )

    print("Checking image quality...")

    quality = check_image_quality(
        image
    )

    print("Running OCR...")

    lines = run_ocr(
        image
    )

    if not lines:

        print(
            "OCR returned no text."
        )

        return None

    text = get_full_text(
        lines
    )

    print(
        f"OCR detected {len(lines)} text lines."
    )

    name = extract_name(
        text
    )

    dob = extract_dob(
        text
    )

    roll_number = extract_roll_number(
        text
    )

    board = detect_board(
        text
    )

    years = extract_years(
        text
    )

    subjects = extract_subject_marks(
        lines
    )

    total = extract_total(
        text
    )

    percentage = extract_percentage(
        text
    )

    calculated = calculate_marks(
        subjects
    )

    result = {

        "document_type":
            "10th Marksheet",

        "board":
            board,

        "student": {

            "name":
                name,

            "date_of_birth":
                dob,

            "roll_number":
                roll_number
        },

        "academic": {

            "subjects":
                subjects,

            "total_marks_extracted":
                total,

            "percentage_extracted":
                percentage,

            "calculated_marks":
                calculated
        },

        "possible_years":
            years,

        "document_quality":
            quality,

        "field_confidence": {

            "name":
                field_confidence(
                    lines,
                    name
                ),

            "date_of_birth":
                field_confidence(
                    lines,
                    dob
                ),

            "roll_number":
                field_confidence(
                    lines,
                    roll_number
                )
        },

        "raw_ocr_text":
            text
    }

    return result


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    project_root = os.path.dirname(os.path.abspath(__file__))
    default_file_path = os.path.join(
        project_root,
        "images",
        "cropped_document.jpg",
    )
    file_path = sys.argv[1] if len(sys.argv) > 1 else default_file_path
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(
        file_path
    ):

        print(
            f"File not found: {file_path}"
        )

        exit(1)

    result = extract_marksheet(
        file_path
    )

    if result:

        print(
            "\n"
            + "=" * 60
        )

        print(
            "MARKSHEET EXTRACTION RESULT"
        )

        print(
            "=" * 60
        )

        print(
            json.dumps(
                result,
                indent=4,
                ensure_ascii=False,
                default=lambda x: x.item() if hasattr(x, "item") else str(x)
            )
        )

        if output_path:
            with open(
                output_path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    result,
                    file,
                    indent=4,
                    ensure_ascii=False,
                    default=lambda x: x.item() if hasattr(x, "item") else str(x)
                )

            print(
                "\nSaved to:"
            )

            print(
                output_path
            )
