# ui/pdf_utils.py
import os, sys, subprocess
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr, code128
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

# Carpeta de salida
NOTAS_DIR = os.path.join(os.getcwd(), "Notas")

# --- Resolución robusta de rutas de assets (logo) ---
def _resolve_logo_path(logo_path: str | None) -> str | None:
    """
    Devuelve una ruta absoluta válida para el logo o None si no se encuentra.
    Busca en ./assets y ./assests además de la ruta dada.
    """
    if not logo_path:
        candidate_name = "logo.png"
    else:
        candidate_name = logo_path

    # Si es ruta absoluta y existe, listo
    if os.path.isabs(candidate_name) and os.path.exists(candidate_name):
        return candidate_name

    # Si es relativa, probamos varios lugares
    base_here = os.path.dirname(os.path.abspath(__file__))         # ui/
    project_root = os.path.normpath(os.path.join(base_here, "..")) # raíz del proyecto

    candidates = []

    # si ya vino como "algo/algo.png", pruébalo relativo al CWD y a raíz
    candidates.append(os.path.join(os.getcwd(), candidate_name))
    candidates.append(os.path.join(project_root, candidate_name))

    # nombres típicos de carpeta
    for assets_dir in ("assets", "assests"):  # soporta ambos nombres
        candidates.append(os.path.join(os.getcwd(), assets_dir, os.path.basename(candidate_name)))
        candidates.append(os.path.join(project_root, assets_dir, os.path.basename(candidate_name)))

    # primera que exista
    for p in candidates:
        if os.path.exists(p):
            return p

    return None

def _draw_code(c, folio: str, kind: str = "QR", *, size: int = 48, x: float = 0, y: float = 0):
    if kind.upper() == "QR":
        w = qr.QrCodeWidget(folio)
        bx, by, bw, bh = w.getBounds()
        sx = size / (bw - bx); sy = size / (bh - by)
        d = Drawing(size, size, transform=[sx, 0, 0, sy, 0, 0])
        d.add(w)
        renderPDF.draw(d, c, x, y)
    else:
        code = code128.Code128(folio, barHeight=size, barWidth=0.6, humanReadable=False)
        code.drawOn(c, x, y)

def generar_pdf_pedido(*, id_pedido: str, cliente: str, fecha_str: str,
                       items: list[dict], logo_path: str | None = "logo.png",
                       qr_kind: str = "QR") -> str:
    """
    Genera PDF en media carta (letter/2).
    items: [{cantidad:int, producto:str, precio_unitario:str/float, importe:str/float}, ...]
    Devuelve la ruta del PDF generado. Sobrescribe si existe.
    """
    os.makedirs(NOTAS_DIR, exist_ok=True)
    nombre_pdf = f"Nota_{id_pedido}_{cliente.replace(' ', '_')}.pdf"
    pdf_path = os.path.join(NOTAS_DIR, nombre_pdf)

    page_w, page_h = (letter[0] / 2, letter[1] / 2)
    c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

    # --- LOGO (arriba izquierda) ---
    resolved_logo = _resolve_logo_path(logo_path)
    if resolved_logo:
        # Ajuste típico del logo en esta plantilla
        try:
            c.drawImage(resolved_logo, -20, page_h - 66, width=200, height=90,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            # Si falla la imagen (formato, etc.), mostramos fallback de texto
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, page_h - 20, "Plásticos Delta")
    else:
        # Fallback si no se encuentra el archivo
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, page_h - 20, "Plásticos Delta")

    # --- QR/código en esquina superior derecha ---
    qr_size = 48
    margin = 20
    qr_x = page_w - margin - qr_size
    qr_y = page_h - margin - qr_size
    _draw_code(c, id_pedido, kind=qr_kind, size=qr_size, x=qr_x, y=qr_y)

    # --- Encabezado debajo del QR (evita encimar fecha/folio con el QR) ---
    gap = 10
    y_head = qr_y - gap
    if y_head > (page_h - 66):  # por si el logo quedó más alto
        y_head = page_h - 66

    # Fecha y folio
    c.setFont("Helvetica", 9)
    try:
        fecha_fmt = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y")
    except Exception:
        fecha_fmt = fecha_str
    c.drawRightString(page_w - margin, y_head, f"Fecha: {fecha_fmt}")
    c.setFillColorRGB(0, 0, 0)
    c.drawRightString(page_w - 95, y_head - 14, "N° Nota:")
    c.setFillColorRGB(1, 0, 0)
    c.drawRightString(page_w - margin, y_head - 14, id_pedido)
    c.setFillColorRGB(0, 0, 0)

    # Cliente
    c.drawString(40, y_head, f"Cliente: {cliente}")

    # --- Cabecera de tabla ---
    y = y_head - 25
    c.line(40, y + 10, page_w - 25, y + 10)
    c.drawString(45, y, "CANT.")
    c.drawString(85, y, "PRODUCTO")
    c.drawString(185, y, "P.UNIT")
    c.drawString(230, y, "IMPORTE")
    y -= 10
    c.line(40, y, page_w - 25, y)

    # --- Filas ---
    total = 0.0
    for it in items:
        try:
            cant = int(it.get("cantidad") or 0)
        except Exception:
            cant = 0
        prod = str(it.get("producto") or "")
        try:
            punit = float(str(it.get("precio_unitario") or "0").replace("$", "").replace(",", ""))
        except Exception:
            punit = 0.0
        try:
            imp = float(str(it.get("importe") or "0").replace("$", "").replace(",", ""))
        except Exception:
            imp = cant * punit
        total += imp

        y -= 15
        if y < 60:
            c.showPage()
            y = page_h - 16
        c.drawString(45, y, str(cant))
        c.drawString(85, y, prod[:24])
        c.drawRightString(225, y, f"${punit:,.2f}")
        c.drawRightString(270, y, f"${imp:,.2f}")
        c.line(40, y - 5, page_w - 25, y - 5)

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(page_w - 25, y - 20, f"TOTAL: ${total:,.2f}")
    c.save()
    return pdf_path

def abrir_pdf(pdf_path: str):
    try:
        if os.name == 'nt':
            os.startfile(pdf_path)  # type: ignore
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path], check=False)
        else:
            subprocess.run(["xdg-open", pdf_path], check=False)
    except Exception:
        pass
