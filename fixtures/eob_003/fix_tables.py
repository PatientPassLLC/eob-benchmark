#!/usr/bin/env python3
"""
Fix table format: merge service description rows with data rows.
"""
import re
from pathlib import Path

def fix_table(table_content: str) -> str:
    """Merge service description rows with their data rows."""
    lines = table_content.strip().split('\n')
    output_lines = []
    
    pending_service = None
    
    for line in lines:
        line = line.strip()
        
        # Keep header row as-is
        if '<th>' in line:
            output_lines.append(line)
            continue
        
        # Skip table tags
        if line in ['<table>', '</table>']:
            continue
        
        # Check if this is a service description row (has "For service on" or service desc, rest empty)
        service_match = re.search(r'<td>([^<]*(?:D\d{4}|service on)[^<]*)</td>(?:<td></td>)+', line, re.IGNORECASE)
        if service_match:
            pending_service = service_match.group(1).strip()
            # Clean up the service description
            pending_service = re.sub(r'^For service on\s*', '', pending_service)
            continue
        
        # Check if this is a data row (first cell empty, rest have data)
        if re.match(r'<tr><td></td><td>\d', line):
            # This is a data row - extract data cells
            cells = re.findall(r'<td>([^<]*)</td>', line)
            if pending_service and cells:
                # Combine service with data
                data = '</td><td>'.join(cells[1:])  # Skip first empty cell
                output_lines.append(f'<tr><td>{pending_service}</td><td>{data}</td></tr>')
                pending_service = None
                continue
        
        # Check for totals row
        if '<td>$' in line or '<td>TOTALS' in line:
            cells = re.findall(r'<td>([^<]*)</td>', line)
            non_empty = [c for c in cells if c]
            if non_empty and non_empty[0].startswith('$'):
                data = '</td><td>'.join(non_empty)
                output_lines.append(f'<tr><td>TOTALS</td><td>{data}</td></tr>')
                continue
        
        # Keep other rows as-is
        if line and '<tr>' in line:
            output_lines.append(line)
    
    return '<table>\n' + '\n'.join(output_lines) + '\n</table>'


def process_file(filepath: Path):
    """Process a single file."""
    content = filepath.read_text()
    
    # Find all tables and fix them
    def replace_table(match):
        table = match.group(0)
        # Skip small summary tables (Amount paid by plan)
        if 'Amount paid by the plan' in table or 'Customer' in table:
            return table
        return fix_table(table)
    
    new_content = re.sub(r'<table>.*?</table>', replace_table, content, flags=re.DOTALL)
    filepath.write_text(new_content)


def main():
    pages_dir = Path("pages")
    
    for f in sorted(pages_dir.glob("page_*_raw.md")):
        page_num = int(re.search(r'page_(\d+)', f.name).group(1))
        if page_num <= 4:
            print(f"Skipping {f.name} (already good)")
            continue
        print(f"Fixing {f.name}...")
        process_file(f)
        print(f"  ✓ Fixed")


if __name__ == "__main__":
    main()

