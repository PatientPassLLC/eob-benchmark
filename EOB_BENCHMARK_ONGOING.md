# EOB Benchmark - Adding Fixtures & Scoring

How to expand the benchmark and measure model performance.

---

## Adding New EOBs

1. **Drop PDF in sources:**
   ```bash
   cp new_eob.pdf sources/
   ```

2. **Run generator:**
   ```bash
   python fixture_generator.py
   ```
   Creates next sequential ID (`eob_011`, `eob_012`, etc.)

3. **Verify the fixture:**
   - Review each `page_N.md` against `page_N.png`
   - Fix extraction errors
   - Update `page_N_tables.json` if you changed table structure
   - Set `verified: true` in `manifest.json`

4. **Naming convention (optional):**
   Add payer info to manifest notes:
   ```json
   {"notes": "Delta Dental CA, complex multi-page"}
   ```

---

## Scoring Methodology

We use **two metrics** weighted differently:

| Metric | Weight | What It Measures |
|--------|--------|------------------|
| **TEDS** (Table Edit Distance Similarity) | 70% | Table structure accuracy |
| **Text Similarity** | 30% | Prose/non-table content |

### Why This Weighting

Your pipeline's critical failure mode is **column drift**—values landing in wrong columns. TEDS catches this aggressively because it treats HTML tables as trees and penalizes structural mismatches. Text similarity matters less because minor prose differences don't break downstream LLM ingestion.

---

## TEDS (Tree Edit Distance Similarity)

Industry-standard metric for table structure evaluation. Converts HTML tables to trees, computes minimum edit operations to transform prediction → ground truth.

**Score range:** 0.0 (completely wrong) → 1.0 (perfect match)

**What it catches:**
- Missing/extra rows
- Missing/extra columns
- Column misalignment (your main concern)
- Cell content errors

```python
from teds import TEDS

teds = TEDS(structure_only=False)  # Include content matching
score = teds.evaluate(pred_html, gt_html)
# Returns 0.0-1.0
```

**Structure-only mode:** Set `structure_only=True` to ignore cell content, only check row/column alignment. Useful for "did columns drift?" without penalizing OCR typos.

---

## Text Similarity

For non-table prose, we use **Normalized Edit Distance**:

```python
from Levenshtein import ratio

def text_similarity(pred: str, gt: str) -> float:
    return ratio(pred.strip(), gt.strip())
```

**Score range:** 0.0 (nothing matches) → 1.0 (identical)

Alternative: **Cosine similarity** via embeddings if you want semantic matching (catches synonyms). But for EOBs, exact matching matters more.

---

## benchmark_runner.py

```python
"""
Run VLM output against fixtures, compute scores.
"""

import json
import re
from pathlib import Path
from teds import TEDS
from Levenshtein import ratio
from bs4 import BeautifulSoup

FIXTURES_DIR = Path("fixtures")
TEDS_WEIGHT = 0.70
TEXT_WEIGHT = 0.30
ALERT_THRESHOLD = 0.85  # Flag anything below this


def extract_tables(md: str) -> list[str]:
    """Extract HTML tables from markdown."""
    return re.findall(r'<table>.*?</table>', md, re.DOTALL)


def extract_prose(md: str) -> str:
    """Extract non-table text."""
    prose = re.sub(r'<table>.*?</table>', '', md, flags=re.DOTALL)
    return re.sub(r'\s+', ' ', prose).strip()


def score_page(pred_md: str, gt_md: str, tables_meta: dict) -> dict:
    """Score single page extraction against ground truth."""
    
    pred_tables = extract_tables(pred_md)
    gt_tables = extract_tables(gt_md)
    
    # TEDS scoring
    teds = TEDS(structure_only=False)
    table_scores = []
    
    for i, (pred_t, gt_t) in enumerate(zip(pred_tables, gt_tables)):
        score = teds.evaluate(pred_t, gt_t)
        expected_cols = tables_meta["tables"][i]["column_count"] if i < len(tables_meta["tables"]) else None
        table_scores.append({
            "table_idx": i,
            "teds_score": score,
            "expected_columns": expected_cols
        })
    
    # Column alignment check (structure only)
    teds_struct = TEDS(structure_only=True)
    struct_scores = [teds_struct.evaluate(p, g) for p, g in zip(pred_tables, gt_tables)]
    
    # Text similarity
    pred_prose = extract_prose(pred_md)
    gt_prose = extract_prose(gt_md)
    text_score = ratio(pred_prose, gt_prose)
    
    # Weighted composite
    avg_teds = sum(t["teds_score"] for t in table_scores) / len(table_scores) if table_scores else 1.0
    composite = (avg_teds * TEDS_WEIGHT) + (text_score * TEXT_WEIGHT)
    
    return {
        "table_scores": table_scores,
        "structure_scores": struct_scores,
        "text_score": text_score,
        "composite_score": composite,
        "alert": composite < ALERT_THRESHOLD
    }


def run_benchmark(model_output_dir: Path) -> dict:
    """
    Run benchmark against all verified fixtures.
    
    Expects model_output_dir to contain:
      eob_001/pages/page_1.md, page_2.md, ...
    """
    results = {}
    
    for fixture_dir in sorted(FIXTURES_DIR.iterdir()):
        manifest_path = fixture_dir / "manifest.json"
        if not manifest_path.exists():
            continue
            
        manifest = json.loads(manifest_path.read_text())
        if not manifest.get("verified"):
            print(f"Skipping {fixture_dir.name} (not verified)")
            continue
        
        eob_id = fixture_dir.name
        eob_results = {"pages": [], "alerts": []}
        
        for page_md in sorted((fixture_dir / "pages").glob("page_*.md")):
            if "_tables" in page_md.name:
                continue
                
            page_name = page_md.stem
            gt_md = page_md.read_text()
            tables_json = page_md.with_name(f"{page_name}_tables.json")
            tables_meta = json.loads(tables_json.read_text()) if tables_json.exists() else {"tables": []}
            
            # Load model output
            model_page = model_output_dir / eob_id / "pages" / page_md.name
            if not model_page.exists():
                print(f"  Missing: {model_page}")
                continue
            pred_md = model_page.read_text()
            
            # Score
            page_result = score_page(pred_md, gt_md, tables_meta)
            page_result["page"] = page_name
            eob_results["pages"].append(page_result)
            
            if page_result["alert"]:
                eob_results["alerts"].append(page_name)
        
        # EOB-level composite
        if eob_results["pages"]:
            eob_results["composite"] = sum(p["composite_score"] for p in eob_results["pages"]) / len(eob_results["pages"])
        
        results[eob_id] = eob_results
    
    return results


def print_report(results: dict, model_name: str):
    """Print human-readable benchmark report."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK REPORT: {model_name}")
    print(f"{'='*60}\n")
    
    all_composites = []
    all_alerts = []
    
    for eob_id, data in results.items():
        composite = data.get("composite", 0)
        all_composites.append(composite)
        status = "⚠️ ALERT" if data["alerts"] else "✓"
        print(f"{eob_id}: {composite:.1%} {status}")
        
        if data["alerts"]:
            all_alerts.extend([f"{eob_id}/{p}" for p in data["alerts"]])
            for page in data["pages"]:
                if page["alert"]:
                    print(f"  └─ {page['page']}: TEDS={page['table_scores'][0]['teds_score']:.1%}, Text={page['text_score']:.1%}")
    
    print(f"\n{'─'*60}")
    print(f"OVERALL: {sum(all_composites)/len(all_composites):.1%}")
    print(f"Alerts: {len(all_alerts)}/{sum(len(r['pages']) for r in results.values())} pages")
    
    if all_alerts:
        print(f"\nPages requiring review:")
        for alert in all_alerts:
            print(f"  - {alert}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python benchmark_runner.py <model_output_dir> <model_name>")
        print("Example: python benchmark_runner.py ./outputs/deepseek 'DeepSeek-OCR'")
        sys.exit(1)
    
    results = run_benchmark(Path(sys.argv[1]))
    print_report(results, sys.argv[2])
```

---

## Running Benchmarks

1. **Run your VLM pipeline** on all fixture PDFs, output to a directory:
   ```
   outputs/
     deepseek/
       eob_001/pages/page_1.md, page_2.md...
       eob_002/pages/...
     olmocr/
       eob_001/pages/...
   ```

2. **Score:**
   ```bash
   python benchmark_runner.py outputs/deepseek "DeepSeek-OCR"
   python benchmark_runner.py outputs/olmocr "olmOCR-2"
   ```

3. **Compare:**
   ```
   BENCHMARK REPORT: DeepSeek-OCR
   ========================================
   eob_001: 94.2% ✓
   eob_002: 87.1% ⚠️ ALERT
     └─ page_2: TEDS=78.3%, Text=92.1%
   
   OVERALL: 91.6%
   Alerts: 1/20 pages
   ```

---

## Alert Thresholds

| Score | Interpretation |
|-------|----------------|
| ≥95%  | Excellent—production ready |
| 90-95%| Good—minor issues, review edge cases |
| 85-90%| Acceptable—some manual QA needed |
| <85%  | **ALERT**—investigate before production |

Adjust `ALERT_THRESHOLD` in `benchmark_runner.py` based on your tolerance.

---

## Interpreting Results

**High TEDS, Low Text:** Table structure correct, some prose OCR errors. Usually acceptable.

**Low TEDS, High Text:** Column drift or missing rows. **This is your critical failure mode.** Investigate immediately.

**Both Low:** Major extraction failure. Check if page rendered correctly, or if it's an unusual format.

---

## Quick Commands

```bash
# Add new EOB
cp new.pdf sources/ && python fixture_generator.py

# Run single model benchmark
python benchmark_runner.py outputs/deepseek "DeepSeek-OCR"

# Compare all models (bash loop)
for model in deepseek olmocr paddle; do
  python benchmark_runner.py outputs/$model "$model"
done
```

---

## Expanding to 30+ EOBs

Once you have 10 verified fixtures working:
1. Prioritize **different payers** for coverage
2. Include **worst-case** documents (faded, skewed, complex tables)
3. Add **edge cases**: multi-page tables, merged cells, handwritten notes
4. Target: 1-2 fixtures per payer you process in production
