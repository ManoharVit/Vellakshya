"""
PDF to HTML and multi-format conversion service.
Supports high-fidelity fixed-layout HTML, semantic responsive HTML, images, and Markdown.
"""
from __future__ import annotations
import base64
import html
import io
import zipfile
from typing import Literal
import fitz  # PyMuPDF


def _drawings_to_svg(page: fitz.Page) -> str:
    """
    Renders vector drawings, lines, rectangles, fills, and curves from page.get_drawings()
    into an absolute SVG overlay layer matching the exact PDF coordinates.
    """
    drawings = page.get_drawings()
    if not drawings:
        return ""
    rect = page.rect
    svg_parts = [
        f'<svg class="pdf-vector-layer" viewBox="0 0 {rect.width} {rect.height}" '
        f'style="position:absolute;top:0;left:0;width:{rect.width}pt;height:{rect.height}pt;pointer-events:none;z-index:1;">'
    ]
    for d in drawings:
        fill = d.get("fill")
        color = d.get("color")
        width = d.get("width", 1.0) or 1.0
        fill_opacity = d.get("fill_opacity", 1.0)
        stroke_opacity = d.get("stroke_opacity", 1.0)

        fill_str = (
            f"rgb({int(fill[0]*255)},{int(fill[1]*255)},{int(fill[2]*255)})"
            if fill
            else "none"
        )
        stroke_str = (
            f"rgb({int(color[0]*255)},{int(color[1]*255)},{int(color[2]*255)})"
            if color
            else "none"
        )

        extra_attrs: list[str] = []
        if fill and fill_opacity is not None and fill_opacity < 1.0:
            extra_attrs.append(f'fill-opacity="{fill_opacity:.2f}"')
        if color and stroke_opacity is not None and stroke_opacity < 1.0:
            extra_attrs.append(f'stroke-opacity="{stroke_opacity:.2f}"')
        attr_suffix = (" " + " ".join(extra_attrs)) if extra_attrs else ""

        for item in d.get("items", []):
            cmd = item[0]
            if cmd == "re":
                r = item[1]
                w = r.x1 - r.x0
                h = r.y1 - r.y0
                svg_parts.append(
                    f'  <rect x="{r.x0:.2f}" y="{r.y0:.2f}" width="{w:.2f}" height="{h:.2f}" '
                    f'fill="{fill_str}" stroke="{stroke_str}" stroke-width="{width:.2f}"{attr_suffix} />'
                )
            elif cmd == "l":
                p1, p2 = item[1], item[2]
                svg_parts.append(
                    f'  <line x1="{p1.x:.2f}" y1="{p1.y:.2f}" x2="{p2.x:.2f}" y2="{p2.y:.2f}" '
                    f'stroke="{stroke_str}" stroke-width="{width:.2f}"{attr_suffix} />'
                )
            elif cmd == "c":
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                svg_parts.append(
                    f'  <path d="M {p1.x:.2f} {p1.y:.2f} C {p2.x:.2f} {p2.y:.2f}, {p3.x:.2f} {p3.y:.2f}, {p4.x:.2f} {p4.y:.2f}" '
                    f'fill="{fill_str}" stroke="{stroke_str}" stroke-width="{width:.2f}"{attr_suffix} />'
                )
            elif cmd == "qu":
                q = item[1]
                points = f"{q.ul.x:.2f},{q.ul.y:.2f} {q.ur.x:.2f},{q.ur.y:.2f} {q.lr.x:.2f},{q.lr.y:.2f} {q.ll.x:.2f},{q.ll.y:.2f}"
                svg_parts.append(
                    f'  <polygon points="{points}" fill="{fill_str}" stroke="{stroke_str}" stroke-width="{width:.2f}"{attr_suffix} />'
                )
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _extract_embedded_fonts(doc: fitz.Document) -> str:
    """
    Extracts embedded TrueType/OpenType/WOFF font streams from PDF
    and generates Base64 @font-face rules so that the HTML renders
    pixel-identically across Windows, macOS, iOS, Android, and web browsers
    without font substitution or broken formatting.
    """
    font_css_rules: list[str] = []
    seen_fonts: set[str] = set()

    for page in doc:
        for font in page.get_fonts():
            xref = font[0]
            font_name = font[3]
            if font_name in seen_fonts or xref == 0:
                continue
            seen_fonts.add(font_name)
            try:
                name, ext, subtype, content = doc.extract_font(xref)
                if content and len(content) > 0 and ext in ("ttf", "otf", "woff", "woff2"):
                    b64_font = base64.b64encode(content).decode("ascii")
                    mime = f"font/{ext}" if ext != "ttf" else "font/ttf"
                    font_css_rules.append(
                        f'@font-face {{\n'
                        f'  font-family: "{font_name}";\n'
                        f'  src: url("data:{mime};base64,{b64_font}") format("{ext}");\n'
                        f'  font-display: swap;\n'
                        f'}}'
                    )
            except Exception:
                continue

    return "\n".join(font_css_rules)


def pdf_to_html_fixed(pdf_bytes: bytes, title: str = "Converted Document") -> str:
    """
    Converts PDF to high-fidelity, standalone HTML with exact layout, fonts, and positions.
    Each page is rendered inside a styled page container with absolute CSS coordinates.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_html: list[str] = []
    embedded_fonts_css = _extract_embedded_fonts(doc)
    
    for page_idx, page in enumerate(doc):
        rect = page.rect
        page_w = rect.width
        page_h = rect.height
        
        # PyMuPDF HTML extraction for this page (includes vector text, fonts, and embedded images)
        raw_page_html = page.get_text("html")
        svg_vector_layer = _drawings_to_svg(page)
        
        # Wrap each page in an interactive container
        page_block = f"""
        <section class="pdf-page-container" id="page-{page_idx + 1}" data-page="{page_idx + 1}" data-width="{page_w}" data-height="{page_h}" style="width: {page_w}pt; min-height: {page_h}pt;">
            <div class="pdf-page-header">
                <span class="page-badge">Page {page_idx + 1} of {len(doc)}</span>
                <span class="dim-badge">{int(page_w)} × {int(page_h)} pt</span>
            </div>
            <div class="pdf-page-body" style="width: {page_w}pt; height: {page_h}pt;">
                {svg_vector_layer}
                {raw_page_html}
            </div>
        </section>
        """
        pages_html.append(page_block)
        
    doc.close()
    
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
    <title>{html.escape(title)} — Converted HTML</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --paper-bg: #ffffff;
            --border-color: #334155;
            --accent-color: #38bdf8;
            --text-color: #0f172a;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        html {{
            -webkit-text-size-adjust: 100%;
            text-size-adjust: 100%;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: #f8fafc;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 24px 16px;
            gap: 24px;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            text-rendering: geometricPrecision;
            touch-action: pan-x pan-y pinch-zoom;
        }}
        /* Embedded PDF Fonts */
        {embedded_fonts_css}

        /* Standard PDF 14 cross-platform font normalization */
        @font-face {{
            font-family: "Helvetica";
            src: local("Helvetica"), local("Arial"), local("-apple-system"), local("Roboto"), local("sans-serif");
        }}
        @font-face {{
            font-family: "Times";
            src: local("Times New Roman"), local("Times"), local("Charter"), local("serif");
        }}
        @font-face {{
            font-family: "Courier";
            src: local("Courier New"), local("Courier"), local("Menlo"), local("monospace");
        }}

        .top-toolbar {{
            position: sticky;
            top: 12px;
            z-index: 100;
            background: rgba(30, 41, 59, 0.95);
            backdrop-filter: blur(8px);
            border: 1px solid var(--border-color);
            border-radius: 9999px;
            padding: 8px 24px;
            display: flex;
            align-items: center;
            gap: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .top-toolbar h1 {{
            font-size: 14px;
            font-weight: 600;
            color: #e2e8f0;
        }}
        .top-toolbar button {{
            background: #2563eb;
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.15s;
        }}
        .top-toolbar button:hover {{
            background: #1d4ed8;
        }}
        .document-viewport {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 24px;
            width: 100%;
            max-width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}
        .pdf-page-container {{
            background: var(--paper-bg);
            color: var(--text-color);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
            border-radius: 4px;
            overflow: hidden;
            position: relative;
            transition: transform 0.2s ease;
        }}
        .pdf-page-header {{
            background: #f1f5f9;
            color: #64748b;
            font-size: 11px;
            padding: 4px 12px;
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid #e2e8f0;
        }}
        .pdf-page-body {{
            position: relative;
            overflow: hidden;
            background: white;
        }}
        .pdf-page-body svg.pdf-vector-layer {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1;
        }}
        .pdf-page-body div[id^="page"], .pdf-page-body div.page {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 2;
        }}
        .pdf-page-body p {{
            position: absolute;
            margin: 0;
            padding: 0;
            white-space: pre;
        }}
        .pdf-page-body span, .pdf-page-body b, .pdf-page-body i {{
            white-space: pre;
        }}
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .top-toolbar {{
                display: none;
            }}
            .pdf-page-container {{
                box-shadow: none;
                page-break-after: always;
                border-radius: 0;
            }}
            .pdf-page-header {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <header class="top-toolbar">
        <h1>{html.escape(title)}</h1>
        <button onclick="toggleFitWidth()">↔️ Fit Width</button>
        <button onclick="window.print()">🖨️ Print / Export PDF</button>
        <button onclick="document.body.classList.toggle('light-theme')">🌓 Toggle Mode</button>
    </header>
    <main class="document-viewport">
        {"".join(pages_html)}
    </main>
    <script>
        let isFitWidth = false;
        function toggleFitWidth() {{
            isFitWidth = !isFitWidth;
            const containers = document.querySelectorAll('.pdf-page-container');
            containers.forEach(c => {{
                if (isFitWidth) {{
                    const w = parseFloat(c.getAttribute('data-width') || c.style.width);
                    const availW = window.innerWidth - 32;
                    const scale = availW / w;
                    c.style.transform = `scale(${{Math.min(1.0, scale)}})`;
                    c.style.transformOrigin = 'top center';
                    const diffH = c.offsetHeight * (1 - Math.min(1.0, scale));
                    c.style.marginBottom = `${{-diffH}}px`;
                }} else {{
                    c.style.transform = '';
                    c.style.transformOrigin = '';
                    c.style.marginBottom = '';
                }}
            }});
        }}
    </script>
</body>
</html>
"""
    return full_html


def pdf_to_html_semantic(pdf_bytes: bytes, title: str = "Converted Document") -> str:
    """
    Converts PDF to clean, responsive, semantic HTML flow (headings, paragraphs, lists)
    ideal for mobile reading, screen readers, and web publishing.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    sections_html: list[str] = []
    
    for page_idx, page in enumerate(doc):
        # Extract text blocks: (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")
        page_links = page.get_links()
        page_content: list[str] = []
        
        page_content.append(f"<div class='semantic-page-divider' id='p{page_idx + 1}'><span>Page {page_idx + 1}</span></div>")
        
        for block in blocks:
            # block_type == 0 is text, 1 is image
            if block[6] == 0:
                raw_text = block[4].strip()
                if not raw_text:
                    continue
                block_rect = fitz.Rect(block[0], block[1], block[2], block[3])
                # Check if this block intersects any link
                link_url = None
                for l in page_links:
                    if l.get("uri") and l.get("from") and block_rect.intersects(l["from"]):
                        link_url = l["uri"]
                        break

                lines = raw_text.split("\n")
                first_line = lines[0].strip()
                
                # Heuristic for headers: short line, title/uppercase or larger font size
                if len(first_line) < 80 and (first_line.isupper() or (len(lines) == 1 and len(first_line) < 45 and not first_line.endswith("."))):
                    item_html = f"<h2>{html.escape(first_line)}</h2>"
                    if len(lines) > 1:
                        remainder = "\n".join(lines[1:]).strip()
                        if remainder:
                            item_html += f"<p>{html.escape(remainder).replace(chr(10), '<br>')}</p>"
                else:
                    item_html = f"<p>{html.escape(raw_text).replace(chr(10), '<br>')}</p>"

                if link_url:
                    item_html = f"<a href='{html.escape(link_url)}' class='semantic-link' target='_blank' rel='noopener'>{item_html}</a>"

                page_content.append(item_html)
            elif block[6] == 1:
                page_content.append("<div class='image-placeholder'>[Image Object]</div>")
                
        # Append standalone page links not embedded within a text block
        for l in page_links:
            uri = l.get("uri")
            if uri and uri not in [p for p in page_content if uri in p]:
                page_content.append(f"<p><a href='{html.escape(uri)}' class='semantic-link' target='_blank' rel='noopener'>{html.escape(uri)}</a></p>")

        sections_html.append(f"<section class='semantic-page-card'>{''.join(page_content)}</section>")
        
    doc.close()
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} — Semantic HTML</title>
    <style>
        :root {{
            --bg-color: #f8fafc;
            --text-color: #1e293b;
            --card-bg: #ffffff;
            --border-color: #e2e8f0;
            --primary-color: #0284c7;
        }}
        body {{
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.7;
            padding: 32px 16px;
            max-width: 820px;
            margin: 0 auto;
        }}
        header {{
            margin-bottom: 32px;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 16px;
        }}
        h1 {{
            color: #0f172a;
            font-size: 26px;
        }}
        .semantic-page-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 28px 32px;
            margin-bottom: 24px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        }}
        .semantic-page-divider {{
            font-size: 12px;
            font-weight: 700;
            color: var(--primary-color);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 16px;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 4px;
        }}
        h2 {{
            color: #0f172a;
            font-size: 18px;
            margin-top: 16px;
            margin-bottom: 8px;
        }}
        p {{
            margin-bottom: 14px;
            font-size: 15px;
        }}
        .image-placeholder {{
            background: #f1f5f9;
            border: 1px dashed #cbd5e1;
            padding: 12px;
            text-align: center;
            font-size: 13px;
            color: #64748b;
            margin: 12px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <header>
        <h1>{html.escape(title)}</h1>
        <p style="color: #64748b; font-size: 14px;">Semantic Responsive Flow</p>
    </header>
    <main>
        {"".join(sections_html)}
    </main>
</body>
</html>
"""


def pdf_to_images_zip(pdf_bytes: bytes, dpi: int = 150, img_format: str = "png") -> bytes:
    """
    Renders every page of the PDF into an image and packages them inside a ZIP file.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            img_data = pix.tobytes(img_format)
            filename = f"page_{idx + 1:03d}.{img_format}"
            zf.writestr(filename, img_data)
            
    doc.close()
    return zip_buffer.getvalue()


def images_to_pdf(images: list[tuple[str, bytes]]) -> bytes:
    """
    Combines a list of image files into a single unified PDF document.
    """
    doc = fitz.open()
    for filename, img_bytes in images:
        img_doc = fitz.open(stream=img_bytes, filetype=filename.split(".")[-1].lower())
        rect = img_doc[0].rect
        pdf_bytes = img_doc.convert_to_pdf()
        img_doc.close()
        
        temp_pdf = fitz.open("pdf", pdf_bytes)
        doc.insert_pdf(temp_pdf)
        temp_pdf.close()
        
    out_pdf = doc.tobytes()
    doc.close()
    return out_pdf


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """
    Extracts text content formatted in structured Markdown.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    md_pages: list[str] = []
    
    for idx, page in enumerate(doc):
        md_pages.append(f"\n\n## Page {idx + 1}\n\n")
        blocks = page.get_text("blocks")
        for block in blocks:
            if block[6] == 0:  # text
                text = block[4].strip()
                if text:
                    md_pages.append(f"{text}\n\n")
                    
    doc.close()
    return "".join(md_pages)
