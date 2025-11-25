# EOB Benchmark Suite

Standardized benchmarking framework for evaluating OCR pipeline accuracy on Explanation of Benefits (EOB) documents.

## Purpose

This benchmark suite serves as the **source of truth** for comparing different OCR pipelines (DeepSeek, FastVLM, OlmOCR, etc.) against verified ground truth extractions.

## Directory Structure

```
eob-benchmark/
├── README.md                    # This file
├── EOB_BENCHMARK_SETUP.md       # Detailed setup instructions
├── EOB_BENCHMARK_ONGOING.md     # Usage guide and scoring methodology
├── requirements.txt
├── fixture_generator.py         # Generates fixtures from PDFs
├── benchmark_runner.py          # Scores model outputs
├── sources/                     # Drop raw EOB PDFs here
└── fixtures/
    └── eob_001/
        ├── original.pdf
        ├── manifest.json
        ├── pages/
        │   ├── page_1.png       # Rendered @ 200 DPI
        │   ├── page_1.md        # Ground truth (verified)
        │   ├── page_1_tables.json
        │   └── ...
        └── full_document.md
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API Key

```bash
export GOOGLE_API_KEY="your-gemini-api-key"
```

### 3. Add EOB PDFs

```bash
cp /path/to/your/eobs/*.pdf sources/
```

### 4. Generate Fixtures

```bash
python fixture_generator.py
```

This creates draft ground truth using Gemini 2.5 Pro.

### 5. Verify Ground Truth

For each fixture:
- Open `fixtures/eob_001/pages/page_1.md`
- Compare against `page_1.png`
- Fix any extraction errors
- Update `page_1_tables.json` if table structure changed
- Set `"verified": true` in `manifest.json`

### 6. Run Benchmarks

Process your PDFs with any pipeline, then score:

```bash
# Example: DeepSeek pipeline output
python benchmark_runner.py outputs/deepseek "DeepSeek-OCR"

# Example: FastVLM pipeline output
python benchmark_runner.py outputs/fastvlm "FastVLM"
```

## Scoring Methodology

**Weighted composite score:**
- **70% TEDS** (Table Edit Distance Similarity) - catches column drift
- **30% Text Similarity** (Levenshtein ratio) - prose accuracy

**Alert threshold:** <85% composite score

See `EOB_BENCHMARK_ONGOING.md` for detailed scoring methodology.

## Expected Output Format

Your pipeline must output markdown files in this structure:

```
outputs/
  your_pipeline_name/
    eob_001/
      pages/
        page_1.md
        page_2.md
        ...
    eob_002/
      pages/
        page_1.md
        ...
```

Each `page_N.md` should contain:
- Plain text for prose
- HTML `<table>` tags with `<tr>/<th>/<td>` for tables
- Exact values (amounts, dates, codes)

## Benchmark Reports

Example output:

```
BENCHMARK REPORT: DeepSeek-OCR
============================================
eob_001: 94.2% ✓
eob_002: 87.1% ⚠️ ALERT
  └─ page_2: TEDS=78.3%, Text=92.1%
eob_003: 96.5% ✓

OVERALL: 92.6%
Alerts: 1/20 pages
```

## Score Interpretation

| Score | Status | Action |
|-------|--------|--------|
| ≥95% | Excellent | Production ready |
| 90-95% | Good | Minor issues, review edge cases |
| 85-90% | Acceptable | Some manual QA needed |
| <85% | **ALERT** | Investigate before production |

## Integration with Pipelines

### EOB-KILL3R-FastVLM

Already outputs compatible format. Just strip hexline prefixes:

```python
import re
def strip_hexlines(md: str) -> str:
    return re.sub(r'^0x[0-9A-F]+:\s*', '', md, flags=re.MULTILINE)
```

### EOB-KILL3R-DEEPSEEK

Extract per-page markdown from hexline output using line ranges from `response["pages"]`.

### Custom Pipelines

Ensure output matches the format:
- Tables as HTML with proper tags
- Prose as plain markdown
- Exact value preservation

## Adding More Fixtures

1. Add PDF to `sources/`
2. Run `python fixture_generator.py`
3. Verify the generated fixture manually
4. Mark as verified in `manifest.json`

**Target:** 30+ fixtures covering different payers and edge cases.

## Documentation

- **Setup Guide:** `EOB_BENCHMARK_SETUP.md`
- **Usage & Scoring:** `EOB_BENCHMARK_ONGOING.md`

## Notes

- 200 DPI rendering matches industry standards (DeepSeek, OmniDocBench)
- Gemini drafts are ~80-90% accurate - always verify manually
- Column drift (values in wrong columns) is the critical failure mode
- TEDS catches structural errors aggressively
- No fixed schema - works across all payers
