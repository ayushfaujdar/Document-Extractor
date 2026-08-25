from __future__ import annotations

import json
import re
import sys
from pathlib import Path


DATE_RE = r"\d{1,2}[/-]\d{1,2}[/-]\d{4}"
AADHAAR_RE = r"\b\d{4}\s?\d{4}\s?\d{4}\b"
PAN_RE = r"\b[A-Z]{5}\d{4}[A-Z]\b"
PHONE_RE = r"\b[6-9]\d{9}\b"
PIN_RE = r"\b\d{6}\b"


def clean(value):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip(" :-")
    return value or None


def lines_from_ocr(ocr):
    raw = clean(ocr.get("raw_text", "")) or ""
    items = ocr.get("text", [])

    lines = []

    for line in raw.splitlines():
        line = clean(line)
        if line:
            lines.append(line)

    if lines:
        return lines

    words = []
    for item in items:
        text = clean(item.get("text"))
        box = item.get("box") or []
        if not text or not box:
            continue
        y = sum(p[1] for p in box) / len(box)
        x = sum(p[0] for p in box) / len(box)
        words.append((y, x, text))

    words.sort()
    grouped = []

    for y, x, text in words:
        if not grouped or abs(grouped[-1][0] - y) > 12:
            grouped.append([y, [(x, text)]])
        else:
            grouped[-1][1].append((x, text))

    for _, row in grouped:
        row.sort()
        lines.append(clean(" ".join(t for _, t in row)))

    return lines


def first_match(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return clean(m.group(1)) if m else None


def extract_generic(ocr, classification=None):
    raw = clean(ocr.get("raw_text", "")) or ""
    lines = lines_from_ocr(ocr)
    joined = "\n".join(lines)

    fields = {}

    m = re.search(AADHAAR_RE, raw)
    if m:
        fields["Aadhaar Number"] = m.group(0)

    m = re.search(PAN_RE, raw.upper())
    if m:
        fields["PAN Number"] = m.group(0)

    dob_patterns = [
        rf"(?:date\s*of\s*birth|dob)\s*[:\-]?\s*({DATE_RE})",
        rf"(?:birth)\s*[:\-]?\s*({DATE_RE})",
    ]

    for pattern in dob_patterns:
        value = first_match(pattern, raw)
        if value:
            fields["Date of Birth"] = value
            break

    label_patterns = {
        "Name": [
            r"(?:^|\n)\s*(?:name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{1,80})",
            r"(?:this is to certify that)\s+([A-Za-z][A-Za-z .'-]{1,80})",
        ],
        "Father's Name": [
            r"(?:father(?:'s|’s)?|father\s*/\s*guardian(?:'s|’s)?)\s*name\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
        ],
        "Mother's Name": [
            r"mother(?:'s|’s)?\s*name\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
        ],
        "Guardian's Name": [
            r"guardian(?:'s|’s)?\s*name\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
        ],
        "Roll Number": [
            r"roll\s*(?:no|number)\.?\s*[:\-]?\s*([A-Z0-9/-]+)",
        ],
        "Registration Number": [
            r"reg(?:istration)?\.?\s*(?:no|number)?\.?\s*[:\-]?\s*([A-Z0-9/-]+)",
        ],
        "Certificate Number": [
            r"certificate\s*(?:no|number)\.?\s*[:\-]?\s*([A-Z0-9/-]+)",
        ],
        "Application Number": [
            r"application\s*(?:no|number)\.?\s*[:\-]?\s*([A-Z0-9/-]+)",
        ],
        "Enrollment Number": [
            r"enrol(?:l)?ment\s*(?:no|number)\.?\s*[:\-]?\s*([A-Z0-9/-]+)",
        ],
        "Gender": [
            r"gender\s*[:\-]?\s*(male|female|transgender)",
        ],
        "Mobile Number": [
            r"(?:mobile|phone|contact)\s*(?:no|number)?\.?\s*[:\-]?\s*(\d{10})",
        ],
        "PIN Code": [
            r"(?:pin|pincode|postal\s*code)\s*[:\-]?\s*(\d{6})",
        ],
    }

    for label, patterns in label_patterns.items():
        for pattern in patterns:
            value = first_match(pattern, raw)
            if value:
                fields[label] = value
                break

    if "Date of Birth" not in fields:
        for line in lines:
            if re.search(r"\b(dob|date\s*of\s*birth)\b", line, re.I):
                m = re.search(DATE_RE, line)
                if m:
                    fields["Date of Birth"] = m.group(0)
                    break

    if "Gender" not in fields:
        for line in lines:
            m = re.search(r"\b(Male|Female|Transgender)\b", line, re.I)
            if m:
                fields["Gender"] = m.group(1).title()
                break

    for i, line in enumerate(lines):
        if re.search(r"\baddress\b", line, re.I):
            value = re.sub(
                r".*?\baddress\b\s*[:\-]?\s*",
                "",
                line,
                flags=re.I,
            ).strip()

            if value and len(value) > 3:
                fields["Address"] = value
            elif i + 1 < len(lines):
                fields["Address"] = lines[i + 1]
            break

    for line in lines:
        m = re.search(r"\bschool\b\s*[:\-]?\s*(.+)", line, re.I)
        if m:
            value = clean(m.group(1))
            if value and value.lower() not in {"name", "information"}:
                fields["School Name"] = value
                break

    generic_labels = [
        "Date of Issue",
        "Issue Date",
        "Expiry Date",
        "Nationality",
        "Category",
        "Caste",
        "Religion",
        "District",
        "State",
        "Village",
        "City",
        "Class",
        "Course",
        "Branch",
        "Institution",
        "Board",
        "University",
        "Result",
    ]

    for label in generic_labels:
        pattern = (
            rf"\b{re.escape(label)}\b"
            rf"\s*[:\-]?\s*([^\n]+)"
        )
        value = first_match(pattern, raw)
        if value and len(value) <= 150:
            fields[label] = value

    document_type = None
    confidence = None

    if isinstance(classification, dict):
        document_type = classification.get("document_type")
        confidence = classification.get("confidence")

    if not document_type or document_type == "UNKNOWN":
        upper = raw.upper()

        if "AADHAAR" in upper or "UNIQUE IDENTIFICATION" in upper:
            document_type = "AADHAAR_CARD"
        elif "PAN" in upper and re.search(PAN_RE, upper):
            document_type = "PAN_CARD"
        elif "MARKS STATEMENT" in upper or "SECONDARY SCHOOL EXAMINATION" in upper:
            document_type = "MARKSHEET"
        elif "BIRTH CERTIFICATE" in upper:
            document_type = "BIRTH_CERTIFICATE"
        elif "TRANSFER CERTIFICATE" in upper:
            document_type = "TRANSFER_CERTIFICATE"
        elif "MIGRATION CERTIFICATE" in upper:
            document_type = "MIGRATION_CERTIFICATE"
        elif "INCOME CERTIFICATE" in upper:
            document_type = "INCOME_CERTIFICATE"
        elif "DOMICILE" in upper or "RESIDENCE CERTIFICATE" in upper:
            document_type = "DOMICILE_CERTIFICATE"
        elif "CASTE CERTIFICATE" in upper:
            document_type = "CASTE_CERTIFICATE"
        else:
            document_type = "OTHER_DOCUMENT"

    return {
        "document_type": document_type,
        "classification_confidence": confidence,
        "fields": fields,
        "all_text": lines,
        "raw_text": raw,
        "field_count": len(fields),
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: python generic_extractor.py <ocr_result.json>")
        sys.exit(1)

    source = Path(sys.argv[1])

    with source.open("r", encoding="utf-8") as f:
        ocr = json.load(f)

    classification = None
    classification_file = source.parent / "classification.json"

    if classification_file.exists():
        try:
            with classification_file.open("r", encoding="utf-8") as f:
                classification = json.load(f)
        except Exception:
            pass

    result = extract_generic(
        ocr,
        classification,
    )

    output = source.parent / "generic_extracted_data.json"

    with output.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    result["output_file"] = str(output)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
