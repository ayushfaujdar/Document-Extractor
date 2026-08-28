# Document Extractor

Document Extractor is a local Flask application that extracts structured data from identity documents and marksheets. It accepts images, PDFs, and DOCX files, runs PaddleOCR, classifies the document, and routes it to a document-specific extractor.

## Quick start

The supported development environment is Python 3.12. Create the environment and install dependencies from the repository root:

~~~bash
brew install python@3.12
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
~~~

PaddleOCR downloads its models on first use. Keep them in the ignored project cache and start the server:

~~~bash
mkdir -p .paddleocr
export PADDLE_OCR_BASE_DIR="$PWD/.paddleocr"
python main.py
~~~

Open http://127.0.0.1:8000.

The important OCR dependency pair is paddlepaddle==2.6.2 and paddleocr==2.10.0. The existing OCR code uses the PaddleOCR 2.x-style API, so do not upgrade PaddleOCR to 3.x without updating app/ocr/module3_ocr.py and its result parsing. NumPy is pinned below version 2 for PaddlePaddle compatibility.

## Capabilities

The active browser flow has dedicated extraction for:

- CBSE 10th marksheets
- CBSE 12th marksheets
- Aadhaar cards
- PAN cards
- Generic or unknown documents

The classifier includes UP Board rules, but UP Board documents currently use the generic extractor because no dedicated UP Board extractor is wired into main.py.

Uploads are limited to 50 MB by the server. The configured extensions are JPG, JPEG, PNG, WEBP, BMP, TIFF, PDF, and DOCX. The UI currently displays a 10 MB message and should be updated if the server limit changes.

## Architecture

~~~text
Browser -> POST /api/upload -> main.py
                               |
                               |-- extension and size validation
                               |-- image quality check
                               |-- Module 1: image/PDF/DOCX ingestion
                               |-- Module 3: PaddleOCR
                               |-- classifier.py
                               |-- document-specific extraction
                               |-- final JSON response
~~~

main.py is the orchestration layer. It runs OCR in-process and invokes several extractors as subprocesses using the active Python interpreter.

## Repository map

~~~text
main.py                         Flask app and pipeline orchestration
requirements.txt                Python dependency pins
templates/index.html             Browser page
static/app.js                   Upload client and result renderers
static/style.css                Browser styling
app/ingestion/module1_ingestion.py
                                File detection, normalization, page creation
app/ocr/module3_ocr.py          Shared PaddleOCR engine
app/ocr/classifier.py           Rule-based document classifier
app/ocr/fast_ocr.py             Optional Tesseract utility
app/ocr/quality_gate.py         Standalone OCR quality rules
app/ocr/feature_extractor.py   Standalone OCR analysis
app/extraction/                 Document-specific extractors
app/validation/                 Standalone validation modules
app/detection/                  Standalone contour detection
document_preprocessor.py        Standalone preprocessing utility
images/                         Sample and intermediate images
tests/                          Test package placeholder
storage/                        Runtime jobs, ignored by Git
~~~

The browser flow does not currently call app/__init__.py, app/detection/module2_detection.py, app/ocr/fast_ocr.py, app/ocr/quality_gate.py, app/ocr/feature_extractor.py, or app/validation/. Treat these as utilities or future integration points until main.py is updated.

## Pipeline details

1. Upload validation checks the extension and the 50 MB request limit.
2. Image quality checks dimensions, blur, and brightness for image uploads.
3. Module 1 creates a UUID job, normalizes images to JPEG, renders PDF pages at 150 DPI, and converts DOCX to PDF through LibreOffice.
4. Module 3 creates one global PaddleOCR object and returns OCR lines with text, confidence, bounding boxes, and raw_text.
5. classifier.py returns document_type, confidence, decision, matching signals, and alternatives.
6. main.py routes the result to the CBSE, marks, Aadhaar, PAN, or generic extractor.
7. build_extraction() creates the common response object consumed by static/app.js.

For CBSE documents, cbse_extractor.py and marks_parser.py run concurrently.

## API

### GET /

Returns the HTML application.

### POST /api/upload

Send one file as multipart form data using the field name file:

~~~bash
curl -X POST \
  -F "file=@images/marksheet.jpeg" \
  http://127.0.0.1:8000/api/upload
~~~

Success responses contain success, status, upload_job_id, job_id, classification, ingestion, quality, and extraction fields. The common extraction fields are document_type, classification_confidence, student, school, academic_summary, marks, document_data, generic_fields, all_text, raw_text, and job_id.

Status codes:

| Code | Meaning |
| --- | --- |
| 200 | Document processed |
| 400 | Missing file or unsupported extension |
| 422 | Image rejected by quality checks |
| 500 | OCR, conversion, or extraction error |

## Runtime files

Each upload creates a UUID job under storage/:

~~~text
storage/input/<upload_job_id>/<uploaded-file>
storage/<job_id>/ingestion.json
storage/<job_id>/pages/page_0001.jpg
storage/<job_id>/temporary/                    DOCX workspace
storage/<job_id>/ocr/ocr_result.json
storage/<job_id>/ocr/ocr_result_0001.json      multi-page OCR
storage/<job_id>/ocr/classification.json
storage/<job_id>/ocr/extracted_data.json       CBSE data
storage/<job_id>/ocr/marks_result.json         marks table
storage/<job_id>/ocr/aadhaar_extracted_data.json
storage/<job_id>/ocr/pan_extracted_data.json
storage/<job_id>/ocr/generic_extracted_data.json
storage/<job_id>/ocr/website_extraction.json   final web result
~~~

Runtime files contain personal documents. The project currently has no database, authentication, encryption, cleanup, or retention policy.

## Optional system dependencies

DOCX uploads require LibreOffice because ingestion invokes the libreoffice command. The optional fast_ocr.py utility requires the Tesseract executable.

~~~bash
brew install --cask libreoffice
brew install tesseract
command -v libreoffice
tesseract --version
~~~

## Useful commands

~~~bash
source .venv312/bin/activate
python -m compileall -q main.py app
python -m pip check

PADDLE_OCR_BASE_DIR="$PWD/.paddleocr" python app/ocr/module3_ocr.py images/marksheet.jpeg
python app/ocr/classifier.py path/to/ocr_result.json
python app/extraction/cbse_extractor.py path/to/ocr_result.json
python app/extraction/marks_parser.py path/to/ocr_result.json
python app/extraction/aadhaar_extractor.py path/to/ocr_result.json
python app/extraction/pan_extractor.py path/to/ocr_result.json
python app/extraction/generic_extractor.py path/to/ocr_result.json
~~~

Standalone utilities include app/validation/marks_validation.py, app/validation/document_verification.py, app/ocr/quality_gate.py, app/ocr/feature_extractor.py, app/ocr/fast_ocr.py, and app/detection/module2_detection.py. Each script prints its own Usage message.

## Development workflow

There are currently no implemented automated tests; tests/ is only a package placeholder. Before opening a change, run compileall and pip check, then manually test the homepage, a clear sample image, a CBSE sample, an unknown document, invalid extensions, and low-quality images.

When changing an extractor, test both its CLI and the browser upload route. The browser depends on the JSON keys consumed by static/app.js.

To add a document type:

1. Add rules and a stable type name in app/ocr/classifier.py.
2. Add an extractor under app/extraction/.
3. Add a runner and output filename in main.py if it is a subprocess.
4. Add routing in run_document_specific_extraction().
5. Map the result in build_extraction().
6. Add a renderer branch in static/app.js if needed.
7. Add sample data and tests, then update this README.

Keep the OCR schema stable. Downstream code expects raw_text and line objects containing text, confidence, and box.

## Known limitations and troubleshooting

- BMP is accepted by the web extension allowlist but is not explicitly handled by ingestion and may fail after upload.
- PDF and DOCX files skip the pre-ingestion image quality check.
- OCR is CPU-bound and can be slow, especially on first inference. Multi-page jobs use up to two workers through OCR_WORKERS in main.py.
- Flask runs with debug=True. The reloader can load the OCR model twice; use debug=False or use_reloader=False while diagnosing model loading.
- ModuleNotFoundError: cv2 usually means the wrong interpreter is active. Activate .venv312 and reinstall requirements.txt.
- Unknown argument: show_log means PaddleOCR 3.x was installed. Reinstall the pinned PaddleOCR 2.10.0 package.
- If models cannot download, check network access and set PADDLE_OCR_BASE_DIR to a writable directory.
- If DOCX conversion fails, install LibreOffice and confirm command -v libreoffice succeeds.

## Data and deployment

This application handles identity documents and educational records. It is intended for local development until authentication, access control, file scanning, storage permissions, retention/deletion, sensitive-log review, rate limiting, request timeouts, and a production WSGI setup are added.

Do not commit uploaded documents, .env files, virtual environments, runtime storage, or .paddleocr model caches. These are covered by .gitignore.
