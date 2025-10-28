from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import os, sys, subprocess

def generar_pdf(cliente, productos, total, logo_path, notas_dir):
    numero_nota = datetime.now().strftime("%Y%m%d%H%M%S")
    fecha = datetime.now().strftime("%d/%m/%Y")
    os.makedirs(notas_dir, exist_ok=True)
    pdf_path = os.path.join(notas_dir, f"Nota_{numero_nota}_{cliente.replace(' ', '_')}.pdf")

    c = canvas.Canvas(pdf_path, pagesize=(letter[0]/2, letter[1]/2))
    if os.path.exists(logo_path):
        c.drawImage(logo_path, -20, 330, width=200, height=90, mask='auto')
    else:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, 380, "Plásticos Delta")

    c.setFont("Helvetica", 9)
    c.drawString(40, 335, f"Cliente: {cliente}")
    c.drawRightString(270, 345, f"Fecha: {fecha}")
    c.drawRightString(290, 335, numero_nota)

    y = 315
    c.line(40, y+10, 270, y+10)
    c.drawString(45, y, "CANT.")
    c.drawString(85, y, "PRODUCTO")
    c.drawString(185, y, "P.UNIT")
    c.drawString(230, y, "IMPORTE")
    y -= 10
    c.line(40, y, 270, y)

    for cant, prod, prec, imp in productos:
        y -= 15
        if y < 60:
            c.showPage()
            y = 380
        c.drawString(45, y, str(cant))
        c.drawString(85, y, str(prod)[:14])
        c.drawRightString(225, y, f"${prec:,.2f}")
        c.drawRightString(270, y, f"${imp:,.2f}")
        c.line(40, y-5, 270, y-5)

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(270, y-20, f"TOTAL: ${total:,.2f}")
    c.save()

    try:
        if os.name == 'nt':
            os.startfile(pdf_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path])
        else:
            subprocess.run(["xdg-open", pdf_path])
    except:
        pass
