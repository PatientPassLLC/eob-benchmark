#!/usr/bin/env python3
"""
Regenerate ground_truth.json from cleaned page files.
"""
import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class CoordinateEntry:
    content: str
    page_num: int
    bbox_px: Optional[str]
    block_type: str


@dataclass  
class TableMeta:
    table_idx: int
    bbox_px: Optional[str]
    rows: int
    cols: int
    headers: list
    validation: str
    source: str


@dataclass
class PageResult:
    page_num: int
    tables: list
    line_range: list
    validation: str
    confidence: float


def parse_table_html(table_html: str) -> dict:
    """Extract metadata from HTML table."""
    rows = re.findall(r'<tr>(.*?)</tr>', table_html, re.DOTALL)
    
    headers = []
    col_counts = []
    
    for row in rows:
        th_cells = re.findall(r'<th[^>]*>(.*?)</th>', row, re.DOTALL)
        td_cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        
        if th_cells and not headers:
            headers = [cell.strip() for cell in th_cells]
        
        col_counts.append(len(th_cells) + len(td_cells))
    
    return {
        "rows": len(rows),
        "cols": max(col_counts) if col_counts else 0,
        "headers": headers
    }


def add_hex_line_numbers(content: str, start_idx: int, page_num: int):
    """Add hex line numbers to content."""
    lines = content.strip().split('\n')
    numbered_lines = []
    coordinate_map = {}
    
    idx = start_idx
    in_table = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        hex_id = f"0x{idx:04X}"
        
        if '<table>' in line.lower():
            block_type = "table_start"
            in_table = True
        elif '</table>' in line.lower():
            block_type = "table_end"
            in_table = False
        elif in_table and '<th' in line.lower():
            block_type = "table_header"
        elif in_table and '<tr' in line.lower():
            block_type = "table_row"
        else:
            block_type = "text"
        
        numbered_lines.append(f"{hex_id}: {line}")
        coordinate_map[hex_id] = CoordinateEntry(
            content=line,
            page_num=page_num,
            bbox_px=None,
            block_type=block_type
        )
        
        idx += 1
    
    return '\n'.join(numbered_lines), coordinate_map, idx


def extract_tables_with_metadata(content: str) -> list:
    """Extract all tables from content with full metadata."""
    tables = []
    pattern = r'<table>(.*?)</table>'
    
    for idx, match in enumerate(re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)):
        table_html = f"<table>{match.group(1)}</table>"
        meta = parse_table_html(table_html)
        
        tables.append(TableMeta(
            table_idx=idx,
            bbox_px=None,
            rows=meta["rows"],
            cols=meta["cols"],
            headers=meta["headers"],
            validation="OK",
            source="gemini-2.5-pro"
        ))
    
    return tables


def main():
    pages_dir = Path("pages")
    
    all_markdown_lines = []
    all_coordinate_map = {}
    pages_result = []
    line_idx = 1
    
    # Process each page
    for page_file in sorted(pages_dir.glob("page_*_raw.md"), key=lambda x: int(re.search(r'page_(\d+)', x.name).group(1))):
        page_num = int(re.search(r'page_(\d+)', page_file.name).group(1))
        print(f"Processing page {page_num}...")
        
        content = page_file.read_text()
        
        # Add hex line numbers
        start_line_idx = line_idx
        numbered_content, page_coords, line_idx = add_hex_line_numbers(content, line_idx, page_num)
        
        # Add to coordinate map
        for hex_id, entry in page_coords.items():
            all_coordinate_map[hex_id] = entry
        
        # Extract table metadata
        tables = extract_tables_with_metadata(content)
        
        # Line range
        end_line_idx = line_idx - 1
        line_range = [f"0x{start_line_idx:04X}", f"0x{end_line_idx:04X}"]
        
        pages_result.append(PageResult(
            page_num=page_num,
            tables=tables,
            line_range=line_range,
            validation="OK",
            confidence=0.95
        ))
        
        all_markdown_lines.append(numbered_content)
        
        # Save page-level ground truth
        page_gt = {
            "page_num": page_num,
            "markdown": numbered_content,
            "tables": [asdict(t) for t in tables],
            "line_range": line_range,
            "coordinate_map": {k: asdict(v) for k, v in page_coords.items()}
        }
        with open(pages_dir / f"page_{page_num}_ground_truth.json", "w") as f:
            json.dump(page_gt, f, indent=2)
    
    # Build full document
    full_output = {
        "success": True,
        "document_id": "eob_001",
        "page_count": len(pages_result),
        "processing_time_ms": 0,
        "markdown": '\n'.join(all_markdown_lines),
        "pages": [asdict(p) for p in pages_result],
        "coordinate_map": {k: asdict(v) for k, v in all_coordinate_map.items()},
        "alerts": [],
        "confidence": 0.95,
        "error": None
    }
    
    # Save
    with open("ground_truth.json", "w") as f:
        json.dump(full_output, f, indent=2)
    
    # Save full document markdown
    with open("full_document.md", "w") as f:
        f.write('\n\n---\n\n'.join(all_markdown_lines))
    
    print(f"\n✓ Generated ground_truth.json ({line_idx-1} lines)")


if __name__ == "__main__":
    main()

