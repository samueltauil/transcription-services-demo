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
    """
    elements = []
    lines = text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            i += 1
            continue
        
        # Headers: ## Header Text
        header_match = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if header_match:
            level = len(header_match.group(1))
            elements.append({
                'type': 'header',
                'level': level,
                'text': header_match.group(2).strip()
            })
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
            continue
        
        # Bullet points: - Item or * Item
        bullet_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        if bullet_match:
            elements.append({
                'type': 'bullet',
                'text': bullet_match.group(1).strip()
            })
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
        
        # Bold label lines: **Label:** Value
        bold_match = re.match(r'^\*\*([^*]+)\*\*:?\s*(.*)$', stripped)
        if bold_match:
            elements.append({
                'type': 'label',
                'label': bold_match.group(1).strip(),
                'value': bold_match.group(2).strip() if bold_match.group(2) else ''
            })
            i += 1
            continue
        
        # Regular text paragraphs - treat as single line to avoid over-merging
        elements.append({
            'type': 'paragraph',
            'text': stripped
        })
        i += 1
    
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
        
        # Split by | and clean up
        cells = line.split('|')
        cells = [c.strip() for c in cells if c.strip()]
        
        if cells:
            rows.append(cells)
    
    if not rows:
        return None
    
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
    for i, elem in enumerate(elements[:5]):
        logger.info(f"Element {i}: type={elem.get('type')}, text={str(elem.get('text', elem.get('label', '')))[:50]}")
    
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
    """Render bullet point item"""
    text = _clean_text(element.get('text', ''))
    if not text:
        return
    
    # Bullet character
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.COLOR_ACCENT)
    pdf.set_x(24)
    pdf.cell(6, 5.5, chr(8226))
    
    # Item text
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.multi_cell(width - 10, 5.5, text)


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
    """Render bold label with optional value"""
    label = _clean_text(element.get('label', ''))
    value = _clean_text(element.get('value', ''))
    
    if not label:
        return
    
    pdf.set_x(24)
    
    # Bold label
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.COLOR_PRIMARY)
    label_text = label + ':'
    label_width = pdf.get_string_width(label_text) + 3
    pdf.cell(label_width, 5.5, label_text)
    
    # Value
    if value:
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
    else:
        pdf.ln(5.5)


def _render_table(pdf: ClinicalReportPDF, element: Dict, width: float):
    """Render data table with professional styling - compact size"""
    headers = element.get('headers', [])
    rows = element.get('rows', [])
    
    if not headers and not rows:
        return
    
    # Page break check
    row_height = 6  # Smaller row height
    needed_height = (len(rows) + 2) * row_height + 10
    if pdf.get_y() + needed_height > 260:
        pdf.add_page()
    
    pdf.ln(3)
    
    num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if num_cols == 0:
        return
    
    # Use smaller font for tables
    pdf.set_font('Helvetica', '', 8)
    
    # Calculate column widths - more compact
    col_widths = []
    for col in range(num_cols):
        max_w = 15  # Smaller minimum
        
        if col < len(headers):
            w = pdf.get_string_width(str(headers[col])) + 6
            max_w = max(max_w, w)
        
        for row in rows:
            if col < len(row):
                w = pdf.get_string_width(str(row[col])) + 6
                max_w = max(max_w, min(w, 60))  # Cap at 60
        
        col_widths.append(max_w)
    
    # Scale to fit but use less than full width for compact look
    total = sum(col_widths)
    max_table_width = min(width, 160)  # Cap table width
    if total > max_table_width:
        scale = max_table_width / total
        col_widths = [w * scale for w in col_widths]
    
    # Header row
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
                
                # Truncate if needed
                display = str(header)
                while pdf.get_string_width(display) > w - 6 and len(display) > 3:
                    display = display[:-1]
                if len(display) < len(str(header)):
                    display = display[:-2] + '..'
                
                pdf.cell(w, row_height, display, border=1, fill=True, align='C')
                x += w
        
        pdf.ln(row_height)
    
    # Data rows - smaller font
    pdf.set_text_color(*pdf.COLOR_SECONDARY)
    pdf.set_font('Helvetica', '', 8)
    
    for row_idx, row in enumerate(rows):
        y = pdf.get_y()
        
        # Page break
        if y + row_height > 265:
            pdf.add_page()
            y = pdf.get_y()
        
        # Alternating row colors
        if row_idx % 2 == 0:
            pdf.set_fill_color(*pdf.COLOR_BG_LIGHT)
        else:
            pdf.set_fill_color(255, 255, 255)
        
        x = 20
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                w = col_widths[idx]
                pdf.set_xy(x, y)
                
                # Truncate if needed
                display = str(cell)
                while pdf.get_string_width(display) > w - 4 and len(display) > 3:
                    display = display[:-1]
                if len(display) < len(str(cell)):
                    display = display[:-2] + '..'
                
                pdf.cell(w, row_height, display, border=1, fill=True)
                x += w
        
        pdf.ln(row_height)
    
    pdf.ln(3)


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
