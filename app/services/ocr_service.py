"""
Extracts text from uploaded documents (PDFs and images).

Strategy:
1. PDFs → Try PyMuPDF text extraction first (fast, free, works on digital PDFs)
2. If minimal text found (scanned PDF) → Fall back to OCR
3. Images → OCR directly

OCR backends (in order of preference):
- Tesseract (free, self-hosted, good enough for receipts/invoices)
- Google Document AI (optional, higher accuracy)
"""

import os
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


# Minimum character count to consider a PDF "text-based" rather than scanned
MIN_TEXT_THRESHOLD = 50

# Tesseract config for financial documents
TESSERACT_CONFIG = "--oem 3 --psm 6"  # LSTM engine, assume uniform block of text


class OCRError(Exception):
    """Raised when OCR processing fails."""
    pass


class OCRService:
    """
    Extract text from PDFs and images.

    Usage:
        ocr = OCRService()

        # From file path
        text = ocr.extract_text("/path/to/receipt.pdf")

        # From bytes
        text = ocr.extract_text_from_bytes(file_bytes, "application/pdf")
    """

    def __init__(self):
        self.backend = os.getenv("OCR_BACKEND", "tesseract").lower()

        if not HAS_PYMUPDF:
            logger.warning("PyMuPDF not installed — PDF text extraction unavailable")
        if not HAS_PIL:
            logger.warning("Pillow not installed — image OCR unavailable")
        if not HAS_TESSERACT and self.backend == "tesseract":
            logger.warning("pytesseract not installed — OCR unavailable")

    def extract_text(self, file_path: str) -> str:
        """
        Extract text from a file on disk.

        Args:
            file_path: Absolute path to PDF or image file

        Returns:
            Extracted text content
        """
        path = Path(file_path)
        if not path.exists():
            raise OCRError(f"File not found: {file_path}")

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_from_pdf(file_path)
        elif suffix in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff"):
            return self._extract_from_image(file_path)
        else:
            raise OCRError(f"Unsupported file type: {suffix}")

    def extract_text_from_bytes(
        self, file_bytes: bytes, content_type: str, filename: str = ""
    ) -> str:
        """
        Extract text from file bytes (e.g., from an upload).

        Args:
            file_bytes: Raw file bytes
            content_type: MIME type (application/pdf, image/jpeg, etc.)
            filename: Original filename (for logging)

        Returns:
            Extracted text content
        """
        if content_type == "application/pdf":
            return self._extract_from_pdf_bytes(file_bytes)
        elif content_type.startswith("image/"):
            return self._extract_from_image_bytes(file_bytes)
        else:
            raise OCRError(f"Unsupported content type: {content_type}")


    # PDF EXTRACTION
    def _extract_from_pdf(self, file_path: str) -> str:
        """Extract text from a PDF file."""
        with open(file_path, "rb") as f:
            return self._extract_from_pdf_bytes(f.read())

    def _extract_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        """
        Extract text from PDF bytes.

        Strategy:
        1. Try PyMuPDF text extraction (works on digital/text-based PDFs)
        2. If result is sparse (scanned PDF), OCR each page as an image
        """
        if not HAS_PYMUPDF:
            raise OCRError("PyMuPDF not installed. Run: pip install pymupdf")

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Step 1: Try direct text extraction
        all_text = []
        for page in doc:
            text = page.get_text("text").strip()
            all_text.append(text)

        combined = "\n\n".join(all_text).strip()

        # If we got meaningful text, return it
        if len(combined) >= MIN_TEXT_THRESHOLD:
            logger.info(
                f"PDF text extraction: {len(combined)} chars from {len(doc)} pages"
            )
            doc.close()
            return combined

        # Step 2: Scanned PDF — OCR each page as image
        logger.info("PDF appears scanned — falling back to OCR")
        ocr_text = []

        for page_num, page in enumerate(doc):
            try:
                # Render page to image at 300 DPI for good OCR quality
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")

                page_text = self._ocr_image_bytes(img_bytes)
                if page_text:
                    ocr_text.append(f"--- Page {page_num + 1} ---\n{page_text}")

            except Exception as e:
                logger.warning(f"OCR failed on page {page_num + 1}: {e}")
                continue

        doc.close()

        result = "\n\n".join(ocr_text).strip()
        logger.info(f"PDF OCR extraction: {len(result)} chars")
        return result


    # IMAGE EXTRACTION
    def _extract_from_image(self, file_path: str) -> str:
        """Extract text from an image file."""
        with open(file_path, "rb") as f:
            return self._extract_from_image_bytes(f.read())

    def _extract_from_image_bytes(self, img_bytes: bytes) -> str:
        """Extract text from image bytes."""
        return self._ocr_image_bytes(img_bytes)


    # OCR BACKENDS
    def _ocr_image_bytes(self, img_bytes: bytes) -> str:
        """
        Run OCR on raw image bytes using the configured backend.
        """
        if self.backend == "tesseract":
            return self._ocr_tesseract(img_bytes)
        elif self.backend == "google":
            return self._ocr_google_document_ai(img_bytes)
        else:
            raise OCRError(f"Unknown OCR backend: {self.backend}")

    def _ocr_tesseract(self, img_bytes: bytes) -> str:
        """OCR using Tesseract (free, local)."""
        if not HAS_TESSERACT:
            raise OCRError(
                "pytesseract not installed. Run: pip install pytesseract\n"
                "Also install Tesseract: brew install tesseract (macOS)"
            )
        if not HAS_PIL:
            raise OCRError("Pillow not installed. Run: pip install pillow")

        try:
            image = Image.open(io.BytesIO(img_bytes))

            # Convert to RGB if needed (RGBA/P modes cause issues)
            if image.mode in ("RGBA", "P", "LA"):
                image = image.convert("RGB")

            text = pytesseract.image_to_string(image, config=TESSERACT_CONFIG)
            return text.strip()

        except pytesseract.TesseractNotFoundError:
            raise OCRError(
                "Tesseract binary not found. Install it:\n"
                "  macOS:  brew install tesseract\n"
                "  Ubuntu: sudo apt-get install tesseract-ocr\n"
                "  Docker: see Dockerfile"
            )
        except Exception as e:
            raise OCRError(f"Tesseract OCR failed: {e}")

    def _ocr_google_document_ai(self, img_bytes: bytes) -> str:
        """
        OCR using Google Document AI (optional, higher accuracy).
        """
        try:
            from google.cloud import documentai_v1 as documentai
        except ImportError:
            raise OCRError(
                "google-cloud-documentai not installed. "
                "Run: pip install google-cloud-documentai"
            )

        project_id = os.getenv("GOOGLE_DOC_AI_PROJECT_ID")
        location = os.getenv("GOOGLE_DOC_AI_LOCATION", "eu")
        processor_id = os.getenv("GOOGLE_DOC_AI_PROCESSOR_ID")

        if not all([project_id, processor_id]):
            raise OCRError(
                "Google Document AI not configured. Set env vars: "
                "GOOGLE_DOC_AI_PROJECT_ID, GOOGLE_DOC_AI_PROCESSOR_ID"
            )

        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(project_id, location, processor_id)

        raw_document = documentai.RawDocument(
            content=img_bytes,
            mime_type="image/png",
        )

        request = documentai.ProcessRequest(
            name=name,
            raw_document=raw_document,
        )

        result = client.process_document(request=request)
        return result.document.text.strip()



# CONVENIENCE FUNCTIONS
_ocr: Optional[OCRService] = None

def get_ocr_service() -> OCRService:
    """Get the singleton OCR service."""
    global _ocr
    if _ocr is None:
        _ocr = OCRService()
    return _ocr
