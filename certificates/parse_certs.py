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

    # Modern, transparent setup
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    # GitHub-native colors
    line_color = '#0969da'  # GitHub Blue
    text_color = '#24292f'  # GitHub Text
    grid_color = '#d0d7de'  # GitHub Border

    # Plot
    ax.plot(angles, stats, color=line_color, linewidth=2.5, zorder=3)
    ax.fill(angles, stats, color=line_color, alpha=0.15, zorder=2)
    # Crisp dots with white borders
    ax.scatter(angles[:-1], stats[:-1], color=line_color, s=50, zorder=4, edgecolors='white', linewidth=1.5)

    # Clean aesthetics
    ax.spines['polar'].set_visible(False)
    ax.grid(color=grid_color, linestyle='--', linewidth=1, alpha=0.8)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=12, color=text_color, fontweight='bold')
    ax.tick_params(axis='x', pad=15)

    ax.set_ylim(0, y_limit)
    ax.set_yticks(ticks)
    ax.set_yticklabels(tick_labels, color='#57606a', size=10)
    ax.set_rlabel_position(45)

    RADAR_IMG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(RADAR_IMG, bbox_inches='tight', dpi=200, transparent=True, pad_inches=0)
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
    """Generates the unified 50/50 layout using pure HTML to avoid Markdown parsing bugs."""
    
    # HTML structure that mimics native markdown tables to prevent GitHub CSS interference
    html = [HHCERTS_START, ""]
    
    html.append('<table style="border: none; width: 100%; border-collapse: collapse;">')
    html.append('  <tr style="border: none; background-color: transparent;">')
    
    # Left column (Table)
    html.append('    <td width="50%" valign="middle" style="border: none; padding: 0 20px 0 0;">')
    html.append('      <table style="border: none; width: 100%; border-collapse: collapse;">')
    html.append('        <thead>')
    html.append('          <tr style="border: none;">')
    html.append('            <th align="left" style="border: none; border-bottom: 1px solid #d0d7de; padding: 8px 16px; font-weight: 600;">Competency</th>')
    html.append('            <th align="left" style="border: none; border-bottom: 1px solid #d0d7de; padding: 8px 16px; font-weight: 600;">Level</th>')
    html.append('            <th align="left" style="border: none; border-bottom: 1px solid #d0d7de; padding: 8px 16px; font-weight: 600;">PDF</th>')
    html.append('          </tr>')
    html.append('        </thead>')
    html.append('        <tbody>')

    if not certs:
        html.append('          <tr style="border: none;"><td colspan="3" align="center" style="border: none; border-bottom: 1px solid #d0d7de; padding: 16px;">_No certificates yet._</td></tr>')
    else:
        for c in certs:
            competency = c.get("competency") or "—"
            level = render_level(c.get("level"))
            file_link = f'<a href="./certificates/files/{c["file"]}">📄 PDF</a>' if c.get("file") else "—"
            
            html.append('          <tr style="border: none; background-color: transparent;">')
            html.append(f'            <td align="left" style="border: none; border-bottom: 1px solid #d0d7de; padding: 10px 16px;"><b>{competency}</b></td>')
            html.append(f'            <td align="left" style="border: none; border-bottom: 1px solid #d0d7de; padding: 10px 16px;">{level}</td>')
            html.append(f'            <td align="left" style="border: none; border-bottom: 1px solid #d0d7de; padding: 10px 16px;">{file_link}</td>')
            html.append('          </tr>')

    html.append('        </tbody>')
    html.append('      </table>')
    html.append('    </td>')
    
    # Right column (Image)
    html.append('    <td width="50%" valign="middle" align="center" style="border: none; padding: 0;">')
    
    if has_radar:
        html.append(f'      <img src="./certificates/radar.png?v={img_hash}" alt="Competency Radar" style="max-width: 100%; height: auto;" />')
    else:
        html.append('      <p style="color: #57606a; text-align: center;">_Radar chart requires at least 3 competencies._</p>')
        
    html.append('    </td>')
    html.append('  </tr>')
    html.append('</table>')
    html.append("")
    html.append(HHCERTS_END)
    
    return "\n".join(html)


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
