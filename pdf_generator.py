"""
PDF Generator for Clinical Summaries
Converts markdown-formatted AI summaries to professionally styled PDFs
"""

import re
import logging
from html.parser import HTMLParser
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from io import BytesIO

import markdown
from fpdf import FPDF

logger = logging.getLogger(__name__)

# ============================================================================
# Clinical PDF Theme Colors (RGB)
# ============================================================================
COLORS = {
    'primary': (0, 120, 212),           # Azure Blue
    'primary_dark': (0, 69, 120),       # Navy Blue
    'text_primary': (33, 33, 33),       # Dark gray
    'text_secondary': (97, 97, 97),     # Medium gray
    'text_light': (255, 255, 255),      # White
    'border': (224, 224, 224),          # Light gray
    'surface': (250, 250, 250),         # Off-white
    'code_bg': (232, 245, 233),         # Light green
    'code_text': (46, 125, 50),         # Green
    'table_header': (227, 242, 253),    # Light blue
    'table_alt': (245, 245, 245),       # Alternating row
}


class MarkdownHTMLParser(HTMLParser):
    """Parse HTML from markdown conversion to extract structured elements"""
    
    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_text = ""
        self.tag_stack = []
        self.current_attrs = {}
        self.list_level = 0
        self.list_type_stack = []  # 'ul' or 'ol'
        self.list_counters = []
        self.in_table = False
        self.current_row = []
        self.table_rows = []
        self.is_header_row = False
    
    def handle_starttag(self, tag, attrs):
        # Flush any accumulated text
        if self.current_text.strip():
            self._flush_text()
        
        self.tag_stack.append(tag)
        self.current_attrs = dict(attrs)
        
        if tag in ('ul', 'ol'):
            self.list_level += 1
            self.list_type_stack.append(tag)
            self.list_counters.append(0)
        elif tag == 'li':
            if self.list_counters:
                self.list_counters[-1] += 1
        elif tag == 'table':
            self.in_table = True
            self.table_rows = []
        elif tag == 'thead':
            self.is_header_row = True
        elif tag == 'tbody':
            self.is_header_row = False
        elif tag == 'tr':
            self.current_row = []
        elif tag == 'code' and 'pre' not in self.tag_stack:
            self.elements.append({'type': 'inline_code_start'})
        elif tag == 'pre':
            self.elements.append({'type': 'code_block_start'})
    
    def handle_endtag(self, tag):
        # Flush text before closing tag
        if self.current_text.strip():
            self._flush_text()
        
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            pass  # Already handled in _flush_text
        elif tag in ('ul', 'ol'):
            self.list_level -= 1
            if self.list_type_stack:
                self.list_type_stack.pop()
            if self.list_counters:
                self.list_counters.pop()
        elif tag == 'table':
            self.in_table = False
            self.elements.append({
                'type': 'table',
                'rows': self.table_rows
            })
            self.table_rows = []
        elif tag == 'tr':
            if self.current_row:
                self.table_rows.append({
                    'cells': self.current_row,
                    'is_header': self.is_header_row
                })
            self.current_row = []
        elif tag == 'code' and len(self.tag_stack) > 0 and self.tag_stack[-1] != 'pre':
            self.elements.append({'type': 'inline_code_end'})
        elif tag == 'pre':
            self.elements.append({'type': 'code_block_end'})
        elif tag == 'p':
            self.elements.append({'type': 'paragraph_end'})
        
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()
    
    def handle_data(self, data):
        self.current_text += data
    
    def _flush_text(self):
        text = self.current_text.strip()
        if not text:
            self.current_text = ""
            return
        
        current_tag = self.tag_stack[-1] if self.tag_stack else None
        
        # Handle table cells
        if self.in_table and current_tag in ('th', 'td'):
            self.current_row.append({
                'text': text,
                'is_header': current_tag == 'th' or self.is_header_row
            })
            self.current_text = ""
            return
        
        # Handle headers
        if current_tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(current_tag[1])
            self.elements.append({
                'type': 'header',
                'level': level,
                'text': text
            })
        # Handle list items
        elif current_tag == 'li':
            list_type = self.list_type_stack[-1] if self.list_type_stack else 'ul'
            counter = self.list_counters[-1] if self.list_counters else 1
            self.elements.append({
                'type': 'list_item',
                'text': text,
                'level': self.list_level,
                'list_type': list_type,
                'number': counter
            })
        # Handle code blocks
        elif 'pre' in self.tag_stack:
            self.elements.append({
                'type': 'code_block_content',
                'text': text
            })
        # Handle inline code
        elif 'code' in self.tag_stack:
            self.elements.append({
                'type': 'inline_code',
                'text': text
            })
        # Regular text/paragraph
        else:
            self.elements.append({
                'type': 'text',
                'text': text,
                'bold': 'strong' in self.tag_stack or 'b' in self.tag_stack,
                'italic': 'em' in self.tag_stack or 'i' in self.tag_stack
            })
        
        self.current_text = ""


class ClinicalSummaryPDF(FPDF):
    """Generate professionally styled PDF for clinical summaries"""
    
    def __init__(self, job_metadata: Optional[Dict] = None):
        super().__init__()
        self.job_metadata = job_metadata or {}
        self.current_section = None
        
        # Use built-in fonts (Helvetica, Courier) - no TTF files needed
        # These fonts support basic Latin characters
        
        # Set margins
        self.set_margins(20, 25, 20)
        self.set_auto_page_break(auto=True, margin=25)
    
    def header(self):
        """Generate page header with clinical banner"""
        # Navy blue banner
        self.set_fill_color(*COLORS['primary_dark'])
        self.rect(0, 0, 210, 20, 'F')
        
        # Header title
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(*COLORS['text_light'])
        self.set_xy(20, 6)
        self.cell(0, 8, 'Clinical Summary Report', align='L')
        
        # Filename on right
        if self.job_metadata.get('filename'):
            self.set_font('Helvetica', '', 9)
            self.set_xy(20, 6)
            filename = self.job_metadata['filename']
            if len(filename) > 40:
                filename = filename[:37] + '...'
            self.cell(170, 8, filename, align='R')
        
        self.ln(15)
    
    def footer(self):
        """Generate page footer with page numbers"""
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*COLORS['text_secondary'])
        
        # Page number
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')
        
        # Generation timestamp
        if self.job_metadata.get('generated_at'):
            self.set_xy(20, -15)
            try:
                dt = datetime.fromisoformat(self.job_metadata['generated_at'].replace('Z', '+00:00'))
                self.cell(0, 10, f'Generated: {dt.strftime("%Y-%m-%d %H:%M UTC")}', align='L')
            except:
                pass
    
    def add_metadata_box(self):
        """Add metadata information box at the start"""
        self.set_fill_color(*COLORS['surface'])
        self.set_draw_color(*COLORS['border'])
        
        content_width = self.w - self.l_margin - self.r_margin
        box_height = 20
        y_start = self.get_y()
        
        # Draw box using margins
        self.rect(self.l_margin, y_start, content_width, box_height, 'DF')
        
        self.set_font('Helvetica', '', 9)
        self.set_text_color(*COLORS['text_secondary'])
        
        # Row 1: Model and Tokens
        half_width = (content_width - 10) / 2
        self.set_xy(self.l_margin + 5, y_start + 3)
        model = self.job_metadata.get('model', 'GPT-4o-mini')
        self.cell(half_width, 6, f'Model: {model}', align='L')
        
        token_usage = self.job_metadata.get('token_usage', {})
        total_tokens = token_usage.get('total_tokens', '-')
        self.cell(half_width, 6, f'Total Tokens: {total_tokens}', align='R')
        
        # Row 2: Cost estimate
        self.set_xy(self.l_margin + 5, y_start + 11)
        cost = token_usage.get('estimated_cost_usd')
        if cost is not None:
            cost_str = f'${cost:.6f}' if cost < 0.01 else f'${cost:.4f}'
            self.cell(half_width, 6, f'Estimated Cost: {cost_str}', align='L')
        
        self.set_y(y_start + box_height + 8)
        self.set_x(self.l_margin)
    
    def add_section_header(self, text: str, level: int = 2):
        """Add a styled section header"""
        # Reset to left margin
        self.set_x(self.l_margin)
        
        # Check if we need a page break (orphan protection)
        if self.get_y() > 240:
            self.add_page()
        
        # Parse section number if present (e.g., "1. FINDINGS SUMMARY")
        section_match = re.match(r'^(\d+)\.\s*(.+)$', text)
        content_width = self.w - self.l_margin - self.r_margin
        
        if level <= 2:
            # Major section header with background
            self.ln(6)
            
            y_pos = self.get_y()
            self.set_fill_color(*COLORS['primary'])
            self.rect(self.l_margin, y_pos, content_width, 10, 'F')
            
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(*COLORS['text_light'])
            
            if section_match:
                # Section number badge
                num, title = section_match.groups()
                self.set_xy(self.l_margin + 3, y_pos + 1.5)
                self.set_fill_color(*COLORS['text_light'])
                self.set_text_color(*COLORS['primary'])
                self.cell(7, 7, num, align='C', fill=True)
                self.set_text_color(*COLORS['text_light'])
                self.set_xy(self.l_margin + 13, y_pos + 2)
                self.cell(content_width - 15, 6, title.upper())
            else:
                self.set_xy(self.l_margin + 5, y_pos + 2)
                self.cell(content_width - 10, 6, text.upper())
            
            self.set_y(y_pos + 14)
            self.set_x(self.l_margin)
        
        elif level == 3:
            # Subsection header
            self.ln(4)
            self.set_x(self.l_margin)
            self.set_font('Helvetica', 'B', 10)
            self.set_text_color(*COLORS['primary'])
            self.cell(content_width, 7, text)
            self.ln(7)
            
            # Underline
            y_pos = self.get_y()
            self.set_draw_color(*COLORS['primary'])
            self.line(self.l_margin, y_pos - 2, self.l_margin + 80, y_pos - 2)
            self.set_x(self.l_margin)
        
        else:
            # Minor header
            self.ln(3)
            self.set_x(self.l_margin)
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(*COLORS['primary_dark'])
            self.cell(content_width, 6, text)
            self.ln(6)
        
        self.set_text_color(*COLORS['text_primary'])
        self.set_x(self.l_margin)
    
    def add_paragraph(self, text: str, bold: bool = False, italic: bool = False):
        """Add a paragraph of text"""
        if not text:
            return
        
        style = ''
        if bold:
            style = 'B'
        elif italic:
            style = 'I'
        
        self.set_font('Helvetica', style, 10)
        self.set_text_color(*COLORS['text_primary'])
        
        # Always reset to left margin for paragraphs
        self.set_x(self.l_margin)
        
        # Use full content width
        content_width = self.w - self.l_margin - self.r_margin
        self.multi_cell(content_width, 5.5, text)
        self.ln(2)
        self.set_x(self.l_margin)
    
    def add_list_item(self, text: str, level: int = 1, list_type: str = 'ul', number: int = 1):
        """Add a list item with bullet or number"""
        if not text:
            return
        
        # Limit nesting level to prevent excessive indentation
        level = min(level, 3)
        indent = self.l_margin + (level - 1) * 5
        bullet_width = 6
        
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*COLORS['text_primary'])
        
        # Bullet or number
        self.set_x(indent)
        if list_type == 'ul':
            self.set_font('Helvetica', 'B', 10)
            self.set_text_color(*COLORS['primary'])
            self.cell(bullet_width, 5, '-')
        else:
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(*COLORS['primary'])
            self.cell(bullet_width + 2, 5, f'{number}.')
            bullet_width += 2
        
        # Text - calculate remaining width from current position
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*COLORS['text_primary'])
        
        text_start_x = indent + bullet_width
        text_width = self.w - text_start_x - self.r_margin
        
        # Multi-cell for text wrapping
        self.multi_cell(text_width, 5.5, text)
        self.set_x(self.l_margin)
    
    def add_inline_code(self, text: str):
        """Add inline code with green badge styling"""
        if not text:
            return
        
        # For inline codes (like UMLS codes), just render as styled text inline
        # Check available space and add new line if needed
        available_width = self.w - self.r_margin - self.get_x()
        
        self.set_font('Courier', '', 9)
        text_width = self.get_string_width(text) + 6
        
        # If code won't fit on this line, start new line
        if text_width > available_width:
            self.ln(6)
            self.set_x(self.l_margin)
        
        self.set_fill_color(*COLORS['code_bg'])
        self.set_text_color(*COLORS['code_text'])
        
        self.cell(text_width, 5.5, ' ' + text + ' ', fill=True)
        
        # Reset font but stay on same line
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*COLORS['text_primary'])
    
    def add_code_block(self, text: str):
        """Add a code block with dark background"""
        if not text:
            return
        
        self.ln(2)
        
        # Reset to left margin
        self.set_x(self.l_margin)
        y_start = self.get_y()
        
        # Calculate height needed
        self.set_font('Courier', '', 9)
        lines = text.split('\n')
        line_height = 4.5
        block_height = min(len(lines) * line_height + 8, 200)  # Cap height
        
        # Check for page break
        if self.get_y() + block_height > 270:
            self.add_page()
            y_start = self.get_y()
        
        # Dark background
        block_width = self.w - self.l_margin - self.r_margin
        self.set_fill_color(30, 30, 30)
        self.rect(self.l_margin, y_start, block_width, block_height, 'F')
        
        # Code text
        self.set_text_color(212, 212, 212)
        self.set_xy(self.l_margin + 4, y_start + 4)
        
        max_lines = int((block_height - 8) / line_height)
        for i, line in enumerate(lines[:max_lines]):
            # Truncate long lines
            if len(line) > 80:
                line = line[:77] + '...'
            self.cell(0, line_height, line)
            self.ln(line_height)
            self.set_x(self.l_margin + 4)
        
        self.set_y(y_start + block_height + 4)
        self.set_text_color(*COLORS['text_primary'])
        self.set_font('Helvetica', '', 10)
    
    def add_table(self, rows: List[Dict]):
        """Add a table with auto-fit columns"""
        if not rows:
            return
        
        # Reset position
        self.set_x(self.l_margin)
        
        # Check for page break (tables need more space)
        if self.get_y() > 220:
            self.add_page()
        
        self.ln(4)
        
        # Calculate column widths based on content
        num_cols = len(rows[0]['cells']) if rows else 0
        if num_cols == 0:
            return
        
        content_width = self.w - self.l_margin - self.r_margin
        
        # Measure max content width for each column
        self.set_font('Helvetica', '', 9)
        col_widths = []
        
        for col_idx in range(num_cols):
            max_content = 0
            for row in rows:
                if col_idx < len(row['cells']):
                    cell = row['cells'][col_idx]
                    width = self.get_string_width(cell['text']) + 8
                    max_content = max(max_content, width)
            col_widths.append(max(max_content, 20))  # Minimum 20
        
        # Scale to fit available width
        total_width = sum(col_widths)
        if total_width != content_width:
            scale = content_width / total_width
            col_widths = [w * scale for w in col_widths]
        
        row_height = 8
        
        for row_idx, row in enumerate(rows):
            y_pos = self.get_y()
            
            # Check for page break
            if y_pos + row_height > 270:
                self.add_page()
                y_pos = self.get_y()
            
            # Background color
            if row.get('is_header'):
                self.set_fill_color(*COLORS['table_header'])
                self.set_font('Helvetica', 'B', 9)
            elif row_idx % 2 == 0:
                self.set_fill_color(*COLORS['surface'])
                self.set_font('Helvetica', '', 9)
            else:
                self.set_fill_color(255, 255, 255)
                self.set_font('Helvetica', '', 9)
            
            self.set_text_color(*COLORS['text_primary'])
            self.set_draw_color(*COLORS['border'])
            
            x_pos = self.l_margin
            for col_idx, cell in enumerate(row['cells']):
                if col_idx < len(col_widths):
                    width = col_widths[col_idx]
                    self.set_xy(x_pos, y_pos)
                    
                    # Truncate text smartly based on actual width
                    text = cell['text']
                    text_width = self.get_string_width(text)
                    if text_width > width - 4:
                        # Truncate to fit
                        while self.get_string_width(text + '..') > width - 4 and len(text) > 1:
                            text = text[:-1]
                        text = text + '..' if len(cell['text']) > len(text) else text
                    
                    self.cell(width, row_height, text, border=1, fill=True)
                    x_pos += width
            
            self.ln(row_height)
        
        self.ln(4)
        self.set_x(self.l_margin)
    
    def add_horizontal_rule(self):
        """Add a horizontal divider"""
        self.set_x(self.l_margin)
        self.ln(3)
        y_pos = self.get_y()
        content_width = self.w - self.l_margin - self.r_margin
        self.set_draw_color(*COLORS['border'])
        self.set_line_width(0.3)
        self.dashed_line(self.l_margin, y_pos, self.l_margin + content_width, y_pos, dash_length=2, space_length=2)
        self.set_line_width(0.2)
        self.ln(5)
        self.set_x(self.l_margin)


def parse_markdown_to_elements(markdown_text: str) -> List[Dict]:
    """Convert markdown text to structured elements"""
    # Convert markdown to HTML
    md = markdown.Markdown(extensions=['tables', 'fenced_code'])
    html_content = md.convert(markdown_text)
    
    # Parse HTML to extract elements
    parser = MarkdownHTMLParser()
    parser.feed(html_content)
    
    return parser.elements


def generate_summary_pdf(
    summary_text: str,
    job_metadata: Optional[Dict] = None
) -> bytes:
    """
    Generate a PDF from a markdown-formatted clinical summary
    
    Args:
        summary_text: Markdown-formatted summary text
        job_metadata: Optional dict with filename, generated_at, model, token_usage
    
    Returns:
        PDF file as bytes
    """
    try:
        pdf = ClinicalSummaryPDF(job_metadata or {})
        pdf.alias_nb_pages()
        pdf.add_page()
        
        # Add metadata box if we have metadata
        if job_metadata:
            try:
                pdf.add_metadata_box()
            except Exception as e:
                logger.warning(f"Failed to add metadata box: {e}")
        
        # Parse markdown to elements
        elements = parse_markdown_to_elements(summary_text)
        
        in_code_block = False
        code_buffer = []
        
        for element in elements:
            try:
                elem_type = element.get('type')
                
                # Reset position if we've drifted too far right
                if pdf.get_x() > pdf.w - 30:
                    pdf.ln(5)
                    pdf.set_x(pdf.l_margin)
                
                if elem_type == 'header':
                    pdf.add_section_header(element['text'], element['level'])
                
                elif elem_type == 'text':
                    if not in_code_block:
                        pdf.add_paragraph(
                            element['text'],
                            bold=element.get('bold', False),
                            italic=element.get('italic', False)
                        )
                
                elif elem_type == 'list_item':
                    pdf.add_list_item(
                        element['text'],
                        level=element.get('level', 1),
                        list_type=element.get('list_type', 'ul'),
                        number=element.get('number', 1)
                    )
                
                elif elem_type == 'table':
                    pdf.add_table(element['rows'])
                
                elif elem_type == 'inline_code':
                    pdf.add_inline_code(element['text'])
                
                elif elem_type == 'code_block_start':
                    in_code_block = True
                    code_buffer = []
                
                elif elem_type == 'code_block_content':
                    code_buffer.append(element['text'])
                
                elif elem_type == 'code_block_end':
                    if code_buffer:
                        pdf.add_code_block('\n'.join(code_buffer))
                    in_code_block = False
                    code_buffer = []
                
                elif elem_type == 'paragraph_end':
                    pass  # Spacing handled in paragraph
                    
            except Exception as elem_error:
                logger.warning(f"Failed to render element {elem_type}: {elem_error}")
                # Try to recover by adding a line break
                try:
                    pdf.ln(5)
                    pdf.set_x(pdf.l_margin)
                except:
                    pass
        
        # Return PDF as bytes
        return bytes(pdf.output())
        
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise


# Convenience function for direct text-to-PDF conversion
def markdown_to_pdf(markdown_text: str, metadata: Optional[Dict] = None) -> bytes:
    """Simple wrapper for generating PDF from markdown"""
    return generate_summary_pdf(markdown_text, metadata)
