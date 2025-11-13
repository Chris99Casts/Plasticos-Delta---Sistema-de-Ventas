import os, sys, subprocess
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr, code128
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

NOTAS_DIR = os.path.join(os.getcwd(), "Notas")


def _draw_code(c, folio: str, kind: str = "QR", *, size: int = 48, x: float = 0, y: float = 0):
    if kind.upper() == "QR":
        w = qr.QrCodeWidget(folio)
        bx, by, bw, bh = w.getBounds()
        sx = size / (bw - bx)
        sy = size / (bh - by)
        d = Drawing(size, size, transform=[sx, 0, 0, sy, 0, 0])
        d.add(w)
        renderPDF.draw(d, c, x, y)
    else:
        code = code128.Code128(folio, barHeight=size, barWidth=0.6, humanReadable=False)
        code.drawOn(c, x, y)


def _draw_cancel_watermark(c: canvas.Canvas, page_w: float, page_h: float):
    """
    Marca 'CANCELADO' en diagonal, rojo con transparencia si está disponible.
    """
    c.saveState()
    # Transparencia (si la versión de reportlab lo soporta)
    try:
        c.setFillAlpha(0.18)
    except Exception:
        pass
    c.setFillColorRGB(1, 0, 0)
    c.setStrokeColorRGB(1, 0, 0)
    c.setFont("Helvetica-Bold", 72)
    c.translate(page_w / 2, page_h / 2)
    c.rotate(35)
    text = "CANCELADO"
    tw = c.stringWidth(text, "Helvetica-Bold", 72)
    c.drawString(-tw / 2, -20, text)
    c.restoreState()

def generar_pdf_pedido(
    *,
    id_pedido: str,
    cliente: str,
    fecha_str: str,
    items: list[dict],
    logo_path: str = "logo.png",
    qr_kind: str = "QR",
    cancelado: bool = False,
) -> str:
    """
    items: [{cantidad:int, producto:str, precio_unitario:str/float, importe:str/float}, ...]
    Devuelve la ruta del PDF generado. Sobrescribe si existe.
    """
    os.makedirs(NOTAS_DIR, exist_ok=True)
    nombre_pdf = f"Nota_{id_pedido}_{cliente.replace(' ', '_')}.pdf"
    pdf_path = os.path.join(NOTAS_DIR, nombre_pdf)

    page_w, page_h = (letter[0] / 2, letter[1] / 2)
    c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))
    margin = 20

    # Fecha visible
    try:
        fecha_vis = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y")
    except Exception:
        fecha_vis = fecha_str

    # ----------------- HELPERS -----------------

    def dibujar_encabezado() -> float:
        """Logo, QR, fecha, N° nota y cliente. Regresa y_head."""
        # Logo
        if os.path.exists(logo_path):
            c.drawImage(
                logo_path,
                -20,
                page_h - 66,
                width=200,
                height=90,
                preserveAspectRatio=True,
                mask="auto",
            )
        else:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, page_h - 20, "Plásticos Delta")

        # QR / código
        qr_size = 48
        qr_x = page_w - margin - qr_size
        qr_y = page_h - margin - qr_size
        _draw_code(c, id_pedido, kind=qr_kind, size=qr_size, x=qr_x, y=qr_y)

        # Base del encabezado
        gap = 10
        y_head_local = qr_y - gap
        if y_head_local > (page_h - 66):
            y_head_local = page_h - 66

        # CANCELADO en marca de agua (cada página)
        if cancelado:
            _draw_cancel_watermark(c, page_w, page_h)

        # Fecha y folio
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - margin, y_head_local, f"Fecha: {fecha_vis}")
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(page_w - 95, y_head_local - 14, "N° Nota:")
        c.setFillColorRGB(1, 0, 0)
        c.drawRightString(page_w - margin, y_head_local - 14, id_pedido)
        c.setFillColorRGB(0, 0, 0)

        # Cliente
        c.drawString(40, y_head_local, f"Cliente: {cliente}")

        return y_head_local

    def dibujar_cabecera_tabla(y_top: float) -> float:
        """Encabezado de la tabla, regresa y inicial para filas."""
        y_local = y_top - 25
        c.line(40, y_local + 10, page_w - 25, y_local + 10)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(45, y_local, "CANT.")
        c.drawString(85, y_local, "PRODUCTO")
        c.drawString(185, y_local, "P.UNIT")
        c.drawString(230, y_local, "IMPORTE")
        y_local -= 10
        c.line(40, y_local, page_w - 25, y_local)
        c.setFont("Helvetica", 9)
        return y_local

    def dibujar_footer():
        """12 recuadros + línea punteada + RECIBIDO, en todas las páginas."""
        tabla_ancho = 110   # ancho de cada bloque
        tabla_alto = 55     # alto de cada bloque
        filas = 3
        cols = 2
        espacio = 20        # espacio entre tablas

        y_tablas = 75
        x1 = 40
        x2 = x1 + tabla_ancho + espacio

        def dibujar_tabla(x, y0):
            c.rect(x, y0, tabla_ancho, tabla_alto)
            col_w = tabla_ancho / cols
            row_h = tabla_alto / filas

            # columna central
            c.line(x + col_w, y0, x + col_w, y0 + tabla_alto)
            # filas horizontales
            for i in range(1, filas):
                c.line(x, y0 + i * row_h, x + tabla_ancho, y0 + i * row_h)

        # dos tablas = 12 recuadros
        dibujar_tabla(x1, y_tablas)
        dibujar_tabla(x2, y_tablas)

        # línea punteada + texto
        y_rec = 40
        c.setDash(3, 3)
        c.line(35, y_rec, page_w - 35, y_rec)
        c.setDash()
        c.setFont("Helvetica-Bold", 10)
        c.drawString(35, y_rec - 12, "RECIBIDO")

    # ----------------- CONTENIDO -----------------

    total = 0.0
    max_items_por_hoja = 9
    n_items = len(items)

    indice = 0
    primera_hoja = True
    y = 0

    while indice < n_items or primera_hoja:
        if not primera_hoja:
            c.showPage()
        primera_hoja = False

        # Encabezado + footer en CADA página
        y_head = dibujar_encabezado()
        dibujar_footer()

        # Cabecera de tabla
        y = dibujar_cabecera_tabla(y_head)

        # Filas de ESTA página
        filas_en_esta_hoja = 0
        while indice < n_items and filas_en_esta_hoja < max_items_por_hoja:
            it = items[indice]
            indice += 1
            filas_en_esta_hoja += 1

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
            c.drawString(45, y, str(cant))
            c.drawString(85, y, prod[:24])
            c.drawRightString(225, y, f"${punit:,.2f}")
            c.drawRightString(270, y, f"${imp:,.2f}")
            c.line(40, y - 5, page_w - 25, y - 5)

        if indice >= n_items:
            break

    # ÚLTIMA PÁGINA: solo aquí va el TOTAL (los recuadros ya se dibujaron)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(page_w - 25, y - 20, f"TOTAL: ${total:,.2f}")

    c.save()
    return pdf_path




def abrir_pdf(pdf_path: str):
    try:
        if os.name == "nt":
            os.startfile(pdf_path)  # type: ignore
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path], check=False)
        else:
            subprocess.run(["xdg-open", pdf_path], check=False)
    except Exception:
        pass
