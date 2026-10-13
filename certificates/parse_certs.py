#!/usr/bin/env python3
"""
Парсер PDF-сертификатов «Национальная система оценки ИТ-компетенций».
PDF лежат в certificates/files/.
Обновляет README.md в корне и сохраняет данные в certificates/certificates.json.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Установите PyMuPDF: pip install pymupdf")

ROOT = Path(__file__).resolve().parent.parent   # корень репозитория
CERT_DIR = ROOT / "certificates" / "files"
CERTS_JSON = ROOT / "certificates" / "certificates.json"
README = ROOT / "README.md"

START_MARKER = "<!-- CERTS_START -->"
END_MARKER = "<!-- CERTS_END -->"
PDF_GLOB = "*Сертификат*.pdf"


def extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return re.sub(r"\s+", " ", text).strip()


def parse_certificate(pdf_path: Path) -> dict:
    text = extract_text(pdf_path)

    data = {
        "file": pdf_path.name,
        "issuer": "Национальная система оценки ИТ-компетенций",
        "name": None,
        "competency": None,
        "section": None,
        "level": None,
        "valid_until": None,
        "valid_until_display": None,
    }

    m = re.search(r"КОМПЕТЕНЦИЙ\s+(.+?)\s+подтвердил", text)
    if m:
        data["name"] = m.group(1).strip()

    m = re.search(
        r"подтвердил\s+ИТ-компетенцию\s+(.+?)\s+"
        r"(?:Теория|Практика|базовый|продвинутый|экспертный)",
        text,
        re.IGNORECASE,
    )
    if m:
        data["competency"] = m.group(1).strip()

    m = re.search(r"\b(Теория|Практика)\b", text, re.IGNORECASE)
    if m:
        data["section"] = m.group(1).capitalize()

    m = re.search(r"\b(базовый|продвинутый|экспертный)\s+уровень", text, re.IGNORECASE)
    if m:
        data["level"] = m.group(0).strip().lower()

    m = re.search(r"действителен до:\s*(\d{2}\.\d{2}\.\d{4})", text)
    if m:
        display = m.group(1)
        data["valid_until_display"] = display
        try:
            data["valid_until"] = datetime.strptime(display, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass

    if not data["competency"]:
        guess = pdf_path.name.split("_")[0]
        if guess:
            data["competency"] = guess

    return data


def collect_certificates() -> list[dict]:
    if not CERT_DIR.exists():
        print(f"[!] Папка не найдена: {CERT_DIR}", file=sys.stderr)
        return []

    certs = []
    for pdf in sorted(CERT_DIR.glob(PDF_GLOB)):
        if pdf.is_file():
            try:
                certs.append(parse_certificate(pdf))
            except Exception as e:
                print(f"[!] Ошибка при парсинге {pdf.name}: {e}", file=sys.stderr)

    certs.sort(
        key=lambda c: (c.get("valid_until") or "", c.get("competency") or ""),
        reverse=True,
    )
    return certs


def render_markdown(certs: list[dict]) -> str:
    if not certs:
        return f"{START_MARKER}\n_Сертификаты пока не добавлены._\n{END_MARKER}"

    lines = [
        START_MARKER,
        "",
        "| Компетенция | Раздел | Уровень | Действителен до | Файл |",
        "|---|---|---|---|---|",
    ]
    for c in certs:
        competency = c.get("competency") or "—"
        section = c.get("section") or "—"
        level = c.get("level") or "—"
        valid = c.get("valid_until_display") or "—"
        file_link = f"[PDF](./certificates/files/{c['file']})" if c.get("file") else "—"
        lines.append(f"| {competency} | {section} | {level} | {valid} | {file_link} |")

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
    print(f"Найдено сертификатов: {len(certs)}")

    CERTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CERTS_JSON.write_text(
        json.dumps(certs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    block = render_markdown(certs)
    changed = update_readme(block)
    print("README обновлён." if changed else "README без изменений.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
