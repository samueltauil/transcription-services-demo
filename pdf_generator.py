"""
Professional Clinical Summary PDF Generator
Enterprise-grade PDF report generation for healthcare transcription summaries

This module provides clean, reliable PDF generation using fpdf2 with:
- Professional healthcare-appropriate styling
- Clean typography and consistent spacing
- Robust error handling
- Simple markdown parsing that works reliably
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, List
from fpdf import FPDF

logger = logging.getLogger(__name__)


class ClinicalReportPDF(FPDF):
    """
    Enterprise-grade PDF generator for clinical summaries.
    Uses a clean, professional design suitable for healthcare documentation.
    """
    
    def __init__(self, metadata: Optional[Dict] = None):
        super().__init__()
        self.metadata = metadata or {}
        
        # Page setup
        self.set_margins(left=20, top=30, right=20)
        self.set_auto_page_break(auto=True, margin=25)
        
        # Professional color palette
        self.COLOR_PRIMARY = (0, 82, 147)      # Professional blue
        self.COLOR_SECONDARY = (55, 55, 55)    # Dark gray for body text
        self.COLOR_LIGHT = (120, 120, 120)     # Light gray for metadata
        self.COLOR_ACCENT = (0, 150, 136)      # Teal accent
        self.COLOR_BG_LIGHT = (248, 249, 250)  # Light background
        self.COLOR_BORDER = (222, 226, 230)    # Border gray
        
    def header(self):
        """Professional header with branding"""
        # Top accent line
        self.set_draw_color(*self.COLOR_PRIMARY)
        self.set_line_width(1)
        self.line(10, 10, 200, 10)
        
        # Report title
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(*self.COLOR_PRIMARY)
        self.set_xy(20, 14)
        self.cell(0, 8, 'Clinical Summary Report', align='L')
        
        # Source file info
        if self.metadata.get('filename'):
            self.set_font('Helvetica', '', 9)
            self.set_text_color(*self.COLOR_LIGHT)
            self.set_xy(20, 22)
            filename = self.metadata['filename']
            if len(filename) > 60:
                filename = filename[:57] + '...'
            self.cell(0, 5, f'Source: {filename}', align='L')
        
        # Reset position for content
        self.set_y(32)
        
    def footer(self):
        """Professional footer with page numbers and confidentiality notice"""
        self.set_y(-20)
        
        # Footer separator line
        self.set_draw_color(*self.COLOR_BORDER)
        self.set_line_width(0.3)
        self.line(20, self.get_y(), 190, self.get_y())
        
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*self.COLOR_LIGHT)
        
        # Left: Timestamp
        self.set_xy(20, -15)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        self.cell(60, 10, f'Generated: {timestamp}', align='L')
        
        # Center: Confidentiality notice
        self.set_xy(80, -15)
        self.cell(50, 10, 'CONFIDENTIAL', align='C')
        
        # Right: Page number
        self.set_xy(140, -15)
        self.cell(50, 10, f'Page {self.page_no()} of {{nb}}', align='R')


def parse_summary_content(text: str) -> List[Dict]:
    """
    Parse markdown content into structured elements.
    Designed for reliability with clinical summary format.
    Handles:
    - Headers (# ## ### ####)
    - Tables (|col|col|)
    - Bullets (- item, * item, + item)
    - Nested/indented bullets (  - item)
    - Numbered items (1. item, 1) item)
    - Bold labels (**Label:** value)
    - Bold labels with content on following lines
    - Plain paragraphs
    """
    elements = []
    lines = text.split('\n')
    i = 0
    
    logger.info(f"Parsing {len(lines)} lines of text")
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            i += 1
            continue
        
        # Headers: ## Header Text (also handle ### 1. Header format)
        header_match = re.match(r'^(#{1,4})\s+(?:\d+\.\s*)?(.+)$', stripped)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()
            elements.append({
                'type': 'header',
                'level': level,
                'text': header_text
            })
            logger.debug(f"Found header level {level}: {header_text[:40]}")
            i += 1
            continue
        
        # Tables: Lines starting with |
        if stripped.startswith('|') and '|' in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            
            table_data = _parse_table(table_lines)
            if table_data:
                elements.append({
                    'type': 'table',
                    'headers': table_data['headers'],
                    'rows': table_data['rows']
                })
                logger.debug(f"Found table with {len(table_data['headers'])} cols, {len(table_data['rows'])} rows")
            continue
        
        # Bullet points: - Item or * Item (including indented)
        # Match lines starting with optional whitespace, then -, *, or +
        bullet_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if bullet_match:
            indent = len(bullet_match.group(1))
            bullet_text = bullet_match.group(2).strip()
            elements.append({
                'type': 'bullet',
                'text': bullet_text,
                'indent': indent
            })
            logger.debug(f"Found bullet (indent {indent}): {bullet_text[:40]}")
            i += 1
            continue
        
        # Numbered items: 1. Item or 1) Item
        num_match = re.match(r'^(\d+)[.)]\s+(.+)$', stripped)
        if num_match:
            elements.append({
                'type': 'numbered',
                'number': num_match.group(1),
                'text': num_match.group(2).strip()
            })
            i += 1
            continue
        
        # Bold label lines: **Label:** Value or **Label**
        # This could have content on the same line or following lines
        bold_match = re.match(r'^\*\*([^*]+)\*\*:?\s*(.*)$', stripped)
        if bold_match:
            label = bold_match.group(1).strip()
            value = bold_match.group(2).strip() if bold_match.group(2) else ''
            
            # If the label is a section-like heading (e.g., "Negated Findings", "Key Clinical Insights")
            # and value is empty, look ahead for content
            if not value and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Check if next line is content (not a header, not a new bold label, not empty)
                if next_line and not next_line.startswith('#') and not next_line.startswith('**'):
                    # It's content following the label - collect it as the value
                    pass  # Value stays empty, the next line will be parsed as paragraph/bullet
            
            elements.append({
                'type': 'label',
                'label': label,
                'value': value
            })
            logger.debug(f"Found label: {label}: {value[:40] if value else '(empty)'}")
            i += 1
            continue
        
        # Colon-based labels without bold: Label: Value
        colon_match = re.match(r'^([A-Z][A-Za-z\s]{2,30}):\s+(.+)$', stripped)
        if colon_match:
            elements.append({
                'type': 'label',
                'label': colon_match.group(1).strip(),
                'value': colon_match.group(2).strip()
            })
            i += 1
            continue
        
        # Regular text paragraphs
        elements.append({
            'type': 'paragraph',
            'text': stripped
        })
        logger.debug(f"Found paragraph: {stripped[:40]}")
        i += 1
    
    logger.info(f"Total parsed elements: {len(elements)}")
    return elements


def _parse_table(lines: List[str]) -> Optional[Dict]:
    """Parse markdown table lines into headers and rows"""
    if len(lines) < 2:
        return None
    
    rows = []
    for line in lines:
        # Skip separator rows (|---|---|)
        if re.match(r'^[\|\s\-:]+$', line):
            continue
        
        # Split by | and clean up each cell
        # Handle both |col1|col2| and col1|col2 formats
        cells = []
        parts = line.split('|')
        for p in parts:
            cell = p.strip()
            # Don't skip empty cells in the middle - they matter for alignment
            # Only skip the first/last if they're empty (from leading/trailing |)
            cells.append(cell)
        
        # Remove empty leading/trailing cells from |col1|col2| format
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]
        
        if cells:
            rows.append(cells)
            logger.debug(f"Parsed table row with {len(cells)} cells: {cells}")
    
    if not rows:
        return None
    
    # Ensure all rows have the same number of columns
    max_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append('')  # Pad short rows
    
    logger.info(f"Parsed table: {max_cols} cols, {len(rows)} rows")
    
    return {
        'headers': rows[0],
        'rows': rows[1:] if len(rows) > 1 else []
    }


def _clean_text(text: str) -> str:
    """Remove markdown formatting for clean PDF display"""
    # Remove inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove italic
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def generate_summary_pdf(
    summary_text: str,
    job_metadata: Optional[Dict] = None
) -> bytes:
    """
    Generate a professional PDF report from a clinical summary.
    
    Args:
        summary_text: Markdown-formatted summary text from AI
        job_metadata: Optional metadata (filename, model, token_usage, generated_at)
    
    Returns:
        PDF file as bytes
    """
    pdf = ClinicalReportPDF(job_metadata)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    content_width = 170  # Page width minus margins
    
    # Add metadata box at top
    if job_metadata:
        _render_metadata_box(pdf, job_metadata, content_width)
    
    # Parse content
    elements = parse_summary_content(summary_text)
    
    logger.info(f"Parsed {len(elements)} elements from summary")
    # Log all elements for debugging
    for i, elem in enumerate(elements):
        elem_type = elem.get('type')
        if elem_type == 'header':
            logger.info(f"Element {i}: HEADER level {elem.get('level')}: {elem.get('text', '')[:60]}")
        elif elem_type == 'table':
            logger.info(f"Element {i}: TABLE with {len(elem.get('headers',[]))} cols, {len(elem.get('rows',[]))} rows")
        elif elem_type == 'label':
            logger.info(f"Element {i}: LABEL '{elem.get('label', '')}' = '{elem.get('value', '')[:40]}'")
        else:
            logger.info(f"Element {i}: {elem_type.upper()}: {str(elem.get('text', ''))[:50]}")
    
    # Render each element
    for element in elements:
        try:
            elem_type = element.get('type')
            
            if elem_type == 'header':
                _render_header(pdf, element, content_width)
            elif elem_type == 'paragraph':
                _render_paragraph(pdf, element, content_width)
            elif elem_type == 'bullet':
                _render_bullet(pdf, element, content_width)
            elif elem_type == 'numbered':
                _render_numbered(pdf, element, content_width)
            elif elem_type == 'label':
                _render_label(pdf, element, content_width)
            elif elem_type == 'table':
                _render_table(pdf, element, content_width)
                
        except Exception as e:
            logger.warning(f"Render error for {elem_type}: {e}")
            continue
    
    return bytes(pdf.output())


def _render_metadata_box(pdf: ClinicalReportPDF, metadata: Dict, width: float):
    """Render the metadata information box"""
    y_start = pdf.get_y()
    box_height = 18
    
    # Box background
    pdf.set_fill_color(*pdf.COLOR_BG_LIGHT)
    pdf.set_draw_color(*pdf.COLOR_BORDER)
    pdf.rect(20, y_start, width, box_height, 'DF')
    
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(*pdf.COLOR_LIGHT)
    
    # First row: Model and Tokens
    pdf.set_xy(25, y_start + 3)
    model = metadata.get('model', 'GPT-4o-mini')
    pdf.cell(55, 5, f'AI Model: {model}')
    
    token_usage = metadata.get('token_usage', {})
    tokens = token_usage.get('total_tokens', '-')
    pdf.cell(55, 5, f'Tokens: {tokens}')
    
    cost = token_usage.get('estimated_cost_usd')
    if cost is not None:
        cost_str = f'${cost:.6f}' if cost < 0.01 else f'${cost:.4f}'
        pdf.cell(50, 5, f'Cost: {cost_str}')
    
    # Second row: Timestamp
    pdf.set_xy(25, y_start + 10)
    gen_time = metadata.get('generated_at', '')
    if gen_time:
        try:
            dt = datetime.fromisoformat(gen_time.replace('Z', '+00:00'))
            pdf.cell(100, 5, f'Analysis Date: {dt.strftime("%B %d, %Y at %H:%M UTC")}')
        except:
            pass
    
    pdf.set_y(y_start + box_height + 8)


def _render_header(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render section headers"""
    level = element.get('level', 2)
    text = _clean_text(element.get('text', ''))
    
    if not text:
        return
    
    # Page break protection for headers
    if pdf.get_y() > 250:
        pdf.add_page()
    
    pdf.ln(3)
    
    if level == 1:
        # Main title
        pdf.set_font('Helvetica', 'B', 14)
        pdf.set_text_color(*pdf.COLOR_PRIMARY)
        pdf.set_x(20)
        pdf.cell(width, 8, text, align='L')
        pdf.ln(9)
        # Underline
        pdf.set_draw_color(*pdf.COLOR_PRIMARY)
        pdf.set_line_width(0.5)
        pdf.line(20, pdf.get_y() - 1, 190, pdf.get_y() - 1)
        pdf.ln(2)
        
    elif level == 2:
        # Section header with blue background
        y_pos = pdf.get_y()
        pdf.set_fill_color(*pdf.COLOR_PRIMARY)
        pdf.rect(20, y_pos, width, 9, 'F')
        
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(24, y_pos + 2)
        pdf.cell(width - 8, 5, text.upper())
        pdf.set_y(y_pos + 12)
        
    elif level == 3:
        # Subsection header
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*pdf.COLOR_PRIMARY)
        pdf.set_x(20)
        pdf.cell(width, 6, text)
        pdf.ln(7)
        
    else:
        # Minor header
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(*pdf.COLOR_SECONDARY)
        pdf.set_x(20)
        pdf.cell(width, 5, text)
        pdf.ln(6)
    
    pdf.set_text_color(*pdf.COLOR_SECONDARY)


def _render_paragraph(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render paragraph text"""
    text = _clean_text(element.get('text', ''))
    if not text:
        return
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.set_x(20)
    pdf.multi_cell(width, 5.5, text)
    pdf.ln(2)


def _render_bullet(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render bullet point item with indent support"""
    text = _clean_text(element.get('text', ''))
    if not text:
        return
    
    # Calculate indent based on nesting level
    indent = element.get('indent', 0)
    base_x = 24 + (indent // 2) * 6  # Extra indent for nested items
    
    # Bullet character - use different symbols for nested levels
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.COLOR_ACCENT)
    pdf.set_x(base_x)
    
    bullet_char = chr(8226)  # Default bullet •
    if indent > 0:
        bullet_char = chr(9702)  # White bullet ◦ for nested
    
    pdf.cell(6, 5.5, bullet_char)
    
    # Item text
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    
    # Adjust width for indentation
    text_width = width - (base_x - 20) - 6
    pdf.multi_cell(text_width, 5.5, text)


def _render_numbered(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render numbered list item"""
    text = _clean_text(element.get('text', ''))
    num = element.get('number', '1')
    if not text:
        return
    
    # Number
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.COLOR_ACCENT)
    pdf.set_x(24)
    pdf.cell(8, 5.5, f'{num}.')
    
    # Text
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.multi_cell(width - 12, 5.5, text)


def _render_label(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render bold label with optional value - handles subsection headers too"""
    label = _clean_text(element.get('label', ''))
    value = _clean_text(element.get('value', ''))
    
    if not label:
        return
    
    # If no value, this is likely a subsection header - render it more prominently
    if not value:
        # Render as a subsection header (like ### level header)
        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*pdf.COLOR_PRIMARY)
        pdf.set_x(22)
        pdf.cell(width - 4, 6, label)
        pdf.ln(7)
        pdf.set_text_color(*pdf.COLOR_SECONDARY)
    else:
        # Regular label: value pair
        pdf.set_x(24)
        
        # Bold label
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*pdf.COLOR_PRIMARY)
        label_text = label + ':'
        label_width = pdf.get_string_width(label_text) + 3
        pdf.cell(label_width, 5.5, label_text)
        
        # Value
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(*pdf.COLOR_SECONDARY)
        remaining_width = width - label_width - 8
        
        if pdf.get_string_width(value) > remaining_width:
            # Value too long - wrap to next line
            pdf.ln(5.5)
            pdf.set_x(28)
            pdf.multi_cell(width - 12, 5.5, value)
        else:
            pdf.cell(remaining_width, 5.5, value)
            pdf.ln(5.5)


def _render_table(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render data table with professional styling - handles all cells properly"""
    headers = element.get('headers', [])
    rows = element.get('rows', [])
    
    if not headers and not rows:
        return
    
    num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if num_cols == 0:
        return
    
    logger.info(f"Rendering table: {num_cols} columns, {len(rows)} data rows")
    
    # Page break check
    row_height = 7  # Standard row height
    needed_height = (len(rows) + 2) * row_height + 10
    if pdf.get_y() + needed_height > 260:
        pdf.add_page()
    
    pdf.ln(4)
    
    # Use smaller font for tables
    pdf.set_font('Helvetica', '', 8)
    
    # Clean all table content first (remove markdown formatting like **bold**)
    headers = [_clean_text(str(h)) for h in headers]
    rows = [[_clean_text(str(cell)) if cell else '' for cell in row] for row in rows]
    
    # Calculate column widths based on cleaned content
    col_widths = []
    for col in range(num_cols):
        max_w = 20  # Minimum column width
        
        # Check header width
        if col < len(headers):
            header_text = headers[col]
            w = pdf.get_string_width(header_text) + 8
            max_w = max(max_w, w)
        
        # Check all row cells for this column
        for row in rows:
            if col < len(row):
                cell_text = row[col]
                w = pdf.get_string_width(cell_text) + 8
                max_w = max(max_w, min(w, 55))  # Cap individual column at 55
        
        col_widths.append(max_w)
    
    # Scale to fit available width
    total = sum(col_widths)
    max_table_width = min(width, 170)  # Allow more table width
    
    if total > max_table_width:
        scale = max_table_width / total
        col_widths = [max(w * scale, 18) for w in col_widths]  # Ensure minimum width
    
    logger.debug(f"Column widths: {col_widths}")
    
    # Draw header row
    if headers:
        pdf.set_fill_color(*pdf.COLOR_PRIMARY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        
        x_start = 20
        y_start = pdf.get_y()
        x = x_start
        
        for idx in range(num_cols):
            w = col_widths[idx]
            pdf.set_xy(x, y_start)
            
            # Get header text (already cleaned), truncate if needed
            header_text = headers[idx] if idx < len(headers) else ''
            display = _truncate_text(pdf, header_text, w - 4)
            
            pdf.cell(w, row_height, display, border=1, fill=True, align='C')
            x += w
        
        pdf.ln(row_height)
    
    # Draw data rows
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.set_font('Helvetica', '', 8)
    
    for row_idx, row in enumerate(rows):
        y = pdf.get_y()
        
        # Page break check
        if y + row_height > 265:
            pdf.add_page()
            y = pdf.get_y()
        
        # Alternating row colors
        if row_idx % 2 == 0:
            pdf.set_fill_color(*pdf.COLOR_BG_LIGHT)
        else:
            pdf.set_fill_color(255, 255, 255)
        
        x = 20
        for col_idx in range(num_cols):
            w = col_widths[col_idx]
            pdf.set_xy(x, y)
            
            # Get cell content (already cleaned), handle missing cells
            cell_text = row[col_idx] if col_idx < len(row) else ''
            display = _truncate_text(pdf, cell_text, w - 4)
            
            pdf.cell(w, row_height, display, border=1, fill=True)
            x += w
        
        pdf.ln(row_height)
    
    pdf.ln(4)


def _truncate_text(pdf: FPDF, text: str, max_width: float) -> str:
    """Truncate text to fit within max_width, adding ellipsis if needed"""
    if not text:
        return ''
    
    if pdf.get_string_width(text) <= max_width:
        return text
    
    # Progressively truncate
    while len(text) > 3 and pdf.get_string_width(text + '..') > max_width:
        text = text[:-1]
    
    return text + '..' if len(text) < len(text) else text


# Public convenience function
def markdown_to_pdf(markdown_text: str, metadata: Optional[Dict] = None) -> bytes:
    """
    Convert markdown text to professional PDF.
    
    Args:
        markdown_text: Markdown-formatted clinical summary
        metadata: Optional metadata dictionary
        
    Returns:
        PDF bytes
    """
    return generate_summary_pdf(markdown_text, metadata)
