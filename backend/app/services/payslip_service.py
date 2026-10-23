"""Renders a salary payment as a PDF payslip.

Every figure on the page comes from the SalaryPayment row passed in (which
itself snapshots what was actually paid that month - see the comment on
SalaryPayment.basic_pay). Only the company letterhead (name, logo) is a
setting (COMPANY_NAME in .env) and a logo file, since that's the business's identity, not employee data.
"""

from datetime import datetime, timezone
from importlib import resources
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

from app.config import settings
from app.models.payroll import SalaryPayment

COMPANY_TAGLINE = "Payslip"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

INK = colors.HexColor("#292524")
MUTED = colors.HexColor("#78716c")
MUTED_ON_NAVY = colors.HexColor("#A9AEDC")
NAVY = colors.HexColor("#1E2761")
GOLD = colors.HexColor("#C79A2B")
LINE = colors.HexColor("#E7E5E4")
PAID_GREEN = colors.HexColor("#15803D")
ZEBRA_TINT = colors.HexColor("#FAFAF9")

FONT = "Lato"
FONT_BOLD = "Lato-Bold"

_FONTS_REGISTERED = False


def _ensure_fonts_registered() -> None:
    """Embeds a real typeface instead of relying on the PDF reader's built-in Helvetica - this is one
    of the biggest single factors in whether a generated document reads as "a template" or "designed"."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    fonts_dir = resources.files("app").joinpath("static", "fonts")
    pdfmetrics.registerFont(TTFont(FONT, str(fonts_dir.joinpath("Lato-Regular.ttf"))))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(fonts_dir.joinpath("Lato-Bold.ttf"))))
    _FONTS_REGISTERED = True


def _logo_path() -> str:
    return str(resources.files("app").joinpath("static", "company_logo.png"))


def _draw_page_frame(canvas, doc):
    """A thin border around the whole page and a confidentiality notice - the "formal document" look a
    payslip is expected to have, rather than text simply floating on a blank page."""
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.75)
    canvas.rect(10 * mm, 10 * mm, A4[0] - 20 * mm, A4[1] - 20 * mm)
    canvas.setFont(FONT, 7)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(A4[0] / 2, 12.5 * mm, "Confidential - for the named employee only")
    canvas.restoreState()


def _payslip_number(payment: SalaryPayment) -> str:
    """A stable per-payslip reference, the kind every real payslip carries for traceability - not
    stored anywhere, just derived from facts that never change about an already-paid month."""
    return f"PS-{payment.year}{payment.month:02d}-{payment.employee.employee_code}"


def _attendance_summary(payment: SalaryPayment) -> tuple[list[list[str]], list[list[str]], str] | None:
    """A full day-by-day breakdown of the month, split into two columns the same shape as the
    Earnings/Deductions tables (so it fits one page instead of a single tall list), plus the payable-days
    total line. None for a payment made before pay was attendance-based (payment.total_days is null),
    when everyone was simply paid their full salary with nothing to break down."""
    if payment.total_days is None or payment.payable_days is None:
        return None

    def days(n: int | None) -> str:
        return f"{n or 0:g}"

    left = [
        ["Attendance", "Days"],
        ["Present", days(payment.present_days)],
        ["Late (paid in full)", days(payment.late_days)],
        ["Half day", days(payment.half_days)],
        ["Absent", days(payment.absent_days)],
    ]
    right = [
        ["Leave & Off", "Days"],
        ["Leave, paid", days(payment.paid_leave_days)],
        ["Leave, unpaid", days(payment.unpaid_leave_days)],
        ["Half-day leave", days(payment.half_leave_days)],
        ["Weekly off / holiday", days(payment.days_off_days)],
    ]
    payable = f"{float(payment.payable_days):g} of {payment.total_days} days"
    return left, right, payable


def render_payslip_pdf(payment: SalaryPayment) -> bytes:
    _ensure_fonts_registered()

    employee = payment.employee
    basic_pay = float(payment.basic_pay or 0)
    allowances = float(payment.allowances or 0)
    deductions = float(payment.deductions or 0)
    gross = basic_pay + allowances
    net_pay = float(payment.amount)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Payslip - {employee.full_name} - {MONTH_NAMES[payment.month - 1]} {payment.year}",
    )

    h1 = ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=17, textColor=colors.white, leading=21)
    h1_tagline = ParagraphStyle("h1_tagline", fontName=FONT, fontSize=9, textColor=MUTED_ON_NAVY, leading=12)
    h2 = ParagraphStyle("h2", fontName=FONT, fontSize=9, textColor=MUTED, leading=12)
    label = ParagraphStyle("label", fontName=FONT, fontSize=8.5, textColor=MUTED, leading=12)
    value = ParagraphStyle("value", fontName=FONT_BOLD, fontSize=9.5, textColor=INK, leading=13)
    section = ParagraphStyle("section", fontName=FONT_BOLD, fontSize=10, textColor=NAVY, leading=14, spaceAfter=4)
    footnote = ParagraphStyle("footnote", fontName=FONT, fontSize=7.5, textColor=MUTED, leading=11)

    story = []

    # A bold, solid letterhead band - closer to how a bank or established company header reads, rather
    # than a tinted strip that could be mistaken for a decorative accent.
    logo = Image(_logo_path(), width=15 * mm, height=13.7 * mm)
    header_text = [Paragraph(escape(settings.company_name.upper()), h1), Paragraph(COMPANY_TAGLINE, h1_tagline)]
    header_table = Table([[logo, header_text]], colWidths=[20 * mm, None])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 2, GOLD),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    period_label = f"{MONTH_NAMES[payment.month - 1]} {payment.year}"
    status_color = PAID_GREEN if payment.status.value == "PAID" else MUTED
    status_style = ParagraphStyle("status", fontName=FONT_BOLD, fontSize=10, textColor=status_color)
    period_table = Table(
        [[Paragraph(f"Payslip for {period_label}", section), Paragraph(payment.status.value, status_style)]],
        colWidths=[None, 40 * mm],
    )
    period_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(period_table)
    story.append(Paragraph(f"Payslip No: {_payslip_number(payment)}", h2))
    story.append(Spacer(1, 2 * mm))

    divider = Table([[""]], colWidths=[A4[0] - 2 * doc.leftMargin])
    divider.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.75, LINE)]))
    story.append(divider)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Employee Details", section))

    def cell(text_label: str, text_value: str):
        return [Paragraph(text_label, label), Paragraph(text_value, value)]

    details_rows = [
        [cell("Employee name", employee.full_name), cell("Employee code", employee.employee_code)],
        [cell("Department", employee.department.name), cell("Designation", employee.designation.name)],
        [cell("Role", employee.user.role.name), cell("Date of joining", employee.date_of_joining.strftime("%d %b %Y"))],
    ]
    flat_rows = []
    for pair in details_rows:
        flat_rows.append([pair[0][0], pair[0][1], pair[1][0], pair[1][1]])
    details_table = Table(flat_rows, colWidths=[32 * mm, 60 * mm, 32 * mm, None])
    details_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), ZEBRA_TINT),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
        ("LEFTPADDING", (2, 0), (2, -1), 8),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 8),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 6 * mm))

    def money(amount: float) -> str:
        return f"Rs. {amount:,.2f}"

    earnings_rows = [
        ["Earnings", "Amount"],
        ["Basic pay", money(basic_pay)],
        ["Allowances", money(allowances)],
        ["Gross pay", money(gross)],
    ]
    deductions_rows = [
        ["Deductions", "Amount"],
        ["Deductions", money(deductions)],
        ["", ""],
        ["Total deductions", money(deductions)],
    ]

    def ledger_table(rows, col_widths, total_row=True):
        t = Table(rows, colWidths=col_widths)
        last = len(rows) - 1
        style = [
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, 1), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        if total_row:
            style += [
                ("ROWBACKGROUNDS", (0, 1), (-1, last - 1), [colors.white, ZEBRA_TINT]),
                ("LINEBELOW", (0, 1), (-1, last - 1), 0.5, LINE),
                ("FONTNAME", (0, last), (-1, last), FONT_BOLD),
                ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#F0F0F7")),
                ("LINEABOVE", (0, last), (-1, last), 0.75, NAVY),
            ]
        else:
            style += [
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA_TINT]),
                ("LINEBELOW", (0, 1), (-1, -2), 0.5, LINE),
            ]
        t.setStyle(TableStyle(style))
        return t

    combined = Table(
        [[ledger_table(earnings_rows, [42 * mm, 38 * mm]), ledger_table(deductions_rows, [42 * mm, 38 * mm])]],
        colWidths=[85 * mm, 85 * mm],
    )
    combined.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, 0), 6)]))
    story.append(combined)
    story.append(Spacer(1, 6 * mm))

    attendance_summary = _attendance_summary(payment)
    if attendance_summary:
        left_rows, right_rows, payable_text = attendance_summary
        story.append(Paragraph("Attendance Summary", section))
        attendance_combined = Table(
            [[
                ledger_table(left_rows, [32 * mm, 20 * mm], total_row=False),
                ledger_table(right_rows, [40 * mm, 20 * mm], total_row=False),
            ]],
            colWidths=[85 * mm, 85 * mm],
        )
        attendance_combined.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, 0), 6)]))
        story.append(attendance_combined)
        story.append(Spacer(1, 2 * mm))

        payable_style = ParagraphStyle("payable", fontName=FONT_BOLD, fontSize=9.5, textColor=NAVY)
        payable_table = Table(
            [[Paragraph("Payable days", payable_style), Paragraph(payable_text, payable_style)]],
            colWidths=[130 * mm, 40 * mm],
        )
        payable_table.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F0F7")),
            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(payable_table)
        story.append(Spacer(1, 6 * mm))

    net_style = ParagraphStyle("net", fontName=FONT_BOLD, fontSize=13, textColor=NAVY)
    net_table = Table(
        [[Paragraph("Net pay", net_style), Paragraph(money(net_pay), net_style)]],
        colWidths=[130 * mm, 40 * mm],
    )
    net_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF6E3")),
        ("BOX", (0, 0), (-1, -1), 0.75, GOLD),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 6 * mm))

    if payment.paid_date:
        story.append(Paragraph(f"Paid on {payment.paid_date.strftime('%d %b %Y')}", h2))
        story.append(Spacer(1, 6 * mm))

    footer_rule = Table([[""]], colWidths=[A4[0] - 2 * doc.leftMargin])
    footer_rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, LINE)]))
    story.append(footer_rule)
    story.append(Spacer(1, 3 * mm))

    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    story.append(Paragraph("This is a system-generated payslip and does not require a signature.", footnote))
    story.append(Paragraph(f"Generated on {generated_at}", footnote))

    doc.build(story, onFirstPage=_draw_page_frame, onLaterPages=_draw_page_frame)
    return buffer.getvalue()
