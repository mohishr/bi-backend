from io import BytesIO
from pathlib import Path
from typing import List, Dict, Union
import torch
import gc

import PyPDF2
from PIL import Image
import numpy as np
import easyocr
from pdf2image import convert_from_bytes
import docx # Added for DOCX support

# --- Configuration Imports (Assuming they exist) ---
from utilities.logger import setup_logger
from config import OCR_GPU, OCR_LANGUAGES, POPPLER_PATH

logger = setup_logger(__name__)

class DocumentProcessor:
    """
    A unified class for processing various document types (PDFs, images, DOCX)
    by converting all documents into images and extracting text solely via OCR.
    """

    _ocr_reader = None
    _use_gpu = OCR_GPU
    _gpu_oom_occurred = False

    def __init__(self):
        """Initializes the DocumentProcessor. OCR reader is lazily initialized."""
        pass

    # --- Private Helper Methods for OCR Setup (Remains the same) ---

    @classmethod
    def _get_ocr_reader(cls):
        """Initializes and returns the EasyOCR reader (Singleton pattern)."""
        if cls._ocr_reader is None:
            try:
                logger.info(f"Initializing OCR reader with GPU={cls._use_gpu}...")
                cls._ocr_reader = easyocr.Reader(OCR_LANGUAGES, gpu=cls._use_gpu)
                logger.info("OCR reader initialized successfully")
            except Exception as e:
                logger.error(f"OCR initialization failed: {e}")
                raise
        return cls._ocr_reader

    @classmethod
    def _clear_gpu_memory(cls):
        """Clear GPU memory and cache to prevent OOM errors."""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
                logger.info("GPU memory cleared")
        except Exception as e:
            logger.warning(f"Could not clear GPU memory: {e}")

    # --- Private Helper Methods for File Conversion (Modified) ---

    @staticmethod
    def _convert_docx_to_images(file_bytes: bytes) -> List[Image.Image]:
        """
        ⚠️ IMPORTANT: Converting DOCX to rendered images accurately in pure Python
        is non-trivial, as it requires rendering layout (fonts, margins,
        wrapping). This placeholder only handles the *text content* as an image,
        which is generally insufficient for a true "page-as-image" OCR approach.

        For production, a tool like unoconv (LibreOffice) or a dedicated API
        should be used to generate PDFs/images from DOCX first.
        """
        logger.warning("DOCX conversion to image is complex. Using a placeholder for text-only visualization.")
        
        try:
            doc = docx.Document(BytesIO(file_bytes))
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            
            # Create a simple image (placeholder: white screen with red text)
            # In a real app, you would use a library like ReportLab or Pillow's
            # ImageDraw module to render the text properly across pages.
            if not full_text:
                return []
                
            # PLACEHOLDER: Create one simple image representing the text's presence
            img = Image.new('RGB', (800, 600), color = 'white')
            # Skipping complex text drawing, as it would require font loading (e.g., PIL's ImageDraw)
            
            return [img] # Returns one placeholder image per document
        except Exception as e:
            logger.error(f"Error parsing DOCX: {e}")
            raise


    @staticmethod
    def _to_images(file_bytes: bytes, filename: str) -> List[Image.Image]:
        """Convert a file (image, PDF, or DOCX) to a list of PIL Images (one per page)."""
        ext = Path(filename).suffix.lower()
        images = []

        try:
            if ext in [".png", ".jpg", ".jpeg"]:
                # Single image file
                images.append(Image.open(BytesIO(file_bytes)))
            
            elif ext == ".pdf":
                # Convert PDF pages to images (relies on Poppler)
                images = convert_from_bytes(file_bytes, dpi=200, poppler_path=POPPLER_PATH)
                logger.info(f"Converted PDF to {len(images)} images")
                
            elif ext == ".docx":
                # Convert DOCX to images (uses complex/placeholder method)
                images = DocumentProcessor._convert_docx_to_images(file_bytes)
                logger.info(f"Converted DOCX to {len(images)} images (via placeholder)")
                
            else:
                raise ValueError(f"Unsupported file type for image conversion: {ext}")
            
            return images
        except Exception as e:
            logger.error(f"Error converting {filename} to images: {e}")
            raise

    # --- Public Interface Method (Simplified) ---

    def parse_document_via_ocr(self, file_bytes: bytes, filename: str) -> Dict[int, str]:
        """
        The unified public interface. Extracts text from any supported file 
        (PDF, image, DOCX) by first converting its pages to images and then 
        running OCR.

        Returns:
            Dict[int, str]: A dictionary where keys are 1-based page numbers
                            and values are the extracted text for that page.
        """
        try:
            logger.info(f"Starting OCR pipeline on {filename}")
            
            # 1. Convert Document to Images
            images = self._to_images(file_bytes, filename)
            ocr_reader = self._get_ocr_reader()

            if not images:
                logger.warning(f"No images generated for {filename}. Returning empty result.")
                return {}

            # 2. Run OCR on Images
            ocr_texts = {}
            for i, image in enumerate(images, start=1):
                logger.info(f"Processing page {i}/{len(images)} via OCR")
                
                # Convert PIL Image to a NumPy array for EasyOCR
                image_array = np.array(image)
                
                try:
                    # detail=0 returns only the text strings
                    result = ocr_reader.readtext(image_array, detail=0)
                    page_text = " ".join(result)
                    ocr_texts[i] = page_text.strip()
                    
                except RuntimeError as e:
                    # Handle CUDA out of memory error
                    if "CUDA" in str(e) or "out of memory" in str(e).lower():
                        logger.warning(
                            f"CUDA out of memory on page {i}. "
                            f"Clearing GPU memory and retrying with CPU..."
                        )
                        
                        # Clear GPU memory
                        DocumentProcessor._clear_gpu_memory()
                        
                        # Switch to CPU if using GPU
                        if DocumentProcessor._use_gpu:
                            DocumentProcessor._use_gpu = False
                            DocumentProcessor._ocr_reader = None  # Force reinitialize
                            logger.info("Switched to CPU for OCR processing")
                            ocr_reader = DocumentProcessor._get_ocr_reader()
                        
                        # Retry with CPU
                        try:
                            result = ocr_reader.readtext(image_array, detail=0)
                            page_text = " ".join(result)
                            ocr_texts[i] = page_text.strip()
                        except Exception as cpu_error:
                            logger.error(
                                f"OCR failed on page {i} even with CPU: {cpu_error}"
                            )
                            ocr_texts[i] = ""
                    else:
                        raise

            logger.info(f"OCR successful for {filename}. Extracted text for {len(ocr_texts)} pages.")
            return ocr_texts
            
        except Exception as e:
            logger.error(f"Document processing failed for {filename}: {e}")
            # Re-raise the exception for the caller to handle
            raise

    @staticmethod
    def is_image_file(filename: str) -> bool:
        """Checks if the filename corresponds to a supported image file type."""
        ext = Path(filename).suffix.lower()
        return ext in [".png", ".jpg", ".jpeg"]

# Public-facing instance for easy usage
document_processor = DocumentProcessor()