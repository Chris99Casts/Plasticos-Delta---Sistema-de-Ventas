from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import os, sys, subprocess
from data.paths import NOTAS_DIR

def generar_pdf(cliente, productos, total, logo_path, notas_dir):
    numero_nota = datetime.now().strftime("%Y%m%d%H%M%S")
    fecha = datetime.now().strftime("%d/%m/%Y")
    os.makedirs(notas_dir, exist_ok=True)
    pdf_path = os.path.join(
        notas_dir,
        f"Nota_{numero_nota}_{cliente.replace(' ', '_')}.pdf"
    )

    # Media carta
    page_w, page_h = letter[0] / 2, letter[1] / 2
    c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

    # Logo / título
    if os.path.exists(logo_path):
        c.drawImage(logo_path, -20, page_h - 110, width=200, height=90, mask='auto')
    else:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, page_h - 40, "Plásticos Delta")

    # Datos cabecera
    c.setFont("Helvetica", 9)
    c.drawString(40, page_h - 85, f"Cliente: {cliente}")
    c.drawRightString(page_w - 40, page_h - 75, f"Fecha: {fecha}")
    c.drawRightString(page_w - 20, page_h - 85, numero_nota)

    # Encabezados tabla
    y = page_h - 115
    c.line(40, y + 10, page_w - 40, y + 10)
    c.drawString(45, y, "CANT.")
    c.drawString(85, y, "PRODUCTO")
    c.drawString(page_w - 125, y, "P.UNIT")
    c.drawString(page_w - 70, y, "IMPORTE")
    y -= 10
    c.line(40, y, page_w - 40, y)

    # Filas
    for cant, prod, prec, imp in productos:
        y -= 15
        if y < 80:
            c.showPage()
            y = page_h - 40

        c.drawString(45, y, str(cant))
        c.drawString(85, y, str(prod)[:18])
        c.drawRightString(page_w - 75, y, f"${prec:,.2f}")
        c.drawRightString(page_w - 40, y, f"${imp:,.2f}")
        c.line(40, y - 5, page_w - 40, y - 5)

    # TOTAL
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(page_w - 40, y - 20, f"TOTAL: ${total:,.2f}")

    # 12 RECUADROS (dos tablas de 3x2)
    tabla_ancho = 130
    tabla_alto = 55
    filas = 3
    cols = 2
    espacio_entre_tablas = 25

    y_tablas = 70
    x_tabla_izq = 40
    x_tabla_der = x_tabla_izq + tabla_ancho + espacio_entre_tablas

    def dibujar_tabla(x0, y0):
        c.rect(x0, y0, tabla_ancho, tabla_alto)
        col_width = tabla_ancho / cols
        row_height = tabla_alto / filas
        c.line(x0 + col_width, y0, x0 + col_width, y0 + tabla_alto)
        for i in range(1, filas):
            c.line(x0, y0 + i * row_height, x0 + tabla_ancho, y0 + i * row_height)

    dibujar_tabla(x_tabla_izq, y_tablas)
    dibujar_tabla(x_tabla_der, y_tablas)

    # Línea punteada y "RECIBIDO"
    y_recibido = 40
    x_linea_ini = 30
    x_linea_fin = page_w - 30

    c.setDash(3, 3)
    c.line(x_linea_ini, y_recibido, x_linea_fin, y_recibido)
    c.setDash()

    # TOTAL
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(page_w - 25, y - 20, f"TOTAL: ${total:,.2f}")

    # -------------------------------------------------
    #  12 RECUADROS (dos tablas de 3x2)
    # -------------------------------------------------
    tabla_ancho = 130   # ancho de cada bloque
    tabla_alto = 55     # alto de cada bloque
    filas = 3
    cols = 2
    espacio_entre_tablas = 25

    y_tablas = 70       # altura desde la parte de abajo
    x_tabla_izq = 40
    x_tabla_der = x_tabla_izq + tabla_ancho + espacio_entre_tablas

    def dibujar_tabla(x0, y0):
        c.rect(x0, y0, tabla_ancho, tabla_alto)
        col_width = tabla_ancho / cols
        row_height = tabla_alto / filas
        c.line(x0 + col_width, y0, x0 + col_width, y0 + tabla_alto)
        for i in range(1, filas):
            c.line(x0, y0 + i * row_height, x0 + tabla_ancho, y0 + i * row_height)

    # dos tablas de 3x2 = 12 recuadros
    dibujar_tabla(x_tabla_izq, y_tablas)
    dibujar_tabla(x_tabla_der, y_tablas)

    # -------------------------------------------------
    #  LÍNEA PUNTEADA Y TEXTO "RECIBIDO"
    # -------------------------------------------------
    y_recibido = 40
    x_linea_ini = 35
    x_linea_fin = page_w - 35

    c.setDash(3, 3)
    c.line(x_linea_ini, y_recibido, x_linea_fin, y_recibido)
    c.setDash()

    c.setFont("Helvetica-Bold", 9)
    c.drawString(x_linea_ini, y_recibido - 12, "RECIBIDO")

    # FIN DEL PDF
    c.save()
    return pdf_path


    try:
        if os.name == "nt":
            os.startfile(pdf_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path])
        else:
            subprocess.run(["xdg-open", pdf_path])
    except:
        pass

    return pdf_path