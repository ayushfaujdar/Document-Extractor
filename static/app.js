const fileInput = document.getElementById("fileInput");
const uploadBox = document.getElementById("uploadBox");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");

let currentDocumentType = "DOCUMENT";


// =========================================================
// FILE INPUT
// =========================================================

fileInput.addEventListener("change", function () {

    if (this.files && this.files.length > 0) {
        uploadFile(this.files[0]);
    }

});


// =========================================================
// DRAG & DROP
// =========================================================

uploadBox.addEventListener("dragover", function (event) {

    event.preventDefault();

    uploadBox.classList.add("dragging");

});


uploadBox.addEventListener("dragleave", function () {

    uploadBox.classList.remove("dragging");

});


uploadBox.addEventListener("drop", function (event) {

    event.preventDefault();

    uploadBox.classList.remove("dragging");

    const files = event.dataTransfer.files;

    if (files && files.length > 0) {
        uploadFile(files[0]);
    }

});


// =========================================================
// STATUS
// =========================================================

function showStatus(message, type = "success") {

    statusBox.className = `status ${type}`;

    statusBox.textContent = message;

    statusBox.classList.remove("hidden");

}


// =========================================================
// UPLOAD
// =========================================================

async function uploadFile(file) {

    resultsBox.innerHTML = "";

    resultsBox.classList.add("hidden");

    showStatus(
        "Processing document...",
        "processing"
    );

    const formData = new FormData();

    formData.append("file", file);

    try {

        const response = await fetch(
            "/api/upload",
            {
                method: "POST",
                body: formData
            }
        );

        const result = await response.json();

        console.log("SERVER RESPONSE:", result);

        if (!response.ok || !result.success) {

            throw new Error(
                result.error ||
                result.message ||
                "Document processing failed."
            );

        }

        showStatus(
            "Document processed successfully.",
            "success"
        );

        renderResults(
            result.extraction
        );

    } catch (error) {

        console.error(error);

        showStatus(
            error.message ||
            "Something went wrong.",
            "error"
        );

    }

}


// =========================================================
// HELPERS
// =========================================================

function valueOrDash(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "—";
    }

    return escapeHtml(String(value));

}


function escapeHtml(value) {

    return value
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}


function formatLabel(key) {

    return key
        .replace(/_/g, " ")
        .replace(
            /\b\w/g,
            char => char.toUpperCase()
        );

}


function card(title, content) {

    return `
        <section class="result-card">

            <h2>
                ${escapeHtml(title)}
            </h2>

            ${content}

        </section>
    `;

}


function field(label, value) {

    return `
        <div class="result-field">

            <div class="result-label">
                ${escapeHtml(label)}
            </div>

            <div class="result-value">
                ${valueOrDash(value)}
            </div>

        </div>
    `;

}


// =========================================================
// MAIN ROUTER
// =========================================================

function renderResults(extraction) {

    if (!extraction) {
        return;
    }

    currentDocumentType =
        extraction.document_type ||
        "DOCUMENT";


    console.log(
        "DOCUMENT TYPE:",
        currentDocumentType
    );

    console.log(
        "EXTRACTION:",
        extraction
    );


    // -----------------------------------------------------
    // AADHAAR
    // -----------------------------------------------------

    if (currentDocumentType === "AADHAAR") {

        renderAadhaar(extraction);

        return;
    }


    // -----------------------------------------------------
    // PAN
    // -----------------------------------------------------

    if (currentDocumentType === "PAN_CARD") {

        renderPan(extraction);

        return;
    }


    // -----------------------------------------------------
    // CBSE
    // -----------------------------------------------------

    if (
        currentDocumentType === "CBSE_10TH_MARKSHEET" ||
        currentDocumentType === "CBSE_12TH_MARKSHEET"
    ) {

        renderCbse(extraction);

        return;
    }


    // -----------------------------------------------------
    // GENERIC
    // -----------------------------------------------------

    renderGeneric(extraction);

}


// =========================================================
// DOCUMENT INFORMATION
// =========================================================

// =========================================================
// DOCUMENT INFORMATION
// =========================================================

function renderDocumentInfo(extraction) {

    const documentData =
        extraction.document_data || {};


    return card(
        "Document Information",

        `
        <div class="result-grid">

            ${field(
                "Document Type",
                extraction.document_type
            )}

            ${field(
                "Classification Confidence",
                extraction.classification_confidence !== null &&
                extraction.classification_confidence !== undefined
                    ? extraction.classification_confidence + "%"
                    : "—"
            )}

            ${field(
                "Exam Year",
                documentData.exam_year
            )}

            ${field(
                "Result",
                documentData.result
            )}

        </div>
        `
    );

}

// =========================================================
// AADHAAR
// =========================================================

// =========================================================
// AADHAAR
// =========================================================

function renderAadhaar(extraction) {

    const student =
        extraction.student || {};

    const documentData =
        extraction.document_data || {};


    const aadhaar = {
        ...student,
        ...documentData
    };


    console.log(
        "AADHAAR DATA:",
        aadhaar
    );


    let html = "";


    // -----------------------------------------------------
    // Document Information
    // -----------------------------------------------------

    html += renderDocumentInfo(
        extraction
    );


    // -----------------------------------------------------
    // Aadhaar Information
    // -----------------------------------------------------

    html += card(
        "Aadhaar Information",

        `
        <div class="result-grid">

            ${field(
                "Name",
                aadhaar.name
            )}

            ${field(
                "Father's Name",
                aadhaar.father_name
            )}

            ${field(
                "Date of Birth",
                aadhaar.date_of_birth
            )}

            ${field(
                "Year of Birth",
                aadhaar.year_of_birth
            )}

            ${field(
                "Gender",
                aadhaar.gender
            )}

            ${field(
                "Aadhaar Number",
                aadhaar.aadhaar_number
            )}

        </div>
        `
    );


    // -----------------------------------------------------
    // Address
    // -----------------------------------------------------

    html += card(
        "Address",

        `
        <div class="address-box">

            ${valueOrDash(
                aadhaar.address
            )}

        </div>
        `
    );


    renderResultContainer(html);

}


// =========================================================
// PAN
// =========================================================

// =========================================================
// PAN
// =========================================================

function renderPan(extraction) {

    const student =
        extraction.student || {};

    const documentData =
        extraction.document_data || {};

    const data = {
        ...student,
        ...documentData
    };


    console.log(
        "PAN DATA:",
        data
    );


    let html = "";


    // -----------------------------------------------------
    // Document Information
    // -----------------------------------------------------

    html += renderDocumentInfo(
        extraction
    );


    // -----------------------------------------------------
    // PAN Information
    // -----------------------------------------------------

    html += card(
        "PAN Information",

        `
        <div class="result-grid">

            ${field(
                "PAN Number",
                data.pan_number
            )}

            ${field(
                "Name",
                data.name
            )}

            ${field(
                "Father's Name",
                data.father_name
            )}

            ${field(
                "Date of Birth",
                data.date_of_birth
            )}

        </div>
        `
    );


    renderResultContainer(html);

}


// =========================================================
// CBSE
// =========================================================

function renderCbse(extraction) {

    const student =
        extraction.student || {};

    const school =
        extraction.school || {};

    const summary =
        extraction.academic_summary || {};


    let html = "";


    // Document information

    html += renderDocumentInfo(
        extraction
    );


    // Student

    html += card(
        "Student Information",

        `
        <div class="result-grid">

            ${field(
                "Name",
                student.name
            )}

            ${field(
                "Roll Number",
                student.roll_number
            )}

            ${field(
                "Registration Number",
                student.registration_number
            )}

            ${field(
                "Date of Birth",
                student.date_of_birth
            )}

            ${field(
                "Mother's Name",
                student.mother_name
            )}

            ${field(
                "Father's / Guardian's Name",
                student.father_name
            )}

        </div>
        `
    );


    // School

    html += card(
        "School Information",

        `
        <div class="result-grid">

            ${field(
                "School Name",
                school.name
            )}

        </div>
        `
    );


    // Academic summary

    html += card(
        "Academic Summary",

        `
        <div class="result-grid">

            ${field(
                "Total Marks",
                summary.total_marks
            )}

            ${field(
                "Maximum Marks",
                summary.maximum_marks
            )}

            ${field(
                "Percentage",
                summary.percentage !== null &&
                summary.percentage !== undefined
                    ? summary.percentage + "%"
                    : "—"
            )}

            ${field(
                "Subjects",
                summary.subjects
            )}

        </div>
        `
    );


    // Marks

    html += renderMarksTable(
        extraction.marks || []
    );


    renderResultContainer(html);

}


// =========================================================
// MARKS TABLE
// =========================================================

function renderMarksTable(marks) {

    if (
        !marks ||
        marks.length === 0
    ) {

        return card(
            "Marks",

            `
            <p class="no-data">
                No subject marks were extracted.
            </p>
            `
        );

    }


    let rows = "";


    marks.forEach(mark => {

        rows += `
            <tr>

                <td>
                    ${valueOrDash(
                        mark.subject
                    )}
                </td>

                <td>
                    ${valueOrDash(
                        mark.subject_code
                    )}
                </td>

                <td>
                    ${valueOrDash(
                        mark.theory
                    )}
                </td>

                <td>
                    ${valueOrDash(
                        mark.internal_or_practical
                    )}
                </td>

                <td>
                    ${valueOrDash(
                        mark.total
                    )}
                </td>

                <td>
                    ${valueOrDash(
                        mark.grade
                    )}
                </td>

            </tr>
        `;

    });


    return card(
        "Marks",

        `
        <div class="table-wrapper">

            <table class="marks-table">

                <thead>

                    <tr>

                        <th>Subject</th>

                        <th>Code</th>

                        <th>Theory</th>

                        <th>IA / Practical</th>

                        <th>Total</th>

                        <th>Grade</th>

                    </tr>

                </thead>

                <tbody>

                    ${rows}

                </tbody>

            </table>

        </div>
        `
    );

}


// =========================================================
// GENERIC DOCUMENT
// =========================================================

function renderGeneric(extraction) {

    let html = "";


    html += renderDocumentInfo(
        extraction
    );


    const fields =
        extraction.generic_fields ||
        {};


    let content = "";


    Object.entries(fields).forEach(
        ([key, value]) => {

            content += field(
                formatLabel(key),
                value
            );

        }
    );


    if (!content) {

        content = `
            <p class="no-data">
                No structured fields were extracted.
            </p>
        `;

    }


    html += card(
        "Extracted Information",

        `
        <div class="result-grid">

            ${content}

        </div>
        `
    );


    renderResultContainer(html);

}


// =========================================================
// RESULT CONTAINER
// =========================================================

function renderResultContainer(html) {

    resultsBox.innerHTML = `

        <div class="extraction-header">

            <div>

                <span class="extraction-status">
                    ✓ EXTRACTION COMPLETE
                </span>

                <h2>
                    Extracted Document Details
                </h2>

            </div>


            <span class="document-badge">

                ${escapeHtml(
                    currentDocumentType
                )}

            </span>

        </div>


        ${html}


        <button
            class="upload-another"
            onclick="resetUpload()"
        >
            Upload Another Document
        </button>

    `;


    resultsBox.classList.remove(
        "hidden"
    );


    resultsBox.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

}


// =========================================================
// RESET
// =========================================================

function resetUpload() {

    fileInput.value = "";

    resultsBox.innerHTML = "";

    resultsBox.classList.add(
        "hidden"
    );

    statusBox.className =
        "status hidden";

}