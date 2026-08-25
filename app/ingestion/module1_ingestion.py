from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

import cv2
import pymupdf


# ============================================================
# SUPPORTED FILE TYPES
# ============================================================

SUPPORTED_IMAGES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff"
}

SUPPORTED_DOCUMENTS = {
    ".pdf",
    ".docx"
}


# ============================================================
# RESULT OBJECT
# ============================================================

@dataclass
class Page:

    page_number: int

    image_path: str

    width: int

    height: int


@dataclass
class IngestionResult:

    job_id: str

    original_filename: str

    detected_type: str

    mime_type: str

    page_count: int

    pages: list[Page]


# ============================================================
# FILE TYPE DETECTION
# ============================================================

def detect_file_type(file_path: Path) -> tuple[str, str]:

    """
    Detect file type using file signatures where possible.

    We don't blindly trust the extension.
    """

    with open(file_path, "rb") as f:

        header = f.read(16)


    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if header.startswith(b"%PDF"):

        return (
            "pdf",
            "application/pdf"
        )


    # --------------------------------------------------------
    # JPEG
    # --------------------------------------------------------

    if header.startswith(b"\xff\xd8\xff"):

        return (
            "jpeg",
            "image/jpeg"
        )


    # --------------------------------------------------------
    # PNG
    # --------------------------------------------------------

    if header.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):

        return (
            "png",
            "image/png"
        )


    # --------------------------------------------------------
    # WEBP
    # --------------------------------------------------------

    if (
        header[:4] == b"RIFF"
        and header[8:12] == b"WEBP"
    ):

        return (
            "webp",
            "image/webp"
        )


    # --------------------------------------------------------
    # TIFF
    # --------------------------------------------------------

    if (
        header.startswith(b"II*\x00")
        or
        header.startswith(b"MM\x00*")
    ):

        return (
            "tiff",
            "image/tiff"
        )


    # --------------------------------------------------------
    # DOCX / XLSX / PPTX
    #
    # These are ZIP containers.
    # --------------------------------------------------------

    if header.startswith(b"PK"):

        try:

            with zipfile.ZipFile(file_path) as z:

                names = set(
                    z.namelist()
                )


            if "[Content_Types].xml" in names:

                if any(
                    x.startswith("word/")
                    for x in names
                ):

                    return (
                        "docx",
                        "application/"
                        "vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    )

                if any(
                    x.startswith("ppt/")
                    for x in names
                ):

                    return (
                        "pptx",
                        "application/"
                        "vnd.openxmlformats-officedocument."
                        "presentationml.presentation"
                    )

                if any(
                    x.startswith("xl/")
                    for x in names
                ):

                    return (
                        "xlsx",
                        "application/"
                        "vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    )

        except zipfile.BadZipFile:

            pass


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    extension = (
        file_path.suffix
        .lower()
    )

    mime_type, _ = mimetypes.guess_type(
        str(file_path)
    )

    if mime_type is None:

        mime_type = (
            "application/octet-stream"
        )


    return (
        extension.lstrip(".") or "unknown",
        mime_type
    )


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(
    image_path: Path
) -> tuple[int, int]:

    """
    Validate image without loading multiple copies
    into memory.
    """

    image = cv2.imread(
        str(image_path),
        cv2.IMREAD_UNCHANGED
    )

    if image is None:

        raise ValueError(
            f"Unable to decode image: "
            f"{image_path.name}"
        )

    height, width = image.shape[:2]

    del image

    if width < 100 or height < 100:

        raise ValueError(
            "Image resolution is too small."
        )

    return (
        width,
        height
    )


# ============================================================
# IMAGE NORMALIZATION
# ============================================================

def normalize_image(
    input_path: Path,
    output_path: Path
) -> tuple[int, int]:

    """
    Convert any supported image into JPEG.

    This gives every downstream module a predictable
    image format.
    """

    image = cv2.imread(
        str(input_path),
        cv2.IMREAD_COLOR
    )

    if image is None:

        raise ValueError(
            f"Could not read image: "
            f"{input_path}"
        )

    height, width = image.shape[:2]

    success = cv2.imwrite(
        str(output_path),
        image,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            95
        ]
    )

    del image

    if not success:

        raise IOError(
            "Failed to write normalized image."
        )

    return (
        width,
        height
    )


# ============================================================
# PDF → IMAGES
# ============================================================

def pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 150
) -> Iterator[Page]:

    """
    Convert PDF pages one at a time.

    IMPORTANT:
    We deliberately DO NOT load every page into memory.

    Memory usage ≈ O(size of one page)
    rather than O(total PDF size).
    """

    document = pymupdf.open(
        str(pdf_path)
    )

    try:

        page_count = len(document)

        zoom = dpi / 72

        matrix = pymupdf.Matrix(
            zoom,
            zoom
        )

        for index in range(
            page_count
        ):

            page = document[index]

            pixmap = page.get_pixmap(
                matrix=matrix,
                alpha=False
            )

            output_path = (
                output_dir /
                f"page_{index + 1:04d}.jpg"
            )

            pixmap.save(
                str(output_path)
            )

            width = pixmap.width
            height = pixmap.height

            # Release page resources immediately
            del pixmap
            del page

            yield Page(
                page_number=index + 1,
                image_path=str(
                    output_path
                ),
                width=width,
                height=height
            )

    finally:

        document.close()


# ============================================================
# DOCX → PDF
# ============================================================

def docx_to_pdf(
    docx_path: Path,
    output_dir: Path
) -> Path:

    """
    Convert DOCX to PDF using LibreOffice.

    LibreOffice must be installed on the machine/server.
    """

    command = [

        "libreoffice",

        "--headless",

        "--convert-to",
        "pdf",

        "--outdir",
        str(output_dir),

        str(docx_path)
    ]

    try:

        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120
        )

    except FileNotFoundError:

        raise RuntimeError(
            "LibreOffice is not installed. "
            "Install LibreOffice to process DOCX files."
        )

    except subprocess.TimeoutExpired:

        raise RuntimeError(
            "DOCX conversion timed out."
        )

    pdf_path = (
        output_dir /
        f"{docx_path.stem}.pdf"
    )

    if not pdf_path.exists():

        raise RuntimeError(
            "DOCX conversion failed."
        )

    return pdf_path


# ============================================================
# MAIN INGESTION FUNCTION
# ============================================================

def ingest_document(
    input_file: str,
    storage_root: str = "storage"
) -> IngestionResult:

    """
    Main entry point for Module 1.
    """

    input_path = Path(
        input_file
    ).resolve()

    if not input_path.exists():

        raise FileNotFoundError(
            f"File does not exist: "
            f"{input_path}"
        )

    if not input_path.is_file():

        raise ValueError(
            "Input path is not a file."
        )


    # --------------------------------------------------------
    # File size protection
    # --------------------------------------------------------

    max_file_size = (
        50 * 1024 * 1024
    )

    file_size = (
        input_path.stat().st_size
    )

    if file_size > max_file_size:

        raise ValueError(
            "File exceeds maximum "
            "allowed size of 50 MB."
        )


    # --------------------------------------------------------
    # Unique job
    # --------------------------------------------------------

    job_id = uuid.uuid4().hex

    job_dir = (
        Path(storage_root)
        / job_id
    )

    pages_dir = (
        job_dir
        / "pages"
    )

    temp_dir = (
        job_dir
        / "temporary"
    )

    pages_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_dir.mkdir(
        exist_ok=True
    )


    # --------------------------------------------------------
    # Detect file
    # --------------------------------------------------------

    file_type, mime_type = (
        detect_file_type(
            input_path
        )
    )

    print(
        f"[Module 1] "
        f"Detected: {file_type}"
    )


    pages = []


    # ========================================================
    # IMAGE
    # ========================================================

    if file_type in {
        "jpeg",
        "png",
        "webp",
        "tiff"
    }:

        output_path = (
            pages_dir /
            "page_0001.jpg"
        )

        width, height = (
            normalize_image(
                input_path,
                output_path
            )
        )

        pages.append(
            Page(
                page_number=1,
                image_path=str(
                    output_path
                ),
                width=width,
                height=height
            )
        )


    # ========================================================
    # PDF
    # ========================================================

    elif file_type == "pdf":

        for page in pdf_to_images(
            input_path,
            pages_dir
        ):

            pages.append(
                page
            )


    # ========================================================
    # DOCX
    # ========================================================

    elif file_type == "docx":

        pdf_path = docx_to_pdf(
            input_path,
            temp_dir
        )

        for page in pdf_to_images(
            pdf_path,
            pages_dir
        ):

            pages.append(
                page
            )


    # ========================================================
    # UNSUPPORTED
    # ========================================================

    else:

        shutil.rmtree(
            job_dir,
            ignore_errors=True
        )

        raise ValueError(
            f"Unsupported file type: "
            f"{file_type}"
        )


    # --------------------------------------------------------
    # Empty document protection
    # --------------------------------------------------------

    if not pages:

        shutil.rmtree(
            job_dir,
            ignore_errors=True
        )

        raise ValueError(
            "Document contains no usable pages."
        )


    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    result = IngestionResult(

        job_id=job_id,

        original_filename=(
            input_path.name
        ),

        detected_type=file_type,

        mime_type=mime_type,

        page_count=len(pages),

        pages=pages
    )


    # --------------------------------------------------------
    # Save metadata
    # --------------------------------------------------------

    metadata_path = (
        job_dir /
        "ingestion.json"
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            asdict(result),
            f,
            indent=2
        )


    return result


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Document Verification "
            "Module 1 - File Ingestion"
        )
    )

    parser.add_argument(
        "file",
        help="Input document"
    )

    args = parser.parse_args()

    try:

        result = ingest_document(
            args.file
        )

        print(
            "\n========== RESULT =========="
        )

        print(
            json.dumps(
                asdict(result),
                indent=2
            )
        )

        print(
            "\nModule 1 completed successfully."
        )

    except Exception as error:

        print(
            f"\nERROR: {error}"
        )