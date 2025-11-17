import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from data.csv_manager import (
    cargar_productos,
    cargar_clientes,
    buscar_clientes,
    registrar_pedido as csv_registrar_pedido,
    generar_id_pedido_ym,
)


class TabCapturaRapida:
    """
    Tab para levantar pedidos rápido:
    - Seleccionas cliente (con autocompletado).
    - Se muestra una tabla (scrollable) con todos los productos del CSV en orden.
    - Solo capturas cantidades y navegas con ENTER entre filas.
    """

    def __init__(
        self,
        notebook,
        frame_style="Dark.TFrame",
        label_style="Dark.TLabel",
        button_style="Dark.TButton",
        entry_style="Dark.TEntry",
        tree_style="Dark.Treeview",  # no usamos Treeview, pero mantenemos la firma consistente
        on_refresh_all=None,
    ):
        self.frame_style = frame_style
        self.label_style = label_style
        self.button_style = button_style
        self.entry_style = entry_style
        self.tree_style = tree_style
        self.on_refresh_all = on_refresh_all

        self.frame = ttk.Frame(notebook, style=self.frame_style)

        # Estado de cliente / descuento
        self.cliente = tk.StringVar()
        self.cliente_id = None
        self.cliente_tiene_desc = False

        # este BooleanVar lo usamos igual que en TabNuevaNota
        self.descuento = tk.BooleanVar(value=False)

        # caches
        self.productos_data = []
        self.clientes_data = []

        # filas de captura: [{"producto": str, "precio": str, "precio_desc": str, "entry": Entry}, ...]
        self._rows = []

                # índice de la fila activa (para resaltar)
        self._active_row = None

        # estilos visuales para la fila activa
        style = ttk.Style()
        style.configure("ActiveRow.TFrame", background="#144d2a")
        style.configure("ActiveRow.TLabel", background="#144d2a", foreground="white")
        style.configure("ActiveRow.TEntry", fieldbackground="#206d3a")


        self._build_ui()
        self.refrescar()

    # -------------------- UI --------------------

    def _build_ui(self):
        # --- fila cliente ---
        top = ttk.Frame(self.frame, style=self.frame_style)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 4))
        top.grid_columnconfigure(1, weight=1)

        ttk.Label(top, text="Cliente (ID o Nombre):", style=self.label_style)\
            .grid(row=0, column=0, sticky="e", padx=(0, 6))

        self.entry_cliente = ttk.Entry(top, textvariable=self.cliente, width=40, style=self.entry_style)
        self.entry_cliente.grid(row=0, column=1, sticky="ew")
        self.entry_cliente.bind("<KeyRelease>", self.autocompletar_cliente)

        self.lbl_desc = ttk.Label(top, text="Desc.: —", style=self.label_style)
        self.lbl_desc.grid(row=0, column=2, sticky="w", padx=(10, 0))

        # Lista de sugerencias de clientes
        self.lista_sugerencias_cliente = tk.Listbox(
            self.frame, height=5, bg="#2d2d2d", fg="white", activestyle="dotbox"
        )
        self.lista_sugerencias_cliente.grid(row=1, column=0, sticky="w", padx=10)
        self.lista_sugerencias_cliente.bind("<<ListboxSelect>>", self.seleccionar_cliente)
        self.lista_sugerencias_cliente.grid_remove()

        # --- cabeceras tabla de captura ---
        headers = ttk.Frame(self.frame, style=self.frame_style)
        headers.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10)
        ttk.Label(headers, text="Producto", style=self.label_style)\
            .grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(headers, text="Cantidad", style=self.label_style)\
            .grid(row=0, column=1, sticky="w")

        # --- contenedor scrollable para las filas de productos ---
        container = ttk.Frame(self.frame, style=self.frame_style)
        container.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(10, 0), pady=(4, 8))

        self.frame.grid_rowconfigure(3, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            container,
            highlightthickness=0,
            bd=0,
            bg="#1e1e1e",
        )
        self.scroll_y = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set)

        self.inner = ttk.Frame(self.canvas, style=self.frame_style)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        def _on_frame_config(_event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.inner.bind("<Configure>", _on_frame_config)

        def _on_canvas_config(event):
            # Ajusta el ancho del frame interno al ancho del canvas
            try:
                self.canvas.itemconfigure(self.canvas_window, width=event.width)
            except Exception:
                pass

        self.canvas.bind("<Configure>", _on_canvas_config)

        # Scroll con rueda del mouse (foco en canvas o en entries)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # --- botones inferiores ---
        btns = ttk.Frame(self.frame, style=self.frame_style)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", padx=10, pady=(0, 10))

        self.btn_registrar = ttk.Button(
            btns,
            text="Registrar pedido",
            style=self.button_style,
            command=self.registrar_pedido,
        )
        self.btn_registrar.grid(row=0, column=0, padx=(0, 6))

        self.btn_limpiar = ttk.Button(
            btns,
            text="Limpiar",
            style=self.button_style,
            command=self._limpiar,
        )
        self.btn_limpiar.grid(row=0, column=1)

    # -------------------- Scroll wheel --------------------

    def _on_mousewheel(self, event):
        # Windows reporta delta múltiplos de 120
        if self.canvas.winfo_exists():
            try:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

    # -------------------- Datos base --------------------

    def _cargar_clientes(self):
        try:
            self.clientes_data = cargar_clientes()
        except Exception as e:
            self.clientes_data = []
            messagebox.showerror("Error", f"No se pudieron cargar clientes.\n{e}")

    def _cargar_productos(self):
        # Limpia filas actuales
        for r in self._rows:
            try:
                r["entry"].destroy()
            except Exception:
                pass
        for w in list(self.inner.winfo_children()):
            w.destroy()
        self._rows.clear()

        try:
            self.productos_data = cargar_productos() or []
        except Exception as e:
            self.productos_data = []
            messagebox.showerror("Error", f"No se pudieron cargar productos.\n{e}")
            return

        # Validación de enteros >= 0
        def _validate_int(P):
            s = (P or "").strip()
            if not s:
                return True
            if s.isdigit():
                return True
            return False

        vcmd = (self.frame.register(_validate_int), "%P")

        # Crear filas en el mismo orden del CSV
        for idx, p in enumerate(self.productos_data):
            nombre = p.get("producto", "")

            # ⬇️ Frame por fila para poder iluminarla completa
            row_frame = ttk.Frame(self.inner, style=self.frame_style)
            row_frame.grid(row=idx, column=0, columnspan=2, sticky="ew", pady=1)
            row_frame.grid_columnconfigure(0, weight=1)

            lbl = ttk.Label(row_frame, text=nombre, style=self.label_style)
            lbl.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=2)

            ent = ttk.Entry(
                row_frame,
                width=8,
                style=self.entry_style,
                validate="key",
                validatecommand=vcmd,
            )
            ent.grid(row=0, column=1, sticky="w", pady=2)

            # ENTER → siguiente fila
            ent.bind("<Return>", lambda e, i=idx: self._focus_next_row(i))
            ent.bind("<KP_Enter>", lambda e, i=idx: self._focus_next_row(i))

            # Cuando recibe foco (click, TAB, etc.), resaltar esa fila
            ent.bind("<FocusIn>", lambda e, i=idx: self._set_active_row(i))

            self._rows.append(
                {
                    "producto": nombre,
                    "precio": p.get("precio", ""),
                    "precio_desc": p.get("precio_desc", ""),
                    "entry": ent,
                    "frame": row_frame,
                    "label": lbl,
                }
            )

        # foco y resalte en la primera fila
        if self._rows:
            try:
                self._rows[0]["entry"].focus_set()
                self._set_active_row(0)
            except Exception:
                pass


    # -------------------- Navegación ENTER --------------------

    def _focus_next_row(self, idx):
        """Mover el foco a la siguiente fila; al llegar al final, volver al inicio."""
        if not self._rows:
            return

        last_index = len(self._rows) - 1
        next_idx = (idx + 1) % len(self._rows)

        # 🌀 Si venimos de la ÚLTIMA fila real y vamos a la primera, sí reseteamos el scroll
        if idx == last_index and next_idx == 0:
            try:
                self.canvas.yview_moveto(0.0)
            except Exception:
                pass

        start_idx = next_idx
        while True:
            ent = self._rows[next_idx]["entry"]
            try:
                if ent.winfo_exists():
                    ent.focus_set()
                    ent.icursor("end")
                    self._set_active_row(next_idx)  # esto internamente llama a _ensure_visible
                    return
            except Exception:
                pass

            next_idx = (next_idx + 1) % len(self._rows)
            if next_idx == start_idx:
                break


    # -------------------- Resalte fila activa --------------------    
    def _set_active_row(self, idx):
        """Resalta visualmente la fila activa."""
        # Quitar resalte de la fila anterior
        try:
            if self._active_row is not None and 0 <= self._active_row < len(self._rows):
                old = self._rows[self._active_row]
                old["frame"].configure(style=self.frame_style)
                old["label"].configure(style=self.label_style)
                old["entry"].configure(style=self.entry_style)
        except Exception:
            pass

        # Si idx no es válido, no hay fila activa
        if idx is None or not (0 <= idx < len(self._rows)):
            self._active_row = None
            return

        self._active_row = idx
        row = self._rows[idx]

        # Aplicar estilos "verdes" a la fila activa
        try:
            row["frame"].configure(style="ActiveRow.TFrame")
            row["label"].configure(style="ActiveRow.TLabel")
            row["entry"].configure(style="ActiveRow.TEntry")
        except Exception:
            pass

        # Asegurar que la FILA activa esté visible en el scroll
        try:
            self._ensure_visible(row["frame"])
        except Exception:
            pass


        # Asegurar que la entry activa esté visible en el scroll
        try:
            self._ensure_visible(row["entry"])
        except Exception:
            pass



    # -------------------- Autocompletado de clientes --------------------

    def autocompletar_cliente(self, event=None):
        txt = (self.cliente.get() or "").strip()
        if not txt:
            self.lista_sugerencias_cliente.grid_remove()
            self.cliente_id = None
            self.cliente_tiene_desc = False
            self.descuento.set(False)
            self.lbl_desc.config(text="Desc.: —")
            return

        matches = buscar_clientes(txt)
        self.lista_sugerencias_cliente.delete(0, tk.END)
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

        # Extrae ID para buscar descuento
        try:
            cid = display.split(" - ", 1)[0].strip()
        except Exception:
            cid = display.strip()

        elegido = None
        for c in (self.clientes_data or []):
            if c.get("id_cliente") == cid:
                elegido = c
                break

        tiene_desc = bool(elegido and str(elegido.get("descuento", "0")) == "1")
        self.cliente_id = cid
        self.cliente_tiene_desc = tiene_desc
        self.descuento.set(self.cliente_tiene_desc)
        self.lbl_desc.config(text=f"Desc.: {'Sí' if self.cliente_tiene_desc else 'No'}")

        # Luego de elegir cliente, manda el foco al primer producto
        if self._rows:
            try:
                self._rows[0]["entry"].focus_set()
                self._set_active_row(0)
            except Exception:
                pass


    # -------------------- Registrar pedido --------------------

    def registrar_pedido(self):
        cliente = (self.cliente.get() or "").strip()
        if not cliente:
            messagebox.showerror("Error", "Ingresa el cliente (ID - Nombre).")
            try:
                self.entry_cliente.focus_set()
            except Exception:
                pass
            return

        items = []
        total = 0.0

        for idx, row in enumerate(self._rows):
            ent = row["entry"]
            try:
                raw = (ent.get() or "").strip()
            except Exception:
                raw = ""
            if not raw:
                continue
            try:
                cantidad = int(raw)
            except Exception:
                cantidad = 0
            if cantidad <= 0:
                continue

            producto = row["producto"]
            base_precio = row["precio_desc"] if self.descuento.get() else row["precio"]
            try:
                precio_u = float(str(base_precio or "0").replace(",", "."))
            except Exception:
                precio_u = 0.0
            importe = precio_u * cantidad

            items.append(
                {
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": f"{precio_u:.2f}",
                    "importe": f"{importe:.2f}",
                }
            )
            total += importe

        if not items:
            messagebox.showerror("Error", "Captura al menos una cantidad mayor a 0.")
            return

        now = datetime.now()
        id_pedido = generar_id_pedido_ym(now)
        fecha_str = now.strftime("%Y-%m-%d %H:%M")
        estado = "Pendiente"
        desc_flag = "1" if bool(self.descuento.get()) else "0"

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
                items=items,
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar el pedido.\n{e}")
            return

        messagebox.showinfo("Pedido registrado", f"Pedido {id_pedido} registrado correctamente.")

        # refresca el resto de pestañas si está configurado
        if callable(self.on_refresh_all):
            try:
                self.on_refresh_all()
            except Exception:
                pass

        self._limpiar(cargar_productos_nuevamente=False)

    # -------------------- Limpiar / Refrescar --------------------

    def _limpiar(self, cargar_productos_nuevamente=True):
        # Limpia cliente
        self.cliente.set("")
        self.cliente_id = None
        self.cliente_tiene_desc = False
        self.descuento.set(False)
        self.lbl_desc.config(text="Desc.: —")
        self.lista_sugerencias_cliente.grid_remove()

        # Limpia cantidades pero deja los productos
        for row in self._rows:
            try:
                row["entry"].delete(0, "end")
            except Exception:
                pass

        if cargar_productos_nuevamente:
            # por si se modificó el CSV de productos
            self._cargar_productos()

        try:
            self.entry_cliente.focus_set()
        except Exception:
            pass

    def refrescar(self):
        """Se llama desde el app cuando se refrescan todas las pestañas."""
        self._cargar_clientes()
        self._cargar_productos()
        
# -------------------- Asegurar visibilidad de widget --------------------

    def _ensure_visible(self, widget):
        """Mueve el scroll para que la fila quede visible cuando vamos bajando."""
        try:
            if not (self.canvas.winfo_ismapped() and widget.winfo_ismapped()):
                return

            self.canvas.update_idletasks()

            MARGIN = 24  # píxeles extra para que no quede pegado al borde

            # región visible actual del canvas (coordenadas del inner)
            top = self.canvas.canvasy(0)
            visible_h = self.canvas.winfo_height()
            bottom = top + visible_h

            widget_top = widget.winfo_y()
            widget_bottom = widget_top + widget.winfo_height()

            inner_h = max(1, self.inner.winfo_height())

            # 🔽 Solo movemos si la fila se sale por la parte de abajo
            if widget_bottom + MARGIN > bottom:
                target_top = widget_bottom + MARGIN - visible_h
                # acotar
                target_top = max(0, min(target_top, max(0, inner_h - visible_h)))
                frac = target_top / inner_h
                self.canvas.yview_moveto(max(0.0, min(1.0, frac)))

            # 👀 Nota: ya NO movemos hacia arriba; si vas subiendo, no auto-scroll.
        except Exception:
            pass



