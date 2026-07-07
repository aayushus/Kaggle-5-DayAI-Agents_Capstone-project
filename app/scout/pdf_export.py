from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer


def _md_to_html(text: str) -> str:
    escaped = _escape(text)
    # 1. Inline code: `code` -> <font face="Courier">code</font>
    escaped = re.sub(r'`([^`\n]+)`', r'<font face="Courier">\1</font>', escaped)
    # 2. Bold: **bold** or __bold__ -> <b>bold</b>
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'__(.*?)__', r'<b>\1</b>', escaped)
    # 3. Italic: *italic* or _italic_ -> <i>italic</i>
    escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
    escaped = re.sub(r'_(.*?)_', r'<i>\1</i>', escaped)
    # 4. Links: [text](url) -> <a href="\2"><font color="blue"><u>text</u></font></a>
    escaped = re.sub(r'\[([^\]\n]+)\]\(([^)\n]+)\)', r'<a href="\2"><font color="blue"><u>\1</u></font></a>', escaped)
    return escaped


def write_market_pdf(markdown_text: str, pdf_path: str | Path) -> Path:
    target = Path(pdf_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(target),
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        title="Northstar Market Artifact",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "NorthstarBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )
    mono = ParagraphStyle(
        "NorthstarMono",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8.5,
        leading=11,
        spaceAfter=8,
    )
    h1 = ParagraphStyle("NorthstarH1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=12)
    h2 = ParagraphStyle("NorthstarH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=8, spaceAfter=8)
    h3 = ParagraphStyle("NorthstarH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=6, spaceAfter=6)

    story: list = []
    code_buffer: list[str] = []
    in_code = False
    for line in _lines(markdown_text):
        stripped = line.rstrip()
        if stripped.startswith("```"):
            if in_code and code_buffer:
                story.append(Preformatted("\n".join(code_buffer), mono))
                story.append(Spacer(1, 6))
                code_buffer = []
            in_code = not in_code
            continue
        if in_code:
            code_buffer.append(stripped)
            continue
        if not stripped:
            story.append(Spacer(1, 4))
            continue
        if stripped.startswith("# "):
            story.append(Paragraph(_md_to_html(stripped[2:]), h1))
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(_md_to_html(stripped[3:]), h2))
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(_md_to_html(stripped[4:]), h3))
            continue
        if stripped.startswith("- "):
            story.append(Paragraph(f"• {_md_to_html(stripped[2:])}", body))
            continue
        story.append(Paragraph(_md_to_html(stripped), body))
    if code_buffer:
        story.append(Preformatted("\n".join(code_buffer), mono))
    doc.build(story)
    return target


def _lines(text: str) -> Iterable[str]:
    return str(text or "").splitlines()


def _escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

