import json
import sys


def validate_marks(data):

    if not data.get("success"):
        return {
            "status": "FAIL",
            "errors": ["Marks parsing failed"],
            "warnings": []
        }

    subjects = data.get(
        "academic_subjects",
        []
    )

    errors = []
    warnings = []

    valid_subjects = 0
    review_subjects = 0

    for subject in subjects:

        code = subject.get(
            "subject_code"
        )

        name = subject.get(
            "subject"
        )

        theory = subject.get(
            "theory"
        )

        internal = subject.get(
            "internal_or_practical"
        )

        total = subject.get(
            "total"
        )

        validation = subject.get(
            "validation",
            {}
        )

        # -------------------------------------------------
        # Missing marks
        # -------------------------------------------------

        missing = []

        if theory is None:
            missing.append("theory")

        if internal is None:
            missing.append(
                "internal_or_practical"
            )

        if total is None:
            missing.append("total")

        if missing:

            review_subjects += 1

            warnings.append({
                "subject_code": code,
                "subject": name,
                "type": "ocr_ambiguity",
                "missing_fields": missing
            })

            continue

        # -------------------------------------------------
        # Arithmetic validation
        # -------------------------------------------------

        expected = (
            theory + internal
        )

        if total != expected:

            review_subjects += 1

            warnings.append({
                "subject_code": code,
                "subject": name,
                "type": "total_mismatch",
                "expected": expected,
                "actual": total
            })

            continue

        # -------------------------------------------------
        # Valid subject
        # -------------------------------------------------

        valid_subjects += 1

    # =====================================================
    # OVERALL STATUS
    # =====================================================

    if not subjects:

        status = "FAIL"

    elif review_subjects > 0:

        status = "REVIEW"

    else:

        status = "PASS"

    return {

        "status": status,

        "summary": {
            "subjects_found": len(subjects),
            "valid_subjects": valid_subjects,
            "review_subjects": review_subjects
        },

        "errors": errors,

        "warnings": warnings
    }


# =========================================================
# COMMAND LINE
# =========================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: python app/validation/marks_validation.py <marks_json>"
        )

        sys.exit(1)

    try:

        with open(
            sys.argv[1],
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        result = validate_marks(data)

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