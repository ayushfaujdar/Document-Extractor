import json
import sys
from pathlib import Path


# =========================================================
# HELPERS
# =========================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def add_issue(issues, severity, code, message):
    issues.append({
        "severity": severity,
        "code": code,
        "message": message
    })


# =========================================================
# CLASSIFICATION VALIDATION
# =========================================================

def validate_classification(classification, issues):

    decision = classification.get("decision")
    confidence = classification.get("confidence", 0)

    if decision == "UNKNOWN":
        add_issue(
            issues,
            "error",
            "UNKNOWN_DOCUMENT",
            "The document type could not be identified reliably."
        )

    elif decision == "REVIEW_REQUIRED":
        add_issue(
            issues,
            "warning",
            "CLASSIFICATION_REVIEW",
            "The document type could not be identified with high confidence."
        )

    if confidence < 85:
        add_issue(
            issues,
            "warning",
            "LOW_CLASSIFICATION_CONFIDENCE",
            f"Document classification confidence is {confidence}%."
        )


# =========================================================
# HEADER VALIDATION
# =========================================================

def validate_header(extracted, issues):

    student = extracted.get("student", {})

    required_fields = {
        "name": "Student name",
        "roll_number": "Roll number",
    }

    for field, label in required_fields.items():

        value = student.get(field)

        if not value:
            add_issue(
                issues,
                "error",
                f"MISSING_{field.upper()}",
                f"{label} could not be extracted reliably."
            )

    # Optional fields should NOT automatically fail verification.
    #
    # OCR may legitimately fail to read them.
    #
    # This is important because we don't want to reject
    # otherwise usable documents unnecessarily.


# =========================================================
# MARKS VALIDATION
# =========================================================

def validate_marks(marks_result, issues):

    if not marks_result.get("success"):

        add_issue(
            issues,
            "error",
            "MARKS_EXTRACTION_FAILED",
            "The marks table could not be extracted."
        )

        return

    academic_subjects = (
        marks_result.get(
            "academic_subjects",
            []
        )
    )

    if not academic_subjects:

        add_issue(
            issues,
            "error",
            "NO_ACADEMIC_SUBJECTS",
            "No academic subjects could be extracted."
        )

        return

    validation = marks_result.get(
        "validation",
        {}
    )

    errors = validation.get(
        "errors",
        []
    )

    for error in errors:

        subject_code = error.get(
            "subject_code",
            "unknown"
        )

        subject = error.get(
            "subject",
            "Unknown subject"
        )

        error_type = error.get(
            "error"
        )

        if error_type == "total_mismatch":

            add_issue(
                issues,
                "error",
                "MARK_TOTAL_MISMATCH",
                (
                    f"{subject} ({subject_code}) has "
                    f"inconsistent marks."
                )
            )

        elif error_type == "missing_marks":

            add_issue(
                issues,
                "error",
                "MISSING_MARKS",
                (
                    f"{subject} ({subject_code}) "
                    f"has missing marks."
                )
            )


# =========================================================
# FINAL DECISION
# =========================================================

def determine_status(issues):

    errors = [
        issue
        for issue in issues
        if issue["severity"] == "error"
    ]

    warnings = [
        issue
        for issue in issues
        if issue["severity"] == "warning"
    ]

    # -----------------------------------------------------
    # ERROR
    # -----------------------------------------------------

    if errors:

        return "REVIEW"

    # -----------------------------------------------------
    # WARNING
    # -----------------------------------------------------

    if warnings:

        return "REVIEW"

    # -----------------------------------------------------
    # EVERYTHING GOOD
    # -----------------------------------------------------

    return "VERIFIED"


# =========================================================
# MAIN VERIFICATION
# =========================================================

def verify_document(
    classification,
    extracted,
    marks_result
):

    issues = []

    # -----------------------------------------------------
    # Classification
    # -----------------------------------------------------

    validate_classification(
        classification,
        issues
    )

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    validate_header(
        extracted,
        issues
    )

    # -----------------------------------------------------
    # Marks
    # -----------------------------------------------------

    validate_marks(
        marks_result,
        issues
    )

    # -----------------------------------------------------
    # Final status
    # -----------------------------------------------------

    status = determine_status(
        issues
    )

    errors = [
        issue
        for issue in issues
        if issue["severity"] == "error"
    ]

    warnings = [
        issue
        for issue in issues
        if issue["severity"] == "warning"
    ]

    return {

        "status": status,

        "summary": {

            "errors":
                len(errors),

            "warnings":
                len(warnings),

            "issues":
                len(issues)
        },

        "issues":
            issues
    }


# =========================================================
# COMMAND LINE
# =========================================================

if __name__ == "__main__":

    if len(sys.argv) != 4:

        print(
            "Usage:"
        )

        print(
            "python "
            "app/validation/document_verification.py "
            "<classification.json> "
            "<extracted_data.json> "
            "<marks_result.json>"
        )

        sys.exit(1)

    classification_path = Path(
        sys.argv[1]
    )

    extracted_path = Path(
        sys.argv[2]
    )

    marks_path = Path(
        sys.argv[3]
    )

    try:

        classification = load_json(
            classification_path
        )

        extracted = load_json(
            extracted_path
        )

        marks_result = load_json(
            marks_path
        )

        result = verify_document(
            classification,
            extracted,
            marks_result
        )

        # -------------------------------------------------
        # Save result alongside OCR files
        # -------------------------------------------------

        output_path = (
            classification_path.parent /
            "verification_result.json"
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=2,
                ensure_ascii=False
            )

        result["output_file"] = str(
            output_path
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False
            )
        )

    except Exception as error:

        print(
            f"ERROR: {error}"
        )

        sys.exit(1)