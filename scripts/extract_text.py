import sys
import json
from pathlib import Path
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

MIN_NATIVE_CHARS = 20  # below this, treat page as scanned/image


def extract_pages(pdf_path):
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        source = "native"
        if len(text) < MIN_NATIVE_CHARS:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img).strip()
            source = "ocr"
        pages.append({"page": i + 1, "text": text, "source": source})
    return pages


if __name__ == "__main__":
    pdf_path = Path(sys.argv[1])
    out_dir = Path("state") / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "pages.json"

    if out_file.exists():
        print(f"{out_file} already exists, skipping extraction.")
    else:
        pages = extract_pages(pdf_path)
        out_file.write_text(json.dumps(pages, indent=2))
        print(f"Extracted {len(pages)} pages -> {out_file}")
