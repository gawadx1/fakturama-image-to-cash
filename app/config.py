"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FAKTURAMA_PATH = r"C:\Program Files\Fakturama2\Fakturama.exe"


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    fakturama_path: str
    ocr_lang: str
    ui_timeout: float
    tesseract_cmd: str | None
    screenshots_dir: Path
    groq_max_retries: int = 3

    @classmethod
    def from_env(cls) -> Settings:
        groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        fakturama_path = os.getenv("FAKTURAMA_PATH", DEFAULT_FAKTURAMA_PATH).strip()
        ocr_lang = os.getenv("OCR_LANG", "eng").strip()
        ui_timeout = float(os.getenv("UI_TIMEOUT", "15"))
        tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip() or None
        screenshots_dir = PROJECT_ROOT / "screenshots"
        groq_max_retries = int(os.getenv("GROQ_MAX_RETRIES", "3"))
        return cls(
            groq_api_key=groq_api_key,
            groq_model=groq_model,
            fakturama_path=fakturama_path,
            ocr_lang=ocr_lang,
            ui_timeout=ui_timeout,
            tesseract_cmd=tesseract_cmd,
            screenshots_dir=screenshots_dir,
            groq_max_retries=groq_max_retries,
        )

    def validate_for_run(self, require_groq: bool = True) -> None:
        if require_groq and not self.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and configure it."
            )
        if not Path(self.fakturama_path).exists():
            raise FileNotFoundError(
                f"Fakturama executable not found at: {self.fakturama_path}"
            )


def get_settings() -> Settings:
    return Settings.from_env()
