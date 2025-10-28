import os, sys, subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from ui.pdf_utils import generar_pdf_pedido, abrir_pdf
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr, code128
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from data.csv_manager import generar_id_pedido_ym





# Asegura import relativo cuando se ejecuta desde main.py
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from data.csv_manager import (
    cargar_productos,
    registrar_pedido as registrar_pedido_csv,
    generar_id_pedido_ym,
)

NOTAS_DIR = os.path.join(os.getcwd(), "Notas")


class TabNuevaNota:
    def __init__(self,
                 notebook,
                 frame_style="Dark.TFrame",
                 button_style="Dark.TButton",
                 label_style="Dark.TLabel",
                 entry_style="Dark.TEntry",
                 check_style="Dark.TCheckbutton",
                 on_refresh_all=None,
                 tree_style="Dark.Treeview"):
        self.frame_style = frame_style
        self.button_style = button_style
        self.label_style = label_style
        self.entry_style = entry_style
        self.check_style = check_style
        self.tree_style = tree_style
        self.on_refresh_all = on_refresh_all

        self.frame = ttk.Frame(notebook, style=self.frame_style)

        # Estado
        self.cliente = tk.StringVar()
        self.descuento = tk.BooleanVar(value=False)
        self.producto_var = tk.StringVar()

        self.logo_path = "logo.png"
        os.makedirs(NOTAS_DIR, exist_ok=True)
        self._folio_actual = None  # Folio mensual compartido PDF/Registro

        # Cargar catálogo
        self.productos_data = self._cargar_catalogo()
        self.nombres_productos = [p["producto"] for p in self.productos_data]

        self.crear_ui()
# ------------------- Emitir refresh ----------------------        
    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()


    # ------------------------- UI -------------------------
    def crear_ui(self):
        # Fila 0
        ttk.Label(self.frame, text="Cliente:", style=self.label_style)\
            .grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.entry_cliente = ttk.Entry(self.frame, textvariable=self.cliente, width=40, style=self.entry_style)
        self.entry_cliente.grid(row=0, column=1, columnspan=3, pady=10, sticky="w")

        self.chk_desc = ttk.Checkbutton(self.frame, text="Cliente con Descuento",
                                        variable=self.descuento, command=self.actualizar_precio,
                                        style=self.check_style)
        self.chk_desc.grid(row=0, column=5, padx=10, sticky="w")

        # Fila 1
        ttk.Label(self.frame, text="Cantidad:", style=self.label_style)\
            .grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.cantidad_entry = ttk.Entry(self.frame, width=10, style=self.entry_style)
        self.cantidad_entry.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        ttk.Label(self.frame, text="Producto:", style=self.label_style)\
            .grid(row=1, column=2, padx=10, pady=10, sticky="e")
        self.producto_entry = ttk.Entry(self.frame, textvariable=self.producto_var, width=30, style=self.entry_style)
        self.producto_entry.grid(row=1, column=3, padx=10, pady=10, sticky="w")
        self.producto_entry.bind("<KeyRelease>", self.autocompletar_producto)

        ttk.Label(self.frame, text="Precio Unitario:", style=self.label_style)\
            .grid(row=1, column=4, padx=10, pady=10, sticky="e")
        self.precio_entry = ttk.Entry(self.frame, width=10, style=self.entry_style)
        self.precio_entry.grid(row=1, column=5, padx=10, pady=10, sticky="w")

        self.btn_agregar = ttk.Button(self.frame, text="Agregar", command=self.agregar_producto, style=self.button_style)
        self.btn_agregar.grid(row=1, column=6, padx=10, pady=10)
        self.btn_eliminar = ttk.Button(self.frame, text="Eliminar", command=self.eliminar_producto, style=self.button_style)
        self.btn_eliminar.grid(row=2, column=6, padx=10, pady=10)

        # Lista de autocompletado
        self.lista_sugerencias = tk.Listbox(self.frame, height=4, bg="#2d2d2d", fg="white")
        self.lista_sugerencias.grid(row=2, column=3, padx=10, sticky="w")
        self.lista_sugerencias.bind("<<ListboxSelect>>", self.seleccionar_producto)
        self.lista_sugerencias.grid_remove()

        # Tabla
        self.tree = ttk.Treeview(self.frame,
                                 columns=("cantidad", "producto", "precio", "importe"),
                                 show="headings", height=12, style=self.tree_style)
        for col in ("cantidad", "producto", "precio", "importe"):
            self.tree.heading(col, text=col.capitalize())
            self.tree.column(col, anchor="center")
        self.tree.grid(row=3, column=0, columnspan=7, padx=15, pady=15, sticky="nsew")

        # Botones de acción


        # Registrar Pedido
        self.btn_reg = ttk.Button(self.frame, text="Registrar Pedido",
                                  command=self.registrar_pedido, style=self.button_style)
        self.btn_reg.grid(row=4, column=2, columnspan=2, pady=15, sticky="w")

        # Editar CSV
        self.btn_csv = ttk.Button(self.frame, text="Editar Productos CSV",
                                  command=self.abrir_csv, style=self.button_style)
        self.btn_csv.grid(row=4, column=6, sticky="e", padx=15)

        # Bind Enter
        self.cantidad_entry.bind("<Return>", self.agregar_producto_event)
        self.producto_entry.bind("<Return>", self.agregar_producto_event)
        self.precio_entry.bind("<Return>", self.agregar_producto_event)

        # Expandir tabla
        for i in range(7):
            self.frame.grid_columnconfigure(i, weight=1)
        self.frame.grid_rowconfigure(3, weight=1)

    # ----------------------- Catálogo -----------------------
    def _cargar_catalogo(self):
        try:
            data = cargar_productos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer productos.csv\n{e}")
            data = []
        return data

    # ------------------- Autocompletado ---------------------
    def autocompletar_producto(self, event=None):
        texto = (self.producto_var.get() or "").lower().strip()
        if texto == "":
            self.lista_sugerencias.grid_remove()
            return
        coincidencias = [p for p in self.nombres_productos if texto in p.lower()]
        self.lista_sugerencias.delete(0, tk.END)
        for c in coincidencias:
            self.lista_sugerencias.insert(tk.END, c)
        if coincidencias:
            self.lista_sugerencias.grid()
        else:
            self.lista_sugerencias.grid_remove()
        self.actualizar_precio()

    def seleccionar_producto(self, event=None):
        seleccion = self.lista_sugerencias.curselection()
        if seleccion:
            producto = self.lista_sugerencias.get(seleccion[0])
            self.producto_var.set(producto)
            self.lista_sugerencias.grid_remove()
            self.actualizar_precio()

    def actualizar_precio(self):
        nombre = (self.producto_var.get() or "").strip().lower()
        for p in self.productos_data:
            if (p.get("producto","").lower() == nombre):
                try:
                    base = p.get("precio_desc") if self.descuento.get() else p.get("precio")
                    precio = float((base or "0").replace(",", "."))
                except Exception:
                    precio = 0.0
                self.precio_entry.delete(0, tk.END)
                self.precio_entry.insert(0, f"{precio:.2f}")
                return

    # ------------------- Tabla líneas -----------------------
    def agregar_producto(self):
        try:
            cantidad = int(self.cantidad_entry.get())
            producto = (self.producto_var.get() or "").strip()
            precio = float(str(self.precio_entry.get() or "0").replace("$", "").replace(",", ""))
            importe = cantidad * precio
            if not producto:
                messagebox.showerror("Error", "Debe ingresar un nombre de producto.")
                return
            self.tree.insert("", "end", values=(cantidad, producto, f"${precio:,.2f}", f"${importe:,.2f}"))
            self.cantidad_entry.delete(0, tk.END)
            self.producto_entry.delete(0, tk.END)
            self.precio_entry.delete(0, tk.END)
            self.lista_sugerencias.grid_remove()
            self.cantidad_entry.focus()
        except ValueError:
            messagebox.showerror("Error", "Verifica los valores ingresados")

    def agregar_producto_event(self, event):
        self.agregar_producto()

    def eliminar_producto(self):
        seleccionado = self.tree.selection()
        if not seleccionado:
            messagebox.showwarning("Atención", "Seleccione un producto para eliminar.")
            return
        for item in seleccionado:
            self.tree.delete(item)

    # -------------------- Utilidades ------------------------
    def _parse_float(self, s):
        try:
            return float(str(s).replace("$","").replace(",","").strip() or "0")
        except Exception:
            return 0.0

    # ------------------- Generar PDF ------------------------
    def generar_pdf(self):
        cliente = (self.cliente.get() or "").strip()
        fecha_vis = datetime.now().strftime("%d/%m/%Y")

        productos = []
        total = 0.0
        for iid in self.tree.get_children():
            vals = self.tree.item(iid)["values"]  # (cantidad, producto, precio, importe)
            if not vals or len(vals) < 4:
                continue
            cantidad = int(vals[0])
            producto = str(vals[1])
            precio = self._parse_float(vals[2])
            importe = self._parse_float(vals[3])
            productos.append((cantidad, producto, precio, importe))
            total += importe

        if not cliente or not productos:
            messagebox.showerror("Error", "Debe ingresar un cliente y al menos un producto.")
            return

        # Folio mensual compartido
        if not self._folio_actual:
            self._folio_actual = generar_id_pedido_ym()
        numero_nota = self._folio_actual

        nombre_pdf = f"Nota_{numero_nota}_{cliente.replace(' ', '_')}.pdf"
        pdf_path = os.path.join(NOTAS_DIR, nombre_pdf)

        # Media carta (half letter)
        c = canvas.Canvas(pdf_path, pagesize=(letter[0] / 2, letter[1] / 2))

        # === ENCABEZADO ===
        # Logo (esto NO se mueve)
        if os.path.exists(self.logo_path):
            c.drawImage(self.logo_path, -20, 330, width=200, height=90, preserveAspectRatio=True, mask='auto')
        else:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, 380, "Plásticos Delta")

        # --- QR arriba a la derecha ---
        page_w, page_h = (letter[0] / 2, letter[1] / 2)
        qr_size = 48      # ajusta 42-56 si quieres
        margin  = 20
        qr_x = page_w - margin - qr_size
        qr_y = page_h - margin - qr_size
        self._draw_code(c, numero_nota, kind="QR", size=qr_size, x=qr_x, y=qr_y)

        # Todo lo demás del encabezado/tabla debe ir DEBAJO del QR:
        gap = 10                         # separación visual bajo el QR
        y_head = qr_y - gap              # línea base para "Fecha" / "N° Nota"
        if y_head > 330:
            # seguridad por si QR queda muy alto: limitamos máximo
            y_head = 330

        c.setFont("Helvetica", 9)
        # Coloca "Fecha" y "N° Nota" por debajo del QR
        c.drawRightString(page_w - margin, y_head, f"Fecha: {fecha_vis}")

        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(page_w - margin, y_head - 14, "N° Nota:")
        c.setFillColorRGB(1, 0, 0)
        c.drawRightString(page_w - margin, y_head - 14, numero_nota)
        c.setFillColorRGB(0, 0, 0)

        # Cliente (también debajo del QR)
        c.drawString(40, y_head, f"Cliente: {cliente}")

        # === ARRANQUE DE LA TABLA ===
        y = y_head - 25                  # ahora la tabla arranca más abajo
        c.line(40, y + 10, page_w - 25, y + 10)
        c.drawString(45, y, "CANT.")
        c.drawString(85, y, "PRODUCTO")
        c.drawString(185, y, "P.UNIT")
        c.drawString(230, y, "IMPORTE")
        y -= 10
        c.line(40, y, page_w - 25, y)

        for cant, prod, prec, imp in productos:
            y -= 15
            if y < 60:
                c.showPage()
                y = 380
            c.drawString(45, y, str(cant))
            c.drawString(85, y, str(prod)[:14])
            c.drawRightString(225, y, f"${prec:,.2f}")
            c.drawRightString(270, y, f"${imp:,.2f}")
            c.line(40, y - 5, 270, y - 5)

        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(270, y - 20, f"TOTAL: ${total:,.2f}")
        c.save()

        # Abrir PDF con visor por defecto
        try:
            if os.name == 'nt':
                os.startfile(pdf_path)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", pdf_path], check=False)
            else:
                subprocess.run(["xdg-open", pdf_path], check=False)
        except Exception as e:
            messagebox.showinfo("PDF generado", f"PDF creado en: {pdf_path}\nError al abrir: {e}")

        messagebox.showinfo("Éxito", f"Nota de venta generada:\n{nombre_pdf}")

        # Si NO quieres limpiar aquí para registrar después con el mismo folio, comenta las siguientes líneas:
        # self._reset_form()
        # self._folio_actual = None

    # ---------------- Registrar Pedido ----------------------
    def registrar_pedido(self):
        from datetime import datetime
        from tkinter import messagebox
        from data.csv_manager import registrar_pedido as csv_registrar_pedido, generar_id_pedido_ym
        from ui.pdf_utils import generar_pdf_pedido, abrir_pdf

        cliente = (self.cliente.get() or "").strip()
        if not cliente:
            messagebox.showerror("Error", "Ingresa el nombre del cliente.")
            return

        # Recolectar líneas de la tabla
        items = []
        total = 0.0
        for iid in self.tree.get_children():
            vals = self.tree.item(iid)["values"]
            # Esperado: (cantidad, producto, precio, importe)
            try:
                cantidad = int(vals[0])
            except Exception:
                cantidad = 0
            producto = str(vals[1] or "")
            # Normaliza precios/importe (vienen formateados con $ y comas)
            try:
                precio_u = float(str(vals[2]).replace("$","").replace(",","").strip() or "0")
            except Exception:
                precio_u = 0.0
            try:
                importe = float(str(vals[3]).replace("$","").replace(",","").strip() or "0")
            except Exception:
                importe = cantidad * precio_u

            if producto and cantidad > 0:
                items.append({
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": f"{precio_u:.2f}",
                    "importe": f"{importe:.2f}",
                })
                total += importe

        if not items:
            messagebox.showerror("Error", "Agrega al menos un producto antes de registrar.")
            return

        # Folio por año/mes con consecutivo
        now = datetime.now()
        id_pedido = generar_id_pedido_ym(now)
        fecha_str = now.strftime("%Y-%m-%d %H:%M")
        estado = "Pendiente"
        desc_flag = "1" if bool(self.descuento.get()) else "0"

        # Guardar encabezado + detalle
        try:
            csv_registrar_pedido(
                header={
                    "id_pedido": id_pedido,
                    "fecha": fecha_str,
                    "cliente": cliente,
                    "total": f"{total:.2f}",
                    "estado": estado,
                    "descuento": desc_flag,
                },
                items=items
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar el pedido.\n{e}")
            return

        # Aviso y opción de generar PDF
        if messagebox.askyesno("Registrado", f"Pedido {id_pedido} registrado.\n\n¿Deseas generar la nota (PDF) ahora?"):
            try:
                pdf_path = generar_pdf_pedido(
                    id_pedido=id_pedido,
                    cliente=cliente,
                    fecha_str=fecha_str,
                    items=items,
                    # Deja que pdf_utils resuelva el logo desde assets si ya lo tienes configurado
                    qr_kind="QR",
                )
                abrir_pdf(pdf_path)
            except Exception as e:
                messagebox.showwarning("PDF", f"El pedido se registró, pero no se pudo generar el PDF.\n{e}")

        # --- SIEMPRE: dejar lista la pestaña para otra captura ---
        self._flush_form()
        # SIEMPRE: dejar lista la pestaña y refrescar todo

        # ---- NUEVO: refrescar otras tabs si es necesario ----
        self._flush_form()
        self._emit_refresh_all()



    # ---------------- Abrir productos.csv -------------------
    def abrir_csv(self):
        csv_path = os.path.join(os.getcwd(), "productos.csv")
        try:
            if os.name == 'nt':
                os.startfile(csv_path)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", csv_path], check=False)
            else:
                subprocess.run(["xdg-open", csv_path], check=False)
        except Exception as e:
            messagebox.showinfo("Editar productos", f"No se pudo abrir automáticamente.\nRuta: {csv_path}\nError: {e}")
        messagebox.showinfo("Editar productos", "Edita el archivo CSV y guarda los cambios.\nSe actualizará al reiniciar la app.")

    # ---------------- Limpiar formulario --------------------
    def _reset_form(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.cliente.set("")
        self.cantidad_entry.delete(0, tk.END)
        self.producto_entry.delete(0, tk.END)
        self.precio_entry.delete(0, tk.END)
        self.descuento.set(False)
        self.lista_sugerencias.grid_remove()
        self.cantidad_entry.focus()

    # ------------------ Dibujar códigos ---------------------

    # dentro de TabNuevaNota
    def _draw_code(self, canvas_obj, folio: str, kind: str = "QR", *,
                size: int = 48, x: float = 0, y: float = 0):
        """
        Dibuja un QR o un Code128 en (x, y) con tamaño 'size'.
        (x, y) es la esquina inferior-izquierda del gráfico.
        """
        if kind.upper() == "QR":
            w = qr.QrCodeWidget(folio)
            bx, by, bw, bh = w.getBounds()
            sx = size / (bw - bx)
            sy = size / (bh - by)
            d = Drawing(size, size, transform=[sx, 0, 0, sy, 0, 0])
            d.add(w)
            renderPDF.draw(d, canvas_obj, x, y)
        else:
            # Código de barras Code128
            code = code128.Code128(folio, barHeight=size, barWidth=0.6, humanReadable=False)
            code.drawOn(canvas_obj, x, y)


    # --- NUEVO: dejar lista la pestaña para una nueva nota ---
    def _flush_form(self):
        # Limpiar tabla
        for itm in self.tree.get_children():
            self.tree.delete(itm)
        # Limpiar campos
        self.cliente.set("")
        try:
            self.descuento.set(False)
        except Exception:
            pass
        self.cantidad_entry.delete(0, "end")
        self.producto_entry.delete(0, "end")
        self.precio_entry.delete(0, "end")
        # Enfocar primer campo
        try:
            self.entry_cliente.focus_set()
        except Exception:
            pass


