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
import hashlib
from pathlib import Path

try:
    import pymupdf as fitz
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    sys.exit("Install dependencies: pip install pymupdf matplotlib numpy")

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "certificates" / "files"
CERTS_JSON = ROOT / "certificates" / "certificates.json"
RADAR_IMG = ROOT / "certificates" / "radar.png"
README = ROOT / "README.md"

# Unified marker for the whole block
HHCERTS_START = "<!-- HHCERTS_START -->"
HHCERTS_END = "<!-- HHCERTS_END -->"

PDF_GLOB = "*Сертификат*.pdf"

DEFAULT_SOURCE_NAME = "National IT Competence Assessment System"

LEVEL_MAP = {
    "базовый": {"label": "Junior", "value": 1},
    "средний": {"label": "Middle", "value": 2},
    "продвинутый": {"label": "Senior", "value": 3},
    "экспертный": {"label": "Senior", "value": 3},
}

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
        "level": None,
        "score": 0,
        "source": DEFAULT_SOURCE_NAME,
    }

    m = re.search(r"КОМПЕТЕНЦИЙ\s+(.+?)\s+подтвердил", text)
    if m: data["name"] = m.group(1).strip()

    m = re.search(
        r"подтвердил\s+ИТ-компетенцию\s+(.+?)\s+"
        r"(?:Теория|Практика|базовый|средний|продвинутый|экспертный)",
        text, re.IGNORECASE,
    )
    if m: data["competency"] = m.group(1).strip()

    m = re.search(r"\b(Теория|Практика)\b", text, re.IGNORECASE)
    if m: data["section"] = SECTION_MAP.get(m.group(1).lower(), m.group(1).capitalize())

    m = re.search(r"\b(базовый|средний|продвинутый|экспертный)\s+уровень", text, re.IGNORECASE)
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
    if not certs:
        return False

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

    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    stats += stats[:1]
    angles += angles[:1]

    max_score = max(stats) if stats else 1
    y_limit = max_score + 0.5 
    
    ticks = list(range(1, int(max_score) + 1))
    tick_labels = ["Junior", "Middle", "Senior"][:len(ticks)]

    # Aesthetics
    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    line_color = '#2f81f7' # GitHub Blue
    text_color = '#1F2328' # GitHub Dark Text
    grid_color = '#D0D7DE' # GitHub Border

    # Plot thick lines and nice dots
    ax.plot(angles, stats, color=line_color, linewidth=2.5, zorder=3)
    ax.fill(angles, stats, color=line_color, alpha=0.15, zorder=2)
    ax.scatter(angles[:-1], stats[:-1], color=line_color, s=60, zorder=4, edgecolors='white', linewidth=1.5)

    # Hide outer spine
    ax.spines['polar'].set_visible(False)

    # Solid, slightly thicker grid
    ax.grid(color=grid_color, linestyle='-', linewidth=1, alpha=0.7)

    # Larger fonts
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=14, color=text_color, fontweight='600')
    ax.tick_params(axis='x', pad=20)

    ax.set_ylim(0, y_limit)
    ax.set_yticks(ticks)
    ax.set_yticklabels(tick_labels, color='#57606a', size=11)
    ax.set_rlabel_position(45)

    RADAR_IMG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(RADAR_IMG, bbox_inches='tight', dpi=200, transparent=True, pad_inches=0.1)
    plt.close()
    
    return True


def get_file_hash(path: Path) -> str:
    if not path.exists():
        return "0"
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


def render_level(level: str | None) -> str:
    if not level:
        return "—"
    emoji = LEVEL_EMOJI.get(level, "⚪")
    return f"{emoji} {level}"


def render_block(certs: list[dict], has_radar: bool, img_hash: str) -> str:
    """Generates the unified 50/50 layout using Flexbox divs (bypasses GitHub table CSS)."""
    lines = [HHCERTS_START, ""]
    
    # Outer flex container: Aligns items in the middle, allows wrapping on mobile
    lines.append('<div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 30px;">')
    
    # --- LEFT SIDE (List) ---
    lines.append('<div style="flex: 1; min-width: 300px;">')
    
    # Header Row
    lines.append('<div style="display: flex; font-weight: 600; color: #57606a; border-bottom: 2px solid #d0d7de; padding-bottom: 8px; margin-bottom: 8px; font-size: 14px;">')
    lines.append('  <div style="flex: 2;">Competency</div>')
    lines.append('  <div style="flex: 1;">Level</div>')
    lines.append('  <div style="flex: 1;">PDF</div>')
    lines.append('</div>')

    if not certs:
        lines.append('<div style="padding: 20px 0; text-align: center; color: #57606a;">_No certificates yet._</div>')
    else:
        for c in certs:
            competency = c.get("competency") or "—"
            level = render_level(c.get("level"))
            file_link = f'<a href="./certificates/files/{c["file"]}">📄 PDF</a>' if c.get("file") else "—"
            
            # Data Row
            lines.append('<div style="display: flex; padding: 12px 0; border-bottom: 1px solid #d0d7de;">')
            lines.append(f'  <div style="flex: 2; font-weight: 600;">{competency}</div>')
            lines.append(f'  <div style="flex: 1;">{level}</div>')
            lines.append(f'  <div style="flex: 1;">{file_link}</div>')
            lines.append('</div>')
            
    lines.append('</div>') # End Left Side
    
    # --- RIGHT SIDE (Radar) ---
    lines.append('<div style="flex: 1; min-width: 300px; text-align: center;">')
    
    if has_radar:
        lines.append(f'  <img src="./certificates/radar.png?v={img_hash}" alt="Competency Radar" style="max-width: 100%; height: auto; display: block; margin: 0 auto;" />')
    else:
        lines.append('  <p style="color: #57606a;">_Radar chart requires at least 3 competencies._</p>')
        
    lines.append('</div>') # End Right Side
    
    lines.append('</div>') # End Outer Flex Container
    lines.append("")
    lines.append(HHCERTS_END)
    
    return "\n".join(lines)


def update_readme(block: str) -> bool:
    if not README.exists():
        README.write_text(block + "\n", encoding="utf-8")
        return True

    content = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(HHCERTS_START) + r".*?" + re.escape(HHCERTS_END), re.DOTALL)

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
    
    img_hash = get_file_hash(RADAR_IMG)
    
    block = render_block(certs, has_radar, img_hash)
    changed = update_readme(block)
    print("README updated." if changed else "README unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
