#!/usr/bin/env python3
"""
Parser for PDF certificates issued by the
National IT Competence Assessment System.
PDFs are stored in certificates/files/.
Generates a Radar Chart (360 diagram) and updates README.md.
"""

import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    sys.exit("Install dependencies: pip install pymupdf matplotlib numpy")

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "certificates" / "files"
CERTS_JSON = ROOT / "certificates" / "certificates.json"
RADAR_IMG = ROOT / "certificates" / "radar.png"
README = ROOT / "README.md"

START_MARKER = "<!-- CERTS_START -->"
END_MARKER = "<!-- CERTS_END -->"
PDF_GLOB = "*Сертификат*.pdf"

DEFAULT_SOURCE_NAME = "National IT Competence Assessment System"

# Map Russian level names to English labels and numerical values for the chart
LEVEL_MAP = {
    "базовый": {"label": "Junior", "value": 1},
    "средний": {"label": "Middle", "value": 2},
    "продвинутый": {"label": "Senior", "value": 3},
}

# Emoji for the Markdown table
LEVEL_EMOJI = {
    "Junior": "🟡",
    "Middle": "🟢",
    "Senior": "🔴",
}

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
        "level": None,      # label: Junior/Middle/Senior
        "score": 0,         # numeric: 1/2/3
        "source": DEFAULT_SOURCE_NAME,
    }

    m = re.search(r"КОМПЕТЕНЦИЙ\s+(.+?)\s+подтвердил", text)
    if m: data["name"] = m.group(1).strip()

    m = re.search(
        r"подтвердил\s+ИТ-компетенцию\s+(.+?)\s+"
        r"(?:Теория|Практика|базовый|средний|экспертный)",
        text, re.IGNORECASE,
    )
    if m: data["competency"] = m.group(1).strip()

    m = re.search(r"\b(Теория|Практика)\b", text, re.IGNORECASE)
    if m: data["section"] = SECTION_MAP.get(m.group(1).lower(), m.group(1).capitalize())

    m = re.search(r"\b(базовый|средний|экспертный)\s+уровень", text, re.IGNORECASE)
    if m:
        level_info = LEVEL_MAP.get(m.group(1).lower())
        if level_info:
            data["level"] = level_info["label"]
            data["score"] = level_info["value"]

    if not data["competency"]:
        guess = pdf_path.name.split("_")[0]
        if guess: data["competency"] = guess

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

def generate_radar_chart(certs: list[dict]) -> bool:
    """Generates a 360-degree radar chart based on highest competency levels."""
    if not certs:
        return False

    # Aggregate highest score per competency
    competencies = {}
    for c in certs:
        comp = c.get("competency") or "Unknown"
        score = c.get("score", 0)
        if score > competencies.get(comp, 0):
            competencies[comp] = score

    labels = list(competencies.keys())
    stats = list(competencies.values())

    num_vars = len(labels)
    if num_vars < 3:
        print("[!] Need at least 3 unique competencies for a radar chart. Skipping.")
        return False

    # Compute angles for each axis
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    stats += stats[:1]
    angles += angles[:1]

    # --- NEW: Dynamic Scaling ---
    # Find the highest score among all certificates
    max_score = max(stats) if stats else 1
    # Add a little padding above the highest score (e.g., if max is 2, scale goes to 2.5)
    y_limit = max_score + 0.5 
    
    # Generate tick positions based on the highest score
    ticks = list(range(1, int(max_score) + 1))
    tick_labels = ["Junior", "Middle", "Senior"][:len(ticks)]
    # -----------------------------

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    
    ax.fill(angles, stats, color='#005bff', alpha=0.25)
    ax.plot(angles, stats, color='#005bff', linewidth=2, marker='o')

    # Set labels for each point (added pad to fix "API" cutoff)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=12, fontweight='bold', pad=15)

    # Y-axis (Radius) configurations with dynamic limits
    ax.set_ylim(0, y_limit)
    ax.set_yticks(ticks)
    ax.set_yticklabels(tick_labels, color="grey", size=10)
    ax.set_rlabel_position(30)

    plt.title("Competency Radar", size=16, fontweight='bold', pad=30)
    plt.grid(color='grey', linestyle='--', linewidth=0.5, alpha=0.7)

    RADAR_IMG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(RADAR_IMG, bbox_inches='tight', dpi=150, transparent=True)
    plt.close()
    
    return True

def render_level(level: str | None) -> str:
    if not level:
        return "—"
    emoji = LEVEL_EMOJI.get(level, "⚪")
    return f"{emoji} {level}"


def render_markdown(certs: list[dict], has_radar: bool) -> str:
    lines = [START_MARKER, ""]
    
    # Insert Radar Chart image if generated
    if has_radar:
        lines.append("### 🕸 Competency Radar")
        lines.append(f"![Competency Radar](./certificates/radar.png)")
        lines.append("")

    if not certs:
        lines.append("_No certificates yet._")
        lines.append(END_MARKER)
        return "\n".join(lines)

    lines += [
        "### 📜 Certificates List",
        "",
        "| Competency | Source | Level | Certificate |",
        "|---|---|---|---|",
    ]
    for c in certs:
        competency = c.get("competency") or "—"
        source = c.get("source") or DEFAULT_SOURCE_NAME
        level = render_level(c.get("level"))
        file_link = f"[📄 Open PDF](./certificates/files/{c['file']})" if c.get("file") else "—"

        lines.append(f"| {competency} | {source} | {level} | {file_link} |")

    lines += ["", END_MARKER]
    return "\n".join(lines)


def update_readme(block: str) -> bool:
    if not README.exists():
        README.write_text(block + "\n", encoding="utf-8")
        return True

    content = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)

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
    CERTS_JSON.write_text(json.dumps(certs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    has_radar = generate_radar_chart(certs)
    if has_radar:
        print("Radar chart generated.")
    
    block = render_markdown(certs, has_radar)
    changed = update_readme(block)
    print("README updated." if changed else "README unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
