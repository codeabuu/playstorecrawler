"""PDF report generation for combined review views."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.models import App


STARS = {1: "1 star", 2: "2 stars", 3: "3 stars", 4: "4 stars", 5: "5 stars"}


def _filters_summary(request):
    """Human-readable description of the filters applied to the report."""
    parts = []
    min_star = request.GET.get("min_star") or "1"
    max_star = request.GET.get("max_star") or "5"
    parts.append(f"Stars: {min_star}-{max_star}")
    if request.GET.get("date_from"):
        parts.append(f"From: {request.GET['date_from']}")
    if request.GET.get("date_to"):
        parts.append(f"To: {request.GET['date_to']}")
    if request.GET.get("app_version"):
        parts.append(f"App version: {request.GET['app_version']}")
    return " | ".join(parts)


def build_reviews_pdf(request, app_ids, rows):
    """Render the selected apps' reviews into a PDF, returned as a BytesIO."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Play Store review report",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=6)
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#666666"))

    apps = {a.app_id: a for a in App.objects.filter(app_id__in=app_ids)}

    story = [
        Paragraph("Play Store review report", h1),
        Paragraph(_filters_summary(request), meta),
        Paragraph(f"{len(app_ids)} app(s) selected &middot; {len(rows)} review(s)", meta),
        Spacer(1, 8),
        Paragraph("Apps included", h2),
    ]

    app_rows = [["App", "Package ID"]]
    for app_id in app_ids:
        app = apps.get(app_id)
        app_rows.append([app.title if app and app.title else app_id, app_id])
    table = Table(app_rows, colWidths=[80 * mm, 90 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)

    # Star distribution across everything in the report.
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in rows:
        if r.score in counts:
            counts[r.score] += 1
    story.append(Paragraph("Star distribution", h2))
    dist = [[STARS[s] for s in (1, 2, 3, 4, 5)], [str(counts[s]) for s in (1, 2, 3, 4, 5)]]
    dist_table = Table(dist, colWidths=[32 * mm] * 5)
    dist_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(dist_table)

    story.append(PageBreak())
    story.append(Paragraph(f"Reviews ({len(rows)})", h2))

    if not rows:
        story.append(Paragraph("No reviews match the selected filters.", body))

    for r in rows:
        app = apps.get(r.app_id)
        title = app.title if app and app.title else r.app_id
        head = f"<b>{STARS.get(r.score, r.score)}</b> &middot; {title}"
        if r.at:
            head += f" &middot; {r.at:%Y-%m-%d}"
        if r.app_version:
            head += f" &middot; v{r.app_version}"
        if r.thumbs_up:
            head += f" &middot; {r.thumbs_up} thumbs up"

        block = [Paragraph(head, small), Paragraph(_esc(r.content) or "(empty review)", body)]
        if r.reply_content:
            block.append(Paragraph(f"<b>Developer:</b> {_esc(r.reply_content)}", small))
        block.append(Spacer(1, 8))
        story.append(KeepTogether(block))

    doc.build(story)
    buf.seek(0)
    return buf


def _esc(text):
    """Escape text for reportlab's mini-HTML markup."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
