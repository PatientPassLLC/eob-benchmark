#!/usr/bin/env python3
"""
EOB Fixture Generator
Renders PDFs → PNGs, calls Gemini 2.5 Pro for draft ground truth.
"""

import os
import json
import re
from pathlib import Path
from pdf2image import convert_from_path
import google.generativeai as genai

# Config
DPI = 200
FIXTURES_DIR = Path("fixtures")
SOURCES_DIR = Path("sources")

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-pro-preview-05-06")

PROMPT = """Extract ALL text from this EOB page. Output as markdown with:
- All prose/headers as plain markdown
- ALL tables as HTML <table> with <tr>/<th>/<td> tags
- Preserve exact values (amounts, codes, dates)
- Include every row, every column

Output ONLY the markdown content, no explanations."""


def count_tables(md_content: str) -> list[dict]:
    """Parse HTML tables from markdown, return metadata."""
    tables = []
    pattern = r'<table>(.*?)</table>'
    for idx, match in enumerate(re.findall(pattern, md_content, re.DOTALL)):
        rows = re.findall(r'<tr>(.*?)</tr>', match, re.DOTALL)
        col_counts = []
        for row in rows:
            cells = len(re.findall(r'<t[hd]>', row))
            col_counts.append(cells)
        tables.append({
            "table_idx": idx,
            "row_count": len(rows),
            "column_count": max(col_counts) if col_counts else 0
        })
    return tables


def process_eob(pdf_name: str, eob_id: str):
    """Process single EOB PDF into fixture."""
    pdf_path = SOURCES_DIR / pdf_name
    eob_dir = FIXTURES_DIR / eob_id
    pages_dir = eob_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Copy original
    import shutil
    shutil.copy(pdf_path, eob_dir / "original.pdf")

    # Render pages
    images = convert_from_path(pdf_path, dpi=DPI)
    all_md = []

    for i, img in enumerate(images, 1):
        page_num = f"page_{i}"
        png_path = pages_dir / f"{page_num}.png"
        md_path = pages_dir / f"{page_num}.md"
        json_path = pages_dir / f"{page_num}_tables.json"

        # Save PNG
        img.save(png_path, "PNG")

        # Call Gemini
        print(f"  Processing {page_num}...")
        response = model.generate_content([PROMPT, img])
        md_content = response.text

        # Save draft markdown
        with open(md_path, "w") as f:
            f.write(md_content)

        # Generate table metadata
        tables_meta = {"tables": count_tables(md_content)}
        with open(json_path, "w") as f:
            json.dump(tables_meta, f, indent=2)

        all_md.append(f"<!-- Page {i} -->\n{md_content}")

    # Combine all pages
    with open(eob_dir / "full_document.md", "w") as f:
        f.write("\n\n---\n\n".join(all_md))

    # Create manifest
    manifest = {
        "eob_id": eob_id,
        "source_file": pdf_name,
        "page_count": len(images),
        "dpi": DPI,
        "verified": False,
        "notes": ""
    }
    with open(eob_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"✓ {eob_id} complete ({len(images)} pages)")


def main():
    """Process all PDFs in sources/ that don't have fixtures yet."""
    FIXTURES_DIR.mkdir(exist_ok=True)
    SOURCES_DIR.mkdir(exist_ok=True)

    existing = {d.name for d in FIXTURES_DIR.iterdir() if d.is_dir()}

    for i, pdf in enumerate(sorted(SOURCES_DIR.glob("*.pdf")), 1):
        eob_id = f"eob_{i:03d}"
        if eob_id in existing:
            print(f"Skipping {eob_id} (exists)")
            continue
        print(f"Processing {pdf.name} → {eob_id}")
        process_eob(pdf.name, eob_id)


if __name__ == "__main__":
    main()
