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
import json, secrets, hashlib
from data.paths import PRODUCTOS_PATH, CLIENTES_PATH





# Asegura import relativo cuando se ejecuta desde main.py
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from data.csv_manager import (
    cargar_productos,
    registrar_pedido as registrar_pedido_csv,
    generar_id_pedido_ym,
    cargar_clientes,
    buscar_clientes, 
)

NOTAS_DIR = os.path.join(os.getcwd(), "Notas")

# Config de administrador
ADMIN_CFG = os.path.join(os.getcwd(), "admin_cfg.json")
ADMIN_USER = "JPerez"  # usuario fijo
DEFAULT_ADMIN_PASS = "18062002"  # podrás cambiarla en la ventana



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

        # --- Menú contextual ---
        self._ctx = tk.Menu(self.frame, tearoff=0)
        self._ctx.add_command(label="Administrador…", command=self._admin_login)

        # Mostrar menú con click derecho en el frame y en la tabla
        self.frame.bind("<Button-3>", lambda e: self._ctx.tk_popup(e.x_root, e.y_root))
        self.frame.bind("<Control-Button-1>", lambda e: self._ctx.tk_popup(e.x_root, e.y_root))
        try:
            self.tree.bind("<Button-3>", lambda e: (self.tree.focus_set(), self._ctx.tk_popup(e.x_root, e.y_root)))
            self.tree.bind("<Control-Button-1>", lambda e: (self.tree.focus_set(), self._ctx.tk_popup(e.x_root, e.y_root)))
        except Exception:
            pass


        # Estado
        self.cliente = tk.StringVar()
        self.descuento = tk.BooleanVar(value=False)
        self.producto_var = tk.StringVar()
        self.cliente_id = None            # guarda el ID del cliente elegido
        self.cliente_tiene_desc = False   # sombra interna para claridad


        self.logo_path = "logo.png"
        os.makedirs(NOTAS_DIR, exist_ok=True)
        self._folio_actual = None  # Folio mensual compartido PDF/Registro

        # Cargar catálogo
        self.productos_data = self._cargar_catalogo()
        self.nombres_productos = [p["producto"] for p in self.productos_data]
        self.clientes_data = cargar_clientes()


        self.crear_ui()
# ------------------- Emitir refresh ----------------------        
    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()


    # ------------------------- UI -------------------------
    def crear_ui(self):
        # Fila 0
        ttk.Label(self.frame, text="Cliente (ID o Nombre):", style=self.label_style)\
            .grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.entry_cliente = ttk.Entry(self.frame, textvariable=self.cliente, width=40, style=self.entry_style)
        self.entry_cliente.grid(row=0, column=1, columnspan=3, pady=10, sticky="w")
        self.entry_cliente.bind("<KeyRelease>", self.autocompletar_cliente)   # <--- NUEVO

        # Descuento
        self.lbl_desc = ttk.Label(self.frame, text="Desc.: —", style=self.label_style)
        self.lbl_desc.grid(row=0, column=5, padx=10, sticky="w")

        # Lista de autocompletado clientes
        self.lista_sugerencias_cliente = tk.Listbox(self.frame, height=5, bg="#2d2d2d", fg="white")
        self.lista_sugerencias_cliente.grid(row=1, column=1, columnspan=3, padx=10, sticky="w")
        self.lista_sugerencias_cliente.bind("<<ListboxSelect>>", self.seleccionar_cliente)
        self.lista_sugerencias_cliente.grid_remove()


       

        # Fila 1
        ttk.Label(self.frame, text="Cantidad:", style=self.label_style)\
            .grid(row=2, column=0, padx=10, pady=10, sticky="e")
        self.cantidad_entry = ttk.Entry(self.frame, width=10, style=self.entry_style)
        self.cantidad_entry.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        ttk.Label(self.frame, text="Producto:", style=self.label_style)\
            .grid(row=2, column=2, padx=10, pady=10, sticky="e")
        self.producto_entry = ttk.Entry(self.frame, textvariable=self.producto_var, width=30, style=self.entry_style)
        self.producto_entry.grid(row=2, column=3, padx=10, pady=10, sticky="w")
        self.producto_entry.bind("<KeyRelease>", self.autocompletar_producto)

        ttk.Label(self.frame, text="Precio Unitario:", style=self.label_style)\
            .grid(row=2, column=4, padx=10, pady=10, sticky="e")
        self.precio_entry = ttk.Entry(self.frame, width=10, style=self.entry_style)
        self.precio_entry.grid(row=2, column=5, padx=10, pady=10, sticky="w")

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

        # --------------------- Aviso y opción de generar PDF---------------------------- #
        # if messagebox.askyesno("Registrado", f"Pedido {id_pedido} registrado.\n\n¿Deseas generar la nota (PDF) ahora?"):
        #     try:
        #         pdf_path = generar_pdf_pedido(
        #             id_pedido=id_pedido,
        #             cliente=cliente,
        #             fecha_str=fecha_str,
        #             items=items,
        #             # Deja que pdf_utils resuelva el logo desde assets si ya lo tienes configurado
        #             qr_kind="QR",
        #         )
        #         abrir_pdf(pdf_path)
        #     except Exception as e:
        #         messagebox.showwarning("PDF", f"El pedido se registró, pero no se pudo generar el PDF.\n{e}")

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

        self.cliente_id = None
        self.cliente_tiene_desc = False
        try:
            self.lbl_desc.config(text="Desc.: —")
        except Exception:
            pass
    
    def autocompletar_cliente(self, event=None):
        txt = (self.cliente.get() or "").strip()
        if not txt:
            self.lista_sugerencias_cliente.grid_remove()
            # si el usuario borró, limpia selección/flag
            self.cliente_id = None
            self.cliente_tiene_desc = False
            self.descuento.set(False)
            self.lbl_desc.config(text="Desc.: —")
            self.actualizar_precio()
            return
        matches = buscar_clientes(txt)
        self.lista_sugerencias_cliente.delete(0, tk.END)
        # Muestra "ID - Nombre"
        for c in matches[:50]:
            self.lista_sugerencias_cliente.insert(tk.END, f"{c['id_cliente']} - {c['nombre']}")
        if matches:
            self.lista_sugerencias_cliente.grid()
        else:
            self.lista_sugerencias_cliente.grid_remove()

    def seleccionar_cliente(self, event=None):
        sel = self.lista_sugerencias_cliente.curselection()
        if not sel:
            return
        display = self.lista_sugerencias_cliente.get(sel[0])  # "ID - Nombre"
        self.cliente.set(display)
        self.lista_sugerencias_cliente.grid_remove()
        # Resolver el cliente exacto
        try:
            cid = display.split(" - ", 1)[0].strip()
        except:
            cid = display.strip()
        # Busca en data para jalar el flag de descuento
        elegido = None
        for c in (self.clientes_data or []):
            if c.get("id_cliente") == cid:
                elegido = c; break
        tiene_desc = (elegido and str(elegido.get("descuento","0")) == "1")
        self.cliente_id = cid
        self.cliente_tiene_desc = bool(tiene_desc)
        # Actualiza el BooleanVar que ya usa tu lógica de precios
        self.descuento.set(self.cliente_tiene_desc)
        self.lbl_desc.config(text=f"Desc.: {'Sí' if self.cliente_tiene_desc else 'No'}")
        self.actualizar_precio()  # refresca P.Unit del producto seleccionado (si hubiera)
    

    # ===================== ADMIN: helpers credenciales =====================
    def _admin_load_cfg(self):
        # Si no existe, crea con password por default
        if not os.path.exists(ADMIN_CFG):
            data = {
                "user": ADMIN_USER,
                "salt": secrets.token_hex(16),
                "hash": ""  # se setea con DEFAULT_ADMIN_PASS
            }
            h = hashlib.sha256((DEFAULT_ADMIN_PASS + data["salt"]).encode("utf-8")).hexdigest()
            data["hash"] = h
            try:
                with open(ADMIN_CFG, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return data
        try:
            with open(ADMIN_CFG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"user": ADMIN_USER, "salt": secrets.token_hex(16), "hash": ""}

    def _admin_check(self, user, password):
        cfg = self._admin_load_cfg()
        if (user or "").strip() != (cfg.get("user") or ADMIN_USER):
            return False
        salt = cfg.get("salt") or ""
        expect = cfg.get("hash") or ""
        h = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return h == expect

    def _admin_save_password(self, new_password):
        cfg = self._admin_load_cfg()
        cfg["salt"] = secrets.token_hex(16)
        cfg["hash"] = hashlib.sha256((new_password + cfg["salt"]).encode("utf-8")).hexdigest()
        cfg["user"] = ADMIN_USER
        with open(ADMIN_CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True

    # ===================== ADMIN: UI =====================
    def _admin_login(self):
        win = tk.Toplevel(self.frame)
        win.title("Acceso administrador")
        win.transient(self.frame.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=12); frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Usuario:", style=self.label_style).grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        var_user = tk.StringVar(value=ADMIN_USER)
        ttk.Entry(frm, textvariable=var_user, width=26).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(frm, text="Contraseña:", style=self.label_style).grid(row=1, column=0, sticky="e", padx=(0,6), pady=4)
        var_pass = tk.StringVar()
        ttk.Entry(frm, textvariable=var_pass, width=26, show="•").grid(row=1, column=1, sticky="w", pady=4)

        btns = ttk.Frame(frm, style=self.frame_style); btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8,0))
        def _ok():
            if self._admin_check(var_user.get(), var_pass.get()):
                try:
                    win.grab_release()
                except Exception:
                    pass
                win.destroy()
                self._admin_panel()
            else:
                messagebox.showerror("Acceso", "Usuario o contraseña incorrectos.", parent=win)

        ttk.Button(btns, text="Entrar", command=_ok, style=self.button_style).pack(side="right")
        ttk.Button(btns, text="Cancelar", command=win.destroy, style=self.button_style).pack(side="right", padx=(0,8))

        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")

    def _admin_panel(self):
        win = tk.Toplevel(self.frame)
        win.title("Panel de administrador")
        win.transient(self.frame.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=14); frm.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frm, text="Acciones:", style=self.label_style).grid(row=0, column=0, sticky="w", pady=(0,6))

        # 1) Editar Productos CSV (solo admin)
        ttk.Button(frm, text="Editar Productos CSV", style=self.button_style,
                command=lambda: self._open_csv(PRODUCTOS_PATH)).grid(row=1, column=0, sticky="ew", pady=4)

        # 2) Editar Clientes CSV (solo admin)
        ttk.Button(frm, text="Editar Clientes CSV", style=self.button_style,
                command=lambda: self._open_csv(CLIENTES_PATH)).grid(row=2, column=0, sticky="ew", pady=4)

        # 3) Cambiar contraseña de administrador
        ttk.Button(frm, text="Cambiar contraseña de administrador…", style=self.button_style,
                command=self._admin_change_password).grid(row=3, column=0, sticky="ew", pady=(10,4))

        ttk.Button(frm, text="Cerrar", command=win.destroy, style=self.button_style).grid(row=4, column=0, sticky="e", pady=(10,0))

        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")

    def _open_csv(self, path_csv: str):
        try:
            if os.name == "nt":
                os.startfile(path_csv)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", path_csv], check=False)
            else:
                subprocess.run(["xdg-open", path_csv], check=False)
        except Exception as e:
            messagebox.showerror("Abrir CSV", f"No se pudo abrir:\n{path_csv}\n\n{e}")

    def _admin_change_password(self):
        win = tk.Toplevel(self.frame)
        win.title("Cambiar contraseña (admin)")
        win.transient(self.frame.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=12); frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Actual:", style=self.label_style).grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        v_old = tk.StringVar()
        ttk.Entry(frm, textvariable=v_old, show="•", width=26).grid(row=0, column=1, sticky="w")

        ttk.Label(frm, text="Nueva:", style=self.label_style).grid(row=1, column=0, sticky="e", padx=(0,6), pady=4)
        v_new = tk.StringVar()
        ttk.Entry(frm, textvariable=v_new, show="•", width=26).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Confirmar:", style=self.label_style).grid(row=2, column=0, sticky="e", padx=(0,6), pady=4)
        v_new2 = tk.StringVar()
        ttk.Entry(frm, textvariable=v_new2, show="•", width=26).grid(row=2, column=1, sticky="w")

        btns = ttk.Frame(frm, style=self.frame_style); btns.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8,0))

        def _save():
            if not self._admin_check(ADMIN_USER, v_old.get()):
                messagebox.showerror("Error", "La contraseña actual no es correcta.", parent=win)
                return
            if not v_new.get():
                messagebox.showerror("Error", "La nueva contraseña no puede estar vacía.", parent=win)
                return
            if v_new.get() != v_new2.get():
                messagebox.showerror("Error", "La confirmación no coincide.", parent=win)
                return
            self._admin_save_password(v_new.get())
            messagebox.showinfo("Listo", "Contraseña actualizada.", parent=win)
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        ttk.Button(btns, text="Guardar", command=_save, style=self.button_style).pack(side="right")
        ttk.Button(btns, text="Cancelar", command=win.destroy, style=self.button_style).pack(side="right", padx=(0,8))

        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")




