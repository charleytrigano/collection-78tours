"""Catalogue PDF de la collection : avec ou sans prix, avec ou sans photos."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

INK = colors.HexColor("#1f1a17")
MUTED = colors.HexColor("#6b625b")
ACCENT = colors.HexColor("#8a1c1c")
RULE = colors.HexColor("#d9d2c9")
PAPER = colors.HexColor("#f6f2ec")

_ss = getSampleStyleSheet()
S = {
    "cover_title": ParagraphStyle("ct", parent=_ss["Title"], fontName="Helvetica-Bold", fontSize=30, leading=36,
                                  textColor=INK, alignment=TA_CENTER),
    "cover_sub": ParagraphStyle("cs", parent=_ss["Normal"], fontSize=13, leading=18, textColor=MUTED,
                                alignment=TA_CENTER),
    "num": ParagraphStyle("num", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT),
    "head": ParagraphStyle("head", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=12.5, leading=15,
                           textColor=INK),
    "side": ParagraphStyle("side", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=MUTED,
                           spaceBefore=2),
    "title": ParagraphStyle("title", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                            textColor=INK),
    "body": ParagraphStyle("body", parent=_ss["Normal"], fontSize=9, leading=12, textColor=INK),
    "small": ParagraphStyle("small", parent=_ss["Normal"], fontSize=8, leading=10.5, textColor=MUTED),
    "pres": ParagraphStyle("pres", parent=_ss["Normal"], fontName="Helvetica-Oblique", fontSize=8, leading=10.5,
                           textColor=INK),
    "price": ParagraphStyle("price", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=10.5, textColor=ACCENT),
    "th": ParagraphStyle("th", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=colors.white),
    "td": ParagraphStyle("td", parent=_ss["Normal"], fontSize=8, leading=10, textColor=INK),
}


def _t(value):
    """Texte sûr pour Helvetica (Latin-1 étendu) et pour le balisage de Paragraph."""
    s = str(value or "").strip()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.encode("cp1252", "replace").decode("cp1252")
    return escape(s)


def _price(r):
    lo, hi = r.get("_basse"), r.get("_haute")
    if lo is None or lo != lo:  # NaN
        return ""
    return f"{lo:,.0f} €".replace(",", " ") if lo == hi else f"{lo:,.0f} – {hi:,.0f} €".replace(",", " ")


def _photo(data, max_w, max_h):
    if not data:
        return None
    try:
        im = ImageOps.exif_transpose(PILImage.open(io.BytesIO(data))).convert("RGB")
    except Exception:
        return None
    im.thumbnail((900, 900))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    buf.seek(0)
    ratio = min(max_w / im.width, max_h / im.height)
    return Image(buf, width=im.width * ratio, height=im.height * ratio)


def _subtitle(r):
    return " · ".join(_t(r.get(k)) for k in ("label_marque", "reference_disque", "annee") if r.get(k))


def _face_block(r, side, with_pres):
    items = [Paragraph(f"FACE {side.upper()}", S["side"]),
             Paragraph(_t(r.get(f"titre_face_{side}")) or "<i>Titre inconnu</i>", S["title"])]
    if r.get(f"interprete_face_{side}"):
        items.append(Paragraph(_t(r.get(f"interprete_face_{side}")), S["body"]))
    if with_pres and r.get(f"presentation_face_{side}"):
        items += [Spacer(1, 3), Paragraph(_t(r.get(f"presentation_face_{side}")), S["pres"])]
    return items


def _card(i, r, with_prices, with_photos, with_pres, load_photo, width):
    head = [Paragraph(f"N° {i}", S["num"]), Paragraph(_subtitle(r) or "Disque", S["head"])]
    meta = [x for x in (r.get("orchestre") and f"Orchestre : {_t(r['orchestre'])}",
                        r.get("auteurs") and f"Auteurs : {_t(r['auteurs'])}",
                        r.get("etat") and f"État : {_t(r['etat'])}",
                        r.get("pochette") and f"Pochette : {_t(r['pochette'])}") if x]
    col_w = (width - 0.6 * cm) / 2
    rows = []
    if with_photos:
        pics = [_photo(load_photo(r.get(k)), col_w - 0.2 * cm, 6.2 * cm) if r.get(k) else None
                for k in ("photo_etiquette", "photo_face_b")]
        if any(pics):
            rows.append([p or Paragraph("Pas de photo", S["small"]) for p in pics])
    rows.append([_face_block(r, "a", with_pres), _face_block(r, "b", with_pres)])
    faces = Table(rows, colWidths=[col_w, col_w])
    faces.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    footer_left = Paragraph(" &nbsp;·&nbsp; ".join(meta), S["small"])
    footer = Table([[footer_left, Paragraph(_price(r), S["price"]) if with_prices else ""]],
                   colWidths=[width - 4 * cm, 4 * cm])
    footer.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    box = Table([[head], [faces], [footer]], colWidths=[width])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, RULE), ("BACKGROUND", (0, 0), (-1, 0), PAPER),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                             ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE)]))
    return KeepTogether([box, Spacer(1, 0.45 * cm)])


def _list_table(df, with_prices, width):
    head = ["N°", "Face A", "Face B", "Label · Réf. · Année", "État"] + (["Estimation"] if with_prices else [])
    data = [[Paragraph(h, S["th"]) for h in head]]
    for i, r in enumerate(df.to_dict("records"), 1):
        fa = f"<b>{_t(r.get('titre_face_a'))}</b><br/>{_t(r.get('interprete_face_a'))}"
        fb = f"<b>{_t(r.get('titre_face_b'))}</b><br/>{_t(r.get('interprete_face_b'))}"
        row = [str(i), fa, fb, _subtitle(r), _t(r.get("etat"))] + ([_price(r)] if with_prices else [])
        data.append([Paragraph(x, S["td"]) for x in row])
    fixed = [0.9 * cm, None, None, 4.2 * cm, 2.2 * cm] + ([2.4 * cm] if with_prices else [])
    free = (width - sum(w for w in fixed if w)) / 2
    t = Table(data, colWidths=[w or free for w in fixed], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE)]))
    return t


def build_catalogue(df, with_prices=True, with_photos=True, with_pres=False, title="Ma collection de 78 tours",
                    load_photo=lambda path: None):
    """df : DataFrame préparé (colonnes de la table + _basse/_haute). load_photo(path) → octets de l'image."""
    df = df.copy()
    text_cols = [c for c in df.columns if not str(c).startswith("_")]
    df[text_cols] = df[text_cols].fillna("").astype(str).replace({"nan": "", "None": ""})
    buf = io.BytesIO()
    margin = 1.6 * cm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=margin, title=title, author="Collection 78 tours")
    width = A4[0] - 2 * margin

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, 1 * cm, _t(title).replace("&amp;", "&"))
        canvas.drawRightString(A4[0] - margin, 1 * cm, f"Page {d.page}")
        canvas.restoreState()

    n = len(df)
    story = [Spacer(1, 6 * cm), Paragraph(_t(title), S["cover_title"]), Spacer(1, 0.6 * cm),
             Paragraph(f"{n} disque{'s' if n > 1 else ''} 78 tours", S["cover_sub"]),
             Paragraph(datetime.now().strftime("Catalogue établi le %d/%m/%Y"), S["cover_sub"])]
    if with_prices:
        lo, hi = df["_basse"].sum(min_count=1), df["_haute"].sum(min_count=1)
        if lo == lo and lo is not None:
            story += [Spacer(1, 1 * cm), Paragraph(
                f"Valeur indicative estimée : {lo:,.0f} – {hi:,.0f} €".replace(",", " "), S["cover_sub"]),
                Paragraph("Estimations indicatives, sans valeur d'expertise.", S["small"])]
    story.append(PageBreak())

    if with_photos or with_pres:
        for i, r in enumerate(df.to_dict("records"), 1):
            story.append(_card(i, r, with_prices, with_photos, with_pres, load_photo, width))
    else:
        story.append(_list_table(df, with_prices, width))

    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=footer)
    return buf.getvalue()
