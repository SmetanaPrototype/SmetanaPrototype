#!/usr/bin/env python3
"""
Parser for PDF certificates issued by the
National IT Competence Assessment System.
PDFs are stored in certificates/files/.
Updates README.md in the repo root and saves data to certificates/certificates.json.
"""

import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Install PyMuPDF: pip install pymupdf")

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "certificates" / "files"
CERTS_JSON = ROOT / "certificates" / "certificates.json"
README = ROOT / "README.md"

START_MARKER = "<!-- CERTS_START -->"
END_MARKER = "<!-- CERTS_END -->"
PDF_GLOB = "*Сертификат*.pdf"

# Default source name (can be overridden per-entry in certificates.json)
DEFAULT_SOURCE_NAME = "National IT Competence Assessment System"

# Map Russian level names from the PDF to English labels
LEVEL_MAP = {
    "базовый": "junior",
    "продвинутый": "middle",
    "экспертный": "senior",
}

# Colored emoji per level
LEVEL_EMOJI = {
    "junior": "🟡",
    "middle": "🟢",
    "senior": "🔴",
}
DEFAULT_LEVEL_EMOJI = "⚪"

# Map Russian section names to English
SECTION_MAP = {
    "теория": "Theory",
    "практика": "Practice",
}


def extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return re.sub(r"\s+", " ", text).strip()


def parse_certificate(pdf_path: Path) -> dict:
    text = extract_text(pdf_path)

    data = {
        "file": pdf_path.name,
        "name": None,
        "competency": None,
        "section": None,
        "level": None,
        "source": DEFAULT_SOURCE_NAME,
    }

    # Full name
    m = re.search(r"КОМПЕТЕНЦИЙ\s+(.+?)\s+подтвердил", text)
    if m:
        data["name"] = m.group(1).strip()

    # Competency
    m = re.search(
        r"подтвердил\s+ИТ-компетенцию\s+(.+?)\s+"
        r"(?:Теория|Практика|базовый|продвинутый|экспертный)",
        text,
        re.IGNORECASE,
    )
    if m:
        data["competency"] = m.group(1).strip()

    # Section: Theory / Practice
    m = re.search(r"\b(Теория|Практика)\b", text, re.IGNORECASE)
    if m:
        data["section"] = SECTION_MAP.get(m.group(1).lower(), m.group(1).capitalize())

    # Level: junior / middle / senior
    m = re.search(r"\b(базовый|продвинутый|экспертный)\s+уровень", text, re.IGNORECASE)
    if m:
        data["level"] = LEVEL_MAP.get(m.group(1).lower(), m.group(1).lower())

    # Fallback: competency from filename prefix
    if not data["competency"]:
        guess = pdf_path.name.split("_")[0]
        if guess:
            data["competency"] = guess

    return data


def collect_certificates() -> list[dict]:
    if not CERT_DIR.exists():
        print(f"[!] Folder not found: {CERT_DIR}", file=sys.stderr)
        return []

    certs = []
    for pdf in sorted(CERT_DIR.glob(PDF_GLOB)):
        if pdf.is_file():
            try:
                certs.append(parse_certificate(pdf))
            except Exception as e:
                print(f"[!] Failed to parse {pdf.name}: {e}", file=sys.stderr)

    certs.sort(key=lambda c: (c.get("competency") or "").lower())
    return certs


def render_level(level: str | None) -> str:
    """Return level label prefixed with a colored emoji."""
    if not level:
        return "—"
    key = level.lower()
    emoji = LEVEL_EMOJI.get(key, DEFAULT_LEVEL_EMOJI)
    return f"{emoji} {key}"


def render_markdown(certs: list[dict]) -> str:
    if not certs:
        return f"{START_MARKER}\n_No certificates yet._\n{END_MARKER}"

    lines = [
        START_MARKER,
        "",
        "| Competency | Source | Section | Level | File |",
        "|---|---|---|---|---|",
    ]
    for c in certs:
        competency = c.get("competency") or "—"
        source = c.get("source") or DEFAULT_SOURCE_NAME
        section = c.get("section") or "—"
        level = render_level(c.get("level"))
        file_link = f"[PDF](./certificates/files/{c['file']})" if c.get("file") else "—"

        lines.append(
            f"| {competency} | {source} | {section} | {level} | {file_link} |"
        )

    lines += ["", END_MARKER]
    return "\n".join(lines)


def update_readme(block: str) -> bool:
    if not README.exists():
        README.write_text(block + "\n", encoding="utf-8")
        return True

    content = README.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )

    if pattern.search(content):
        new_content = pattern.sub(block, content)
    else:
        new_content = content.rstrip() + "\n\n" + block + "\n"

    if new_content != content:
        README.write_text(new_content, encoding="utf-8")
        return True
    return False


def main() -> int:
    certs = collect_certificates()
    print(f"Certificates found: {len(certs)}")

    CERTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CERTS_JSON.write_text(
        json.dumps(certs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    block = render_markdown(certs)
    changed = update_readme(block)
    print("README updated." if changed else "README unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
