#!/usr/bin/env python3
"""
Flatten Gemini's complex HTML tables into VLM-realistic simple tables.
"""
import re
from pathlib import Path

STANDARD_HEADER = '<tr><th>Service</th><th>AMOUNT YOU CHARGED ($)</th><th>YOUR CONTRACTED AMOUNT ($)</th><th>AMOUNT ELIGIBLE FOR COVERAGE BY THE PLAN ($)</th><th>PATIENT COPAY/ DEDUCTIBLE ($)</th><th>REMAINING BALANCE ($)</th><th>PATIENT COINSURANCE ($)</th><th>THE PLAN COVERED (%)</th><th>THE PLAN COVERED ($)</th></tr>'

def flatten_table(table_html: str) -> str:
    """Convert complex table to flat VLM-style table."""
    # Extract all rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    
    output_rows = [STANDARD_HEADER]
    
    pending_service = None
    
    for row in rows:
        row_clean = row.strip()
        
        # Skip header rows
        if re.search(r'<th[^>]*rowspan', row, re.IGNORECASE):
            continue
        if re.search(r'<th>\s*\(%\)', row, re.IGNORECASE):
            continue
        if re.search(r'AMOUNT YOU CHARGED', row, re.IGNORECASE) and '<th' in row.lower():
            continue
            
        # Check if this is a "For service on" row (colspan or first cell with description)
        service_match = re.search(r'For service on[^<]+', row, re.IGNORECASE)
        if service_match:
            # Extract service description
            pending_service = service_match.group(0).strip()
            pending_service = pending_service.replace('For service on ', '')
            continue
        
        # Extract data cells
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        
        if not cells:
            continue
            
        # Clean cells
        clean_cells = []
        for cell in cells:
            cell = re.sub(r'<[^>]+>', '', cell).strip()  # Remove HTML
            cell = re.sub(r'\*\*', '', cell)  # Remove bold
            clean_cells.append(cell)
        
        # Skip rows where first cell is empty or all cells empty
        non_empty = [c for c in clean_cells if c]
        if not non_empty:
            continue
        
        # Skip rows that are just headers again
        if clean_cells and any('AMOUNT' in c.upper() for c in clean_cells[:3] if c):
            continue
            
        # If first cell is empty but we have pending service, combine them
        if clean_cells[0] == '' and pending_service:
            # Data row following service description
            data_cells = [c for c in clean_cells if c]  # Remove empty cells
            output_rows.append(f'<tr><td>{pending_service}</td>' + ''.join(f'<td>{c}</td>' for c in data_cells) + '</tr>')
            pending_service = None
        elif clean_cells[0].startswith('$') or (clean_cells[0] == '' and len(non_empty) > 3):
            # Totals row (starts with $ or is a summary row)
            data_cells = [c for c in clean_cells if c]
            output_rows.append(f'<tr><td>TOTALS</td>' + ''.join(f'<td>{c}</td>' for c in data_cells) + '</tr>')
        elif pending_service:
            # Service was pending, this row has data
            output_rows.append(f'<tr><td>{pending_service}</td>' + ''.join(f'<td>{c}</td>' for c in clean_cells) + '</tr>')
            pending_service = None
        elif clean_cells[0] and not clean_cells[0].startswith('For'):
            # Direct row with data
            output_rows.append('<tr>' + ''.join(f'<td>{c}</td>' for c in clean_cells) + '</tr>')
    
    return '<table>\n' + '\n'.join(output_rows) + '\n</table>'


def clean_markdown(content: str) -> str:
    """Remove markdown formatting, keep plain text."""
    content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
    content = re.sub(r'^###?\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\*\s+', '', content, flags=re.MULTILINE)
    content = re.sub(r'<br\s*/?>', ' ', content)
    return content


def process_page(content: str) -> str:
    """Process a single page's raw markdown."""
    content = clean_markdown(content)
    
    def replace_table(match):
        table = match.group(0)
        # Skip small summary tables
        if 'Amount paid by the plan' in table:
            # Simple 2-row table, keep as is but clean
            return re.sub(r'<th>Service</th>.*?</tr>\n?', '', table)
        return flatten_table(table)
    
    content = re.sub(r'<table>.*?</table>', replace_table, content, flags=re.DOTALL | re.IGNORECASE)
    
    return content


def main():
    pages_dir = Path("pages")
    
    for page_file in sorted(pages_dir.glob("page_*_raw.md")):
        page_num = int(re.search(r'page_(\d+)', page_file.name).group(1))
        # Process all pages now
        print(f"Processing {page_file.name}...")
        content = page_file.read_text()
        cleaned = process_page(content)
        page_file.write_text(cleaned)
        print(f"  ✓ Cleaned")


if __name__ == "__main__":
    main()
