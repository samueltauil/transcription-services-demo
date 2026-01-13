"""
Professional Clinical Summary PDF Generator
Enterprise-grade PDF report generation for healthcare transcription summaries

This module provides clean, reliable PDF generation using fpdf2 with:
- Professional healthcare-appropriate styling
- Clean typography and consistent spacing
- Robust error handling
- Simple line-by-line rendering that works reliably
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


def clean_markdown(text: str) -> str:
    """Remove all markdown formatting from text"""
    if not text:
        return ''
    # Remove bold **text**
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove italic *text* or _text_
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Remove inline code `text`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def generate_summary_pdf(
    summary_text: str,
    job_metadata: Optional[Dict] = None
) -> bytes:
    """
    Generate a professional PDF report from a clinical summary.
    Uses a simple, reliable line-by-line approach.
    
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
    
    # Split into lines and process each one
    lines = summary_text.split('\n')
    
    logger.info(f"Processing {len(lines)} lines for PDF generation")
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            i += 1
            continue
        
        # Check for table (starts with |)
        if stripped.startswith('|') and '|' in stripped[1:]:
            # Collect all table lines
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            _render_table_simple(pdf, table_lines, content_width)
            continue
        
        # Section headers: ### 1. HEADER or ## HEADER
        header_match = re.match(r'^(#{1,4})\s+(?:\d+\.\s*)?(.+)$', stripped)
        if header_match:
            level = len(header_match.group(1))
            header_text = clean_markdown(header_match.group(2))
            _render_section_header(pdf, header_text, level, content_width)
            logger.info(f"Rendered header: {header_text[:50]}")
            i += 1
            continue
        
        # Bullet points with any indentation
        bullet_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if bullet_match:
            indent_spaces = len(bullet_match.group(1))
            bullet_text = clean_markdown(bullet_match.group(2))
            _render_bullet_item(pdf, bullet_text, indent_spaces, content_width)
            logger.info(f"Rendered bullet (indent={indent_spaces}): {bullet_text[:40]}")
            i += 1
            continue
        
        # Numbered items: 1. Item
        num_match = re.match(r'^(\d+)[.)]\s+(.+)$', stripped)
        if num_match:
            num = num_match.group(1)
            item_text = clean_markdown(num_match.group(2))
            _render_numbered_item(pdf, num, item_text, content_width)
            i += 1
            continue
        
        # Regular paragraph text
        para_text = clean_markdown(stripped)
        if para_text:
            _render_paragraph(pdf, para_text, content_width)
        i += 1
    
    logger.info("PDF generation complete")
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


def _render_section_header(pdf: ClinicalReportPDF, text: str, level: int, width: float):
    """Render section headers with professional styling"""
    if not text:
        return
    
    # Page break protection for headers
    if pdf.get_y() > 250:
        pdf.add_page()
    
    pdf.ln(4)
    
    if level <= 2:
        # Main section header with blue background
        y_pos = pdf.get_y()
        pdf.set_fill_color(*pdf.COLOR_PRIMARY)
        pdf.rect(20, y_pos, width, 9, 'F')
        
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(24, y_pos + 2)
        pdf.cell(width - 8, 5, text.upper())
        pdf.set_y(y_pos + 13)
    else:
        # Subsection header
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*pdf.COLOR_PRIMARY)
        pdf.set_x(20)
        pdf.cell(width, 6, text)
        pdf.ln(8)
    
    pdf.set_text_color(*pdf.COLOR_SECONDARY)


def _render_bullet_item(pdf: ClinicalReportPDF, text: str, indent_spaces: int, width: float):
    """Render a bullet point with proper indentation"""
    if not text:
        return
    
    # Calculate visual indent level (every 2 spaces = 1 indent level)
    indent_level = indent_spaces // 2
    base_x = 24 + (indent_level * 8)
    
    # Determine if this is a label-style bullet (ends with colon)
    is_label = text.endswith(':') and len(text) < 80
    
    # Draw bullet - use ASCII characters since Helvetica doesn't support Unicode
    pdf.set_x(base_x)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.COLOR_ACCENT)
    
    if indent_level == 0:
        bullet = '-'  # Primary bullet
    else:
        bullet = '>'  # Nested bullet
    
    pdf.cell(5, 5, bullet)
    
    # Draw text
    if is_label:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*pdf.COLOR_PRIMARY)
    else:
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(*pdf.COLOR_SECONDARY)
    
    text_width = width - (base_x - 20) - 5
    
    # Get current position after bullet
    x_text = pdf.get_x()
    y_text = pdf.get_y()
    
    # Check if text fits on one line
    if pdf.get_string_width(text) <= text_width:
        pdf.cell(text_width, 5, text)
        pdf.ln(6)
    else:
        # Multi-line text - use multi_cell
        pdf.set_xy(x_text, y_text)
        pdf.multi_cell(text_width, 5, text)
        pdf.ln(1)


def _render_numbered_item(pdf: ClinicalReportPDF, num: str, text: str, width: float):
    """Render a numbered list item"""
    if not text:
        return
    
    pdf.set_x(24)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.COLOR_ACCENT)
    pdf.cell(8, 5, f'{num}.')
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    
    x_text = pdf.get_x()
    y_text = pdf.get_y()
    text_width = width - 12
    
    if pdf.get_string_width(text) <= text_width:
        pdf.cell(text_width, 5, text)
        pdf.ln(6)
    else:
        pdf.set_xy(x_text, y_text)
        pdf.multi_cell(text_width, 5, text)
        pdf.ln(1)


def _render_paragraph(pdf: ClinicalReportPDF, text: str, width: float):
    """Render paragraph text"""
    if not text:
        return
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.set_x(20)
    pdf.multi_cell(width, 5, text)
    pdf.ln(2)


def _render_table_simple(pdf: ClinicalReportPDF, table_lines: List[str], width: float):
    """Render a markdown table with simple, reliable approach"""
    if not table_lines:
        return
    
    # Parse table into rows
    rows = []
    for line in table_lines:
        # Skip separator lines (|---|---|)
        if re.match(r'^[\|\s\-:]+$', line):
            continue
        
        # Split by | and clean
        cells = []
        parts = line.split('|')
        for p in parts:
            cell = clean_markdown(p.strip())
            cells.append(cell)
        
        # Remove empty first/last from |cell|cell| format
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]
        
        if cells:
            rows.append(cells)
    
    if not rows:
        return
    
    # Ensure consistent column count
    num_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < num_cols:
            row.append('')
    
    headers = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []
    
    logger.info(f"Rendering table: {num_cols} cols, {len(data_rows)} data rows")
    
    # Page break check
    if pdf.get_y() + (len(data_rows) + 2) * 7 > 260:
        pdf.add_page()
    
    pdf.ln(4)
    
    # Calculate column widths
    pdf.set_font('Helvetica', '', 8)
    col_widths = []
    for col in range(num_cols):
        max_w = 20
        if col < len(headers):
            max_w = max(max_w, pdf.get_string_width(headers[col]) + 8)
        for row in data_rows:
            if col < len(row):
                max_w = max(max_w, min(pdf.get_string_width(row[col]) + 8, 50))
        col_widths.append(max_w)
    
    # Scale to fit
    total = sum(col_widths)
    max_table_width = min(width, 170)
    if total > max_table_width:
        scale = max_table_width / total
        col_widths = [max(w * scale, 15) for w in col_widths]
    
    row_height = 7
    
    # Draw headers
    if headers:
        pdf.set_fill_color(*pdf.COLOR_PRIMARY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        
        x = 20
        y = pdf.get_y()
        for idx, header in enumerate(headers):
            if idx < len(col_widths):
                w = col_widths[idx]
                pdf.set_xy(x, y)
                display = _truncate(pdf, header, w - 4)
                pdf.cell(w, row_height, display, border=1, fill=True, align='C')
                x += w
        pdf.ln(row_height)
    
    # Draw data rows
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.set_font('Helvetica', '', 8)
    
    for row_idx, row in enumerate(data_rows):
        y = pdf.get_y()
        if y + row_height > 265:
            pdf.add_page()
            y = pdf.get_y()
        
        # Alternating colors
        if row_idx % 2 == 0:
            pdf.set_fill_color(*pdf.COLOR_BG_LIGHT)
        else:
            pdf.set_fill_color(255, 255, 255)
        
        x = 20
        for idx in range(num_cols):
            w = col_widths[idx] if idx < len(col_widths) else 20
            pdf.set_xy(x, y)
            cell_text = row[idx] if idx < len(row) else ''
            display = _truncate(pdf, cell_text, w - 4)
            pdf.cell(w, row_height, display, border=1, fill=True)
            x += w
        pdf.ln(row_height)
    
    pdf.ln(4)


def _truncate(pdf: FPDF, text: str, max_width: float) -> str:
    """Truncate text to fit width"""
    if not text:
        return ''
    if pdf.get_string_width(text) <= max_width:
        return text
    while len(text) > 3 and pdf.get_string_width(text + '..') > max_width:
        text = text[:-1]
    return text + '..'


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
