"""OCR text extraction from order images."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

from app.config import get_settings

logger = logging.getLogger("fakturama_automation")


def _configure_tesseract() -> None:
    settings = get_settings()
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def validate_image(image_path: str | Path) -> Path:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        raise ValueError(f"Unsupported image format: {path.suffix}")
    return path


def _preprocess_variants(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    variants: list[tuple[str, np.ndarray]] = [("gray", gray)]

    upscaled = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    variants.append(("upscaled", upscaled))

    denoised = cv2.fastNlMeansDenoising(upscaled, h=10)
    variants.append(("denoised", denoised))

    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    variants.append(("adaptive", adaptive))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(upscaled)
    variants.append(("contrast", contrast))

    return variants


def _score_text(text: str) -> int:
    if not text.strip():
        return 0
    alnum = sum(ch.isalnum() for ch in text)
    words = len([w for w in text.split() if w.strip()])
    return alnum + words * 3


def extract_text(image_path: str | Path) -> str:
    """Run OCR on an order image and return the best extracted text."""
    _configure_tesseract()
    path = validate_image(image_path)
    settings = get_settings()

    pil_image = Image.open(path)
    image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    configs = [
        f"--oem 3 --psm 6 -l {settings.ocr_lang}",
        f"--oem 3 --psm 4 -l {settings.ocr_lang}",
        f"--oem 3 --psm 11 -l {settings.ocr_lang}",
    ]

    best_text = ""
    best_score = -1

    for variant_name, variant in _preprocess_variants(image):
        for config in configs:
            try:
                text = pytesseract.image_to_string(variant, config=config)
            except pytesseract.TesseractNotFoundError as exc:
                raise FileNotFoundError(
                    "Tesseract OCR is not installed or not on PATH. "
                    "Install Tesseract and/or set TESSERACT_CMD in .env."
                ) from exc
            score = _score_text(text)
            logger.debug(
                "OCR variant=%s score=%s chars=%s", variant_name, score, len(text)
            )
            if score > best_score:
                best_score = score
                best_text = text

    logger.info("OCR completed (%s characters extracted)", len(best_text.strip()))
    return best_text.strip()
