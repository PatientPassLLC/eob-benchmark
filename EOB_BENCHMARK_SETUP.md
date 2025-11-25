# EOB Benchmark Fixtures - Setup Guide

Internal benchmark suite for evaluating VLM OCR pipelines on dental EOB documents.

---

## Directory Structure

```
eob_fixtures/
├── README.md
├── requirements.txt
├── fixture_generator.py
├── benchmark_runner.py
├── sources/                    # Drop raw PDFs here
└── fixtures/
    └── eob_001/
        ├── original.pdf
        ├── manifest.json
        ├── pages/
        │   ├── page_1.png
        │   ├── page_1.md       # Ground truth (Gemini draft → manually verified)
        │   ├── page_1_tables.json
        │   ├── page_2.png
        │   ├── page_2.md
        │   └── page_2_tables.json
        └── full_document.md    # All pages combined
```

---

## Setup

```bash
mkdir eob_fixtures && cd eob_fixtures
mkdir -p sources fixtures

# Dependencies
pip install google-generativeai pdf2image Pillow teds-metric python-Levenshtein beautifulsoup4
```

**requirements.txt:**
```
google-generativeai>=0.8.0
pdf2image>=1.16.0
Pillow>=10.0.0
teds-metric>=1.0.0
python-Levenshtein>=0.25.0
beautifulsoup4>=4.12.0
```

---

## fixture_generator.py

```python
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
```

---

## Quick Start

1. **Add PDFs:**
   ```bash
   cp /path/to/your/eobs/*.pdf sources/
   ```

2. **Set API key:**
   ```bash
   export GOOGLE_API_KEY="your-key"
   ```

3. **Generate drafts:**
   ```bash
   python fixture_generator.py
   ```

4. **Review & verify each fixture:**
   - Open `fixtures/eob_001/pages/page_1.md`
   - Compare against `page_1.png`
   - Fix any errors in the markdown
   - Update `page_1_tables.json` if table structure changed
   - Set `"verified": true` in `manifest.json`

5. **Regenerate combined doc after edits:**
   ```bash
   # Manual: cat pages/*.md > full_document.md
   ```

---

## File Formats

**page_N.md** (ground truth):
```markdown
**Delta Dental of California**
Claim #: 12345678
Patient: John Smith

<table>
<tr><th>Date</th><th>Code</th><th>Billed</th><th>Allowed</th><th>Paid</th></tr>
<tr><td>01/15/25</td><td>D0120</td><td>45.00</td><td>38.00</td><td>38.00</td></tr>
</table>

Total: $38.00
```

**page_N_tables.json** (validation metadata):
```json
{
  "tables": [
    {"table_idx": 0, "row_count": 2, "column_count": 5}
  ]
}
```

**manifest.json**:
```json
{
  "eob_id": "eob_001",
  "source_file": "delta_dental_claim_123.pdf",
  "page_count": 3,
  "dpi": 200,
  "verified": true,
  "notes": "Multi-page claim, table spans pages 1-2"
}
```

---

## Verification Checklist

For each fixture, confirm:
- [ ] All prose text present
- [ ] All tables rendered as HTML
- [ ] Column count correct per row
- [ ] All rows present (no missing service lines)
- [ ] Dollar amounts exact
- [ ] Procedure codes exact
- [ ] `manifest.json` → `verified: true`

---

## Notes

- **200 DPI** is the standard for VLM benchmarks (DeepSeek, OmniDocBench)
- Gemini drafts are ~80-90% accurate—always verify manually
- Column schemas vary by payer—no fixed schema enforced
- Table metadata is for validation scoring, not content matching
