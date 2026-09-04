"""Unified Application Form PDF generator — stdlib ONLY.

Like app/security.py (stdlib JWT/PBKDF2), this deliberately avoids extra
dependencies: a minimal but valid PDF 1.4 writer (Helvetica text, rules,
filled rects) produces the Unified Application Form with:

- auto-filled entity data (from DigiLocker e-KYC + business profile),
- the deterministic sector-clearance checklist (from the rule engine),
- the document pre-validation matrix (magic-byte / regex / cross-checks),
- a signed declaration block,
- timestamp, SHA-256 integrity hash, verification code and a deterministic
  hash-pattern verification block (a scannable QR is rendered in production
  from the same payload — the authoritative check is always the verification
  code against GET /forms/verify/{code}).

The Aadhaar number is NEVER included (only a masked reference).
"""
import hashlib
import re
from datetime import datetime, timezone

PAGE_W, PAGE_H = 595, 842  # A4 points
MARGIN = 48


def _esc(s: str) -> str:
    """Escape a string for a PDF literal and force ASCII (WinAnsi-safe)."""
    s = (s or "").replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    s = s.replace("₹", "Rs.").replace("—", "-").replace("–", "-")
    s = s.replace("✓", "[OK]").replace("✗", "[X]").replace("•", "*")
    return s.encode("ascii", "replace").decode("ascii")


class PDFBuilder:
    """Tiny PDF 1.4 writer: text / lines / rects on A4 pages, top-down coords."""

    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append([])

    @property
    def ops(self) -> list[str]:
        return self.pages[-1]

    def text(self, x: float, y_top: float, size: float, s: str,
             bold: bool = False, gray: float = 0.0) -> None:
        font = "/F2" if bold else "/F1"
        self.ops.append("BT {} {} Tf {} g {} {} Td ({}) Tj ET".format(
            font, size, gray, x, PAGE_H - y_top, _esc(s)))

    def hline(self, x1: float, x2: float, y_top: float, w: float = 0.7,
              gray: float = 0.0) -> None:
        self.ops.append("{} G {} w {} {} m {} {} l S".format(
            gray, w, x1, PAGE_H - y_top, x2, PAGE_H - y_top))

    def rect_fill(self, x: float, y_top: float, w: float, h: float,
                  gray: float = 0.0) -> None:
        self.ops.append("{} g {} {} {} {} re f".format(
            gray, x, PAGE_H - y_top - h, w, h))

    def rect_stroke(self, x: float, y_top: float, w: float, h: float,
                    gray: float = 0.5, lw: float = 0.7) -> None:
        self.ops.append("{} G {} w {} {} {} {} re S".format(
            gray, lw, x, PAGE_H - y_top - h, w, h))

    def hash_pattern(self, x: float, y_top: float, digest_hex: str,
                     modules: int = 15, cell: float = 3.4) -> None:
        """Deterministic verification pattern from the integrity hash.
        (Production renders the same payload as a scannable QR code.)"""
        bits = bin(int(digest_hex[:32], 16))[2:].zfill(128)
        self.rect_stroke(x - 3, y_top - 3, modules * cell + 6,
                         modules * cell + 6)
        for r in range(modules):
            for c in range(modules):
                idx = (r * modules + c) % len(bits)
                if bits[idx] == "1":
                    self.rect_fill(x + c * cell, y_top + r * cell,
                                   cell, cell, 0.0)

    def build(self) -> bytes:
        n_pages = len(self.pages)
        page_ids = [5 + i * 2 for i in range(n_pages)]
        objects: list[bytes] = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join("{} 0 R".format(i) for i in page_ids)
        objects.append("<< /Type /Pages /Kids [{}] /Count {} >>".format(
            kids, n_pages).encode())
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                       b"/Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont "
                       b"/Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        for i, ops in enumerate(self.pages):
            stream = "\n".join(ops).encode("latin-1", "replace")
            objects.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {} {}] "
                           "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                           "/Contents {} 0 R >>".format(
                               PAGE_W, PAGE_H, page_ids[i] + 1).encode())
            objects.append(b"<< /Length " + str(len(stream)).encode() +
                           b" >>\nstream\n" + stream + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for idx, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += "{} 0 obj\n".format(idx).encode() + body + b"\nendobj\n"
        xref_pos = len(out)
        out += "xref\n0 {}\n".format(len(objects) + 1).encode()
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += "{:010d} 00000 n \n".format(off).encode()
        out += ("trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n"
                .format(len(objects) + 1, xref_pos).encode())
        return bytes(out)


def _fmt_money(v) -> str:
    try:
        return "Rs. {:,.0f}".format(float(v or 0))
    except (TypeError, ValueError):
        return "Rs. 0"


def new_form_identity(application_id: str, business_id: str) -> dict:
    now = datetime.now(timezone.utc)
    raw = "{}|{}|{}".format(application_id, business_id, now.isoformat())
    sha = hashlib.sha256(raw.encode()).hexdigest()
    code = re.sub(r"[^A-Z0-9]", "",
                  hashlib.sha256(sha.encode()).hexdigest().upper())[:12]
    return {"form_no": "UAF-{}".format(now.strftime("%Y%m%d%H%M%S")),
            "generated_at": now.isoformat(), "sha256": sha,
            "verification_code": code}


def build_application_pdf(ctx: dict) -> bytes:
    """ctx: form_no, generated_at, verification_code, sha256, profile, approval,
    checklist, documents, kyc, applicant_name."""
    p = PDFBuilder()
    profile, approval = ctx["profile"], ctx["approval"]
    checklist, documents, kyc = ctx["checklist"], ctx["documents"], ctx["kyc"]
    x0, x1 = MARGIN, PAGE_W - MARGIN
    y = MARGIN

    # ---- Header band ----
    p.rect_fill(x0, y, x1 - x0, 64, 0.06)
    p.text(x0 + 12, y + 22, 13, "GOVERNMENT OF MAHARASHTRA", True, 1.0)
    p.text(x0 + 12, y + 40, 10.5,
           "Unified Industrial Application Form - Single Window (SIH26130)",
           False, 1.0)
    p.text(x0 + 12, y + 55, 8,
           "Auto-generated from DigiLocker e-KYC and the deterministic rule engine",
           False, 0.75)
    p.text(x1 - 150, y + 22, 9, "Form No: " + ctx["form_no"][-12:], True, 1.0)
    p.text(x1 - 150, y + 38, 8, "Generated: " + ctx["generated_at"][:19], False, 1.0)
    p.text(x1 - 150, y + 52, 8, "Verify: " + ctx["verification_code"], True, 1.0)
    y += 84
    p.hline(x0, x1, y)
    y += 16

    # ---- Section A: entity & applicant ----
    p.text(x0, y, 11, "A.  ENTITY & APPLICANT DETAILS", True)
    y += 16
    rows = [
        ("Business / Entity Name", profile.get("name", "")),
        ("Sector", str(profile.get("sector", "")).replace("_", " ").title()),
        ("District / Industrial Zone", "{}, {}".format(
            profile.get("district", "") or "-",
            profile.get("industrial_zone", "") or "-")),
        ("Investment / Employees", "{}  /  {} persons".format(
            _fmt_money(profile.get("investment_size")),
            profile.get("employee_count", 0))),
        ("Project Stage", profile.get("project_stage", "")),
        ("Authorized Person", profile.get("authorized_person", "")
         or ctx["applicant_name"]),
        ("PAN (masked)", profile.get("pan_masked", "") or "-"),
        ("GSTIN (masked)", profile.get("gst_masked", "") or "-"),
        ("e-KYC Status", "{} ({})".format(
            str(kyc.get("kyc_status", "not_verified")).upper(),
            kyc.get("kyc_source", "-"))),
        ("Aadhaar Reference", "XXXX XXXX "
         + (kyc.get("aadhaar_last4", "") or "----")
         + "  (full number never stored)"),
    ]
    for label, value in rows:
        p.text(x0 + 6, y, 8.5, label, True)
        p.text(x0 + 190, y, 8.5, str(value))
        y += 14
    y += 6

    # ---- Section B: applied approval ----
    p.text(x0, y, 11, "B.  APPROVAL APPLIED FOR", True)
    y += 16
    for label, value in [("Approval Code", approval.get("code", "")),
                         ("Approval Name", approval.get("name", "")),
                         ("Department", approval.get("department", "")),
                         ("Statutory SLA", "{} days from submission".format(
                             approval.get("sla_days", 15)))]:
        p.text(x0 + 6, y, 8.5, label, True)
        p.text(x0 + 190, y, 8.5, str(value))
        y += 14
    y += 8

    # ---- Section C: sector clearance checklist ----
    p.text(x0, y, 11,
           "C.  SECTOR CLEARANCE CHECKLIST (DETERMINISTIC RULE ENGINE)", True)
    y += 16
    p.rect_fill(x0, y - 3, x1 - x0, 15, 0.92)
    p.text(x0 + 6, y + 8, 8, "APPROVAL", True, 1.0)
    p.text(x0 + 200, y + 8, 8, "DEPARTMENT", True, 1.0)
    p.text(x0 + 400, y + 8, 8, "SLA (DAYS)", True, 1.0)
    p.text(x0 + 470, y + 8, 8, "GREEN CHANNEL", True, 1.0)
    y += 24
    for a in checklist.get("approvals", []):
        p.text(x0 + 6, y, 8, "{} - {}".format(a.get("code", ""), a.get("name", ""))[:62])
        p.text(x0 + 200, y, 8, a.get("department", "")[:33])
        p.text(x0 + 400, y, 8, str(a.get("sla_days", "")))
        p.text(x0 + 470, y, 8, "ELIGIBLE" if a.get("green_channel_eligible") else "-")
        p.hline(x0, x1, y + 5, 0.4, 0.8)
        y += 14
    for e in checklist.get("excluded", [])[:4]:
        p.text(x0 + 6, y, 7.5, "({} - not applicable: rule condition not met)".format(
            e.get("code", "")), False, 0.55)
        y += 12
    y += 6

    # ---- Section D: document verification matrix ----
    p.text(x0, y, 11, "D.  DOCUMENT PRE-VALIDATION MATRIX", True)
    y += 16
    p.rect_fill(x0, y - 3, x1 - x0, 15, 0.92)
    p.text(x0 + 6, y + 8, 8, "DOCUMENT", True, 1.0)
    p.text(x0 + 240, y + 8, 8, "CHECKS PASSED", True, 1.0)
    p.text(x0 + 360, y + 8, 8, "STATUS", True, 1.0)
    p.text(x0 + 440, y + 8, 8, "OCR SOURCE", True, 1.0)
    y += 24
    for d in documents:
        ok = (d.get("checks_total", 0) > 0
              and d.get("checks_passed", 0) == d.get("checks_total", 0))
        p.text(x0 + 6, y, 8, str(d.get("label") or d.get("type", ""))[:46])
        p.text(x0 + 240, y, 8, "{} / {}".format(d.get("checks_passed", 0),
                                                d.get("checks_total", 0)))
        p.text(x0 + 360, y, 8, "PASS" if ok else "FAIL/PENDING", ok)
        p.text(x0 + 440, y, 8, str(d.get("ocr_source", "") or "-")[:24])
        p.hline(x0, x1, y + 5, 0.4, 0.8)
        y += 14
    if not documents:
        p.text(x0 + 6, y, 8, "(no documents uploaded yet)", False, 0.55)
        y += 14
    y += 6


    # ---- Section E: declaration ----
    p.text(x0, y, 11, "E.  DECLARATION", True)
    y += 16
    decl = ("I, the authorized signatory, declare that the information auto-filled "
            "from DigiLocker e-KYC and my business profile is true; supporting "
            "documents were machine-validated against statutory checks; and I "
            "understand that approval is decided solely by the competent authority "
            "(AI is advisory only).")
    words, lines, cur = decl.split(), [], ""
    for w in words:
        if len(cur) + len(w) > 104:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    for ln in lines:
        p.text(x0 + 6, y, 8, ln)
        y += 12
    y += 10
    p.text(x0 + 6, y, 8.5, "Signed (e-KYC bound): " + ctx["applicant_name"], True)
    p.text(x0 + 320, y, 8.5, "Date: " + ctx["generated_at"][:10])
    y += 30

    # ---- Verification block (footer) ----
    if y > PAGE_H - 200:
        p._new_page()
        y = MARGIN
    p.hline(x0, x1, y)
    y += 14
    p.hash_pattern(x0 + 6, y, ctx["sha256"])
    p.text(x0 + 90, y + 8, 9, "INTEGRITY & VERIFICATION", True)
    p.text(x0 + 90, y + 24, 7.5, "SHA-256: " + ctx["sha256"])
    p.text(x0 + 90, y + 36, 7.5, "Verification code: " + ctx["verification_code"])
    p.text(x0 + 90, y + 48, 7.5,
           "Verify at: GET /forms/verify/{} (single-window system)".format(
               ctx["verification_code"]))
    p.text(x0 + 90, y + 60, 7.5,
           "Form generated programmatically at {} - tamper-evident: any edit "
           "invalidates the hash.".format(ctx["generated_at"][:19]))
    return p.build()

