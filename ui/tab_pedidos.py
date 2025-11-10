import tkinter as tk
import os
from tkinter import ttk, messagebox
from datetime import datetime
from ui.pdf_utils import generar_pdf_pedido, abrir_pdf
from data.csv_manager import (
    leer_pedidos,
    leer_items_por_pedido,
    actualizar_cantidades_completadas_batch,    # fallback
    actualizar_cantidades_completadas_batch_sync,  
    actualizar_pedido_completo,
    cargar_productos,
    cancelar_pedido,
    set_fecha_entrega,
)


# === Helpers de fecha para mostrar HH:MM pero filtrar por día ===
def _try_parse_dt(s: str):
    s = (s or "").strip()
    if not s:
        return None
    formatos = [
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",        # por si llega sin hora
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]
    for f in formatos:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    return None

def _fmt_dt_show(s: str) -> str:
    """Lo que se MUESTRA: normaliza a 'YYYY-MM-DD HH:MM' si se puede."""
    dt = _try_parse_dt(s)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else (s or "")

def _date_key(s: str) -> str:
    """Clave para FILTRAR: solo la fecha 'YYYY-MM-DD' si parsea."""
    dt = _try_parse_dt(s)
    return dt.strftime("%Y-%m-%d") if dt else (s or "")


# --- Parser de fecha flexible ---
def _parse_fecha_flexible(s: str) -> datetime:
    s = (s or "").strip()
    formatos = [
        "%Y-%m-%d %H:%M",   # 2025-10-20 19:12
        "%d/%m/%Y %H:%M",   # 20/10/2025 19:12
        "%d-%m-%Y %H:%M",   # 20-10-2025 19:12
        "%Y/%m/%d %H:%M",   # 2025/10/20 19:12
        "%d.%m.%Y %H:%M",   # 20.10.2025 19:12 (por si acaso)
    ]
    for f in formatos:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    # Si llega aquí, no se pudo parsear
    raise ValueError("Formato no reconocido")

# --------- intento de import de la versión con sincronización ---------
try:
    # si tu csv_manager ya tiene esta función, la usamos
    from data.csv_manager import actualizar_cantidades_completadas_batch_sync  # type: ignore
    _HAS_SYNC = True
except Exception:
    _HAS_SYNC = False

def actualizar_batch_con_sync(id_pedido: str, updates: list[tuple[str,int]]):
    """
    Wrapper: si existe actualizar_cantidades_completadas_batch_sync() la usamos.
    Si no, usamos actualizar_cantidades_completadas_batch() (sin sincronía) para no romper nada.
    """
    if _HAS_SYNC:
        return actualizar_cantidades_completadas_batch_sync(id_pedido, updates)  # type: ignore
    else:
        return actualizar_cantidades_completadas_batch(updates)

# Mini calendario (opcional)
try:
    from tkcalendar import DateEntry
    _HAS_TKCAL = True
except Exception:
    _HAS_TKCAL = False


def _es_fantasma_row(p: dict) -> bool:
    """Detecta pedidos fantasma con tolerancia (sin requerir columnas nuevas)."""
    if not p:
        return False
    estado = (p.get("estado", "") or "").strip().lower()
    flag = str(p.get("es_fantasma", "") or "").strip().lower() in ("1", "true", "yes", "y")
    pref = str(p.get("id_pedido", "") or "").startswith("PH-")
    return estado == "fantasma" or flag or pref

def _orden_prioridad(p: dict) -> tuple:
    """
    Prioridad de orden:
    0 = Fantasma (pendiente/parcial)  → al inicio
    1 = Pedidos normales (pendiente/parcial/completado)
    2 = Cancelado
    3 = Fantasma COMPLETADO           → al final
    Luego por fecha e id para estabilidad visual.
    """
    estado = (p.get("estado","") or "").strip().lower()
    es_fantasma = _es_fantasma_row(p)

    if es_fantasma and estado == "completado":
        rank = 3                  # al final-del-final
    elif estado in {"cancelado","cancelada","canceled","cancelled"}:
        rank = 2
    elif es_fantasma:
        rank = 0
    else:
        rank = 1

    return (rank, p.get("fecha",""), p.get("id_pedido",""))


def _es_fantasma_id_estado(id_pedido: str, estado: str) -> bool:
    return str(id_pedido or "").startswith("PH-") or (str(estado or "").strip().lower() == "fantasma")


class TabPedidos:
    def __init__(self, notebook,
                 frame_style="Dark.TFrame",
                 tree_style="Dark.Treeview",
                 button_style="Dark.TButton",
                 label_style="Dark.TLabel",
                 on_refresh_all=None):
        self.frame_style = frame_style
        self.tree_style = tree_style
        self.button_style = button_style
        self.label_style = label_style
        self.on_refresh_all = on_refresh_all

        # Estado para filtros “tipo Excel” y orden
        self._raw_pedidos = []      # datos completos (sin filtrar)
        self._active_filters = {}   # {col_id: set(valores_permitidos)}
        self._sort_state = {}       # {col_id: True=asc, False=desc}
        self._last_sort_col = None  # última columna usada para ordenar

        self.frame = ttk.Frame(notebook, style=self.frame_style)

        self._build_ui()
        self._configure_grid()
        self._init_row_tags()
        self.refrescar()

    # --------------- helpers ---------------
    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()

    # ---------------- UI ----------------
    def _build_ui(self):
        # Top bar
        top_bar = ttk.Frame(self.frame, style=self.frame_style)
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
        top_bar.grid_columnconfigure(99, weight=1)

        filtro_box = ttk.Frame(top_bar, style=self.frame_style)
        filtro_box.grid(row=0, column=0, sticky="w")

        ttk.Label(filtro_box, text="Estado:", style=self.label_style).pack(side="left", padx=(0,6))
        self.cmb_estado = ttk.Combobox(
            filtro_box,
            values=["Todos","Pendiente","Parcial","Completado","Cancelado","Fantasma"],
            state="readonly", width=15
        )
        self.cmb_estado.set("Todos")
        self.cmb_estado.pack(side="left")
        self.cmb_estado.bind("<<ComboboxSelected>>", lambda e: self._pintar_tree_aplicando_filtros_y_orden())

        ttk.Label(filtro_box, text="Pedido #:", style=self.label_style).pack(side="left", padx=(12,6))
        self.var_buscar = tk.StringVar()
        ent_buscar = ttk.Entry(filtro_box, textvariable=self.var_buscar, width=18)
        ent_buscar.pack(side="left")
        ent_buscar.bind("<Return>", lambda e: self._pintar_tree_aplicando_filtros_y_orden())

        ttk.Button(filtro_box, text="Buscar", command=self._pintar_tree_aplicando_filtros_y_orden, style=self.button_style)\
            .pack(side="left", padx=(6,0))
        ttk.Button(filtro_box, text="Limpiar", command=self._limpiar_busqueda, style=self.button_style)\
            .pack(side="left", padx=(6,0))

        # Actions
        btn_bar = ttk.Frame(top_bar, style=self.frame_style)
        btn_bar.grid(row=0, column=1, sticky="e")
        ttk.Button(btn_bar, text="Refrescar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=8)
        ttk.Button(btn_bar, text="Editar líneas…", command=self._abrir_editor_masivo, style=self.button_style)\
            .pack(side="left", padx=8)
        ttk.Button(btn_bar, text="Editar pedido…", command=self._abrir_editor_pedido, style=self.button_style)\
            .pack(side="left", padx=8)

        self.btn_pdf = ttk.Button(
            top_bar,
            text="Generar Nota PDF",
            style=self.button_style,
            command=self._generar_pdf_pedido_sel
        )
        self.btn_pdf.grid(row=0, column=10, padx=(6, 0), sticky="w")

        # Tabla de pedidos
        self._cols_p = ("id_pedido", "fecha", "fecha_entrega", "cliente", "total", "estado", "descuento")
        self.tree_pedidos = ttk.Treeview(self.frame, columns=self._cols_p, show="headings",
                                        height=11, style=self.tree_style)

        headers = {
            "id_pedido":"ID", "fecha":"Fecha", "fecha_entrega":"Entrega",
            "cliente":"Cliente", "total":"Total", "estado":"Estado", "descuento":"Desc."
        }
        for col in self._cols_p:
            self.tree_pedidos.heading(col, text=headers[col])
            self.tree_pedidos.column(col, anchor="center")

        # Selección y FILTROS/ORDEN por encabezado
        self.tree_pedidos.bind("<<TreeviewSelect>>", self._on_select_pedido)
        self.tree_pedidos.bind("<Button-1>", self._on_tree_click_heading)  # encabezado: filtros/orden

        # Scrollbars
        y1 = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree_pedidos.yview)
        x1 = ttk.Scrollbar(self.frame, orient="horizontal", command=self.tree_pedidos.xview)
        self.tree_pedidos.configure(yscrollcommand=y1.set, xscrollcommand=x1.set)

        self.tree_pedidos.grid(row=1, column=0, sticky="nsew", padx=(15,0), pady=(10,2))
        y1.grid(row=1, column=1, sticky="ns", pady=(10,2))
        x1.grid(row=2, column=0, sticky="ew", padx=(15,0))

        # Menú contextual: Cancelar pedido + Fecha de entrega
        self._ctx_menu = tk.Menu(self.frame, tearoff=0)
        self._ctx_menu.add_command(label="Asignar fecha de entrega…", command=self._ctx_set_fecha_entrega)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Cancelar pedido…", command=self._ctx_cancelar_pedido)
        self.tree_pedidos.bind("<Button-3>", self._show_ctx_menu)
        self.tree_pedidos.bind("<Control-Button-1>", self._show_ctx_menu)

        # Tabla de detalle
        cols_d = ("id_linea","producto","cantidad","completado","pendiente","precio_unitario","importe")
        self.tree_detalle = ttk.Treeview(self.frame, columns=cols_d, show="headings",
                                        height=13, style=self.tree_style)
        headers_d = {
            "id_linea":"ID Línea", "producto":"Producto", "cantidad":"Cantidad",
            "completado":"Completado", "pendiente":"Pendiente",
            "precio_unitario":"P.Unit", "importe":"Importe"
        }
        for col in cols_d:
            self.tree_detalle.heading(col, text=headers_d[col])
            self.tree_detalle.column(col, anchor="center")

        y2 = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree_detalle.yview)
        x2 = ttk.Scrollbar(self.frame, orient="horizontal", command=self.tree_detalle.xview)
        self.tree_detalle.configure(yscrollcommand=y2.set, xscrollcommand=x2.set)

        self.tree_detalle.grid(row=3, column=0, sticky="nsew", padx=(15,0), pady=(6,2))
        y2.grid(row=3, column=1, sticky="ns", pady=(6,2))
        x2.grid(row=4, column=0, sticky="ew", padx=(15,0), pady=(0,10))

        # Estado actual
        self._current_pedido = None
        self._current_descuento = "0"

    def _configure_grid(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)  # pedidos
        self.frame.grid_rowconfigure(3, weight=2)  # detalle

    # ---- Tags de color ----
    def _init_row_tags(self):
        # Pedidos
        self.tree_pedidos.tag_configure("row_completado", background="#2ecc71", foreground="#000000")
        self.tree_pedidos.tag_configure("row_parcial",    background="#f1c40f", foreground="#000000")
        self.tree_pedidos.tag_configure("row_pendiente",  background="#00bcd4", foreground="#000000")
        self.tree_pedidos.tag_configure("row_cancelado",  background="#9e9e9e", foreground="#000000")
        self.tree_pedidos.tag_configure("row_fantasma",   foreground="#C62828")  # rojo para fantasmas

        # Detalle
        self.tree_detalle.tag_configure("d_completado", background="#2ecc71", foreground="#000000")
        self.tree_detalle.tag_configure("d_parcial",    background="#f1c40f", foreground="#000000")
        self.tree_detalle.tag_configure("d_pendiente",  background="#00bcd4", foreground="#000000")
        self.tree_detalle.tag_configure("d_cancelado",  background="#9e9e9e", foreground="#000000")

    def _detail_tag_for(self, cantidad: int, completado: int) -> str:
        try:
            c = int(cantidad); comp = int(completado)
        except Exception:
            return "d_pendiente"
        if comp <= 0:
            return "d_pendiente"
        if comp >= c:
            return "d_completado"
        return "d_parcial"

    # ---------------- NUEVA LÓGICA: Excel-like filters + orden ----------------
    def refrescar(self):
        """Recarga datos crudos y repinta aplicando filtros/orden."""
        for t in (self.tree_pedidos, self.tree_detalle):
            for item in t.get_children():
                t.delete(item)
        self._current_pedido = None
        self._current_descuento = "0"

        try:
            self._raw_pedidos = leer_pedidos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer los pedidos.\n{e}")
            self._raw_pedidos = []

        self._pintar_tree_aplicando_filtros_y_orden()

    def _limpiar_busqueda(self):
        """Limpia filtros de la barra superior y los filtros por columna."""
        self.var_buscar.set("")
        self._active_filters.clear()
        self._last_sort_col = None
        self._sort_state.clear()
        self._pintar_tree_aplicando_filtros_y_orden()

    def _filtrar_por_ui_superior(self, pedidos):
        """Aplica filtros existentes (Estado y Pedido#)."""
        estado_sel = (self.cmb_estado.get() or "Todos").strip()
        q = (self.var_buscar.get() or "").strip()

        out = []
        for p in pedidos:
            es_fantasma = _es_fantasma_row(p)
            estado_p = (p.get("estado","") or "").strip().capitalize()

            # 1) Estado
            if estado_sel == "Todos":
                pass
            elif estado_sel == "Fantasma":
                if not es_fantasma:
                    continue
            else:
                if es_fantasma:
                    continue
                if estado_p.lower() != estado_sel.lower():
                    continue

            # 2) Pedido #
            if q and q not in (p.get("id_pedido","")):
                continue

            out.append(p)
        return out

    def _aplicar_filtros_header(self, rows):
        out = []
        for r in rows:
            ok = True
            for col_key, allowed in self._active_filters.items():
                if not allowed:  # si quedó vacío, no hay coincidencias
                    ok = False
                    break
                val = (r.get(col_key) or "")
                # Para fechas, compara por día únicamente
                if col_key in ("fecha", "fecha_entrega"):
                    val = _date_key(val)
                if val not in allowed:
                    ok = False
                    break
            if ok:
                out.append(r)
        return out


    def _pintar_tree_aplicando_filtros_y_orden(self):
        """Combinación: filtros de barra superior + filtros por columna + orden."""
        # 1) Filtros “barra superior”
        datos = self._filtrar_por_ui_superior(self._raw_pedidos)

        # 2) Filtros por encabezado (tipo Excel)
        datos = self._aplicar_filtros_header(datos)

        # 3) Orden
        if self._last_sort_col:
            asc = self._sort_state.get(self._last_sort_col, True)
            datos.sort(key=lambda r: (r.get(self._last_sort_col) or ""), reverse=not asc)
        else:
            # orden estable por prioridad si no hay columna seleccionada
            datos = sorted(datos, key=_orden_prioridad)

        # 4) Repintar
        for item in self.tree_pedidos.get_children():
            self.tree_pedidos.delete(item)

        for p in datos:
            estado = (p.get("estado","") or "").strip().lower()
            es_fantasma = _es_fantasma_row(p)

            if estado == "cancelado":
                tag = "row_cancelado"
            elif estado == "completado":
                tag = "row_completado"
            elif estado == "parcial":
                tag = "row_parcial"
            elif estado == "pendiente":
                tag = "row_pendiente"
            else:
                tag = "row_fantasma" if es_fantasma else "row_pendiente"
            if es_fantasma and estado != "completado":
                tag = "row_fantasma"

            self.tree_pedidos.insert(
                "", "end",
                values=(
                    p.get("id_pedido",""),
                    _fmt_dt_show(p.get("fecha","")),           # ← muestra con HH:MM
                    _fmt_dt_show(p.get("fecha_entrega","")),   # ← muestra con HH:MM
                    p.get("cliente",""),
                    p.get("total",""),
                    p.get("estado",""),
                    p.get("descuento","0")
                ),
                tags=(tag,)
            )

        # 5) Actualizar el texto de encabezados para indicar filtros activos (•)
        headers = {
            "id_pedido":"ID", "fecha":"Fecha", "fecha_entrega":"Entrega",
            "cliente":"Cliente", "total":"Total", "estado":"Estado", "descuento":"Desc."
        }
        for col in self._cols_p:
            base = headers[col]
            mark = " •" if col in self._active_filters else ""
            self.tree_pedidos.heading(col, text=base + mark)

        # limpiar detalle al repintar
        for item in self.tree_detalle.get_children():
            self.tree_detalle.delete(item)
        self._current_pedido = None
        self._current_descuento = "0"

    # ----------- Encabezado: click para filtros / Shift+click para ordenar -----------
    def _on_tree_click_heading(self, event):
        region = self.tree_pedidos.identify_region(event.x, event.y)
        if region != "heading":
            return  # deja pasar el click normal (selecciones, etc.)

        colid = self.tree_pedidos.identify_column(event.x)  # e.g. '#1'
        try:
            idx = int(colid.replace("#","")) - 1
        except Exception:
            return

        if not (0 <= idx < len(self._cols_p)):
            return
        key = self._cols_p[idx]

        # Shift presionado -> toggle sort
        if (event.state & 0x0001):  # Shift
            self._toggle_sort(key)
            return

        # Clic normal -> popup filtro
        self._open_filter_popup_for_column(key, event)

        # Cancelamos el comportamiento por defecto de redimensionar/ordenar headings
        return "break"

    def _toggle_sort(self, key):
        self._last_sort_col = key
        self._sort_state[key] = not self._sort_state.get(key, False)
        self._pintar_tree_aplicando_filtros_y_orden()

    def _open_filter_popup_for_column(self, key, event):
        # Cierra popup anterior si sigue abierto
        try:
            if hasattr(self, "_filter_popup") and self._filter_popup and self._filter_popup.winfo_exists():
                self._filter_popup.destroy()
        except Exception:
            pass

        # --- datos base ---
        MAX_W, MAX_H, MARGIN = 300, 420, 10
        base_x = self.tree_pedidos.winfo_rootx() + event.x
        base_y = self.tree_pedidos.winfo_rooty() + event.y + 20

        # --- popup ---
        top = tk.Toplevel(self.tree_pedidos)
        top.wm_overrideredirect(True)         # look tipo popup
        top.attributes("-topmost", True)
        self._filter_popup = top

        # flags anti-race
        _alive = {"ok": True}
        _after_id = {"id": None}
        _qtrace = {"id": None}

        def _exists(w):
            try:
                return bool(w and w.winfo_exists())
            except Exception:
                return False

        # contenedor principal
        frm = ttk.Frame(top, padding=8, style=self.frame_style)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Filtrar por: {key}", style=self.label_style).pack(anchor="w")

        qvar = tk.StringVar()
        ent = ttk.Entry(frm, textvariable=qvar)
        ent.pack(fill="x", pady=(4,6))
        ent.focus_set()

        # valores únicos (fechas por día)
        if key in ("fecha", "fecha_entrega"):
            vals = sorted({ _date_key(r.get(key)) for r in self._raw_pedidos })
        else:
            vals = sorted({ (r.get(key) or "") for r in self._raw_pedidos })

        preset = set(self._active_filters.get(key, set())) or set(vals)

        # "Seleccionar todo" + lista con scroll
        listfrm = ttk.Frame(frm, style=self.frame_style); listfrm.pack(fill="both", expand=True, pady=(2,6))
        var_all = tk.BooleanVar(value=(preset == set(vals)))
        ttk.Checkbutton(listfrm, text="(Seleccionar todo)", variable=var_all, style=self.label_style)\
            .pack(anchor="w")

        canvas = tk.Canvas(listfrm, highlightthickness=0, bg="#1e1e1e")
        sby = ttk.Scrollbar(listfrm, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style=self.frame_style)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sby.set)
        canvas.pack(side="left", fill="both", expand=True)
        sby.pack(side="right", fill="y")

        item_vars = []

        def _apply_and_close(selected_values:set):
            self._active_filters[key] = selected_values
            self._pintar_tree_aplicando_filtros_y_orden()
            _safe_close()

        def _apply_single(value):
            _apply_and_close({value})

        def _rebuild_items(filter_text=""):
            if not (_alive["ok"] and _exists(inner)):
                return

            # limpia lista
            for w in list(inner.winfo_children()):
                try: w.destroy()
                except: pass
            item_vars.clear()

            subset = [v for v in vals if filter_text.lower() in str(v).lower()]
            for v in subset:
                var = tk.BooleanVar(value=(v in preset))
                txt = v if v != "" else "N/A"
                cb = ttk.Checkbutton(inner, text=txt, variable=var, style=self.label_style)
                cb.pack(anchor="w")
                # doble clic o Enter → aplica solo ese
                cb.bind("<Double-Button-1>", lambda e, vv=v: _apply_single(vv))
                cb.bind("<Return>",          lambda e, vv=v: _apply_single(vv))
                item_vars.append((v, var))

            current = {v for v, vv in item_vars if vv.get()}
            var_all.set(len(subset) > 0 and len(current) == len(subset))

            _debounced_fit()

        def _set_all_checks(state: bool):
            for _, var in item_vars:
                var.set(state)

        # búsqueda incremental
        def on_q_changed(*_):
            if not (_alive["ok"] and _exists(top) and _exists(inner)):
                return
            _rebuild_items(qvar.get())
        _qtrace["id"] = qvar.trace_add("write", on_q_changed)

        # botones
        btns = ttk.Frame(frm, style=self.frame_style); btns.pack(fill="x")
        ttk.Button(btns, text="Aplicar", style=self.button_style,
                command=lambda: _apply_and_close({v for v, var in item_vars if var.get()}))\
            .pack(side="right")
        ttk.Button(btns, text="Limpiar", style=self.button_style,
                command=lambda: (_apply_and_close(set())))\
            .pack(side="right", padx=(6,0))
        ttk.Button(btns, text="Cerrar",  style=self.button_style,
                command=lambda: _safe_close())\
            .pack(side="left")

        # Enter en textbox → aplicar ese valor
        def _apply_from_entry(_e=None):
            val = (qvar.get() or "").strip()
            if not val:
                return
            if key in ("fecha", "fecha_entrega"):
                val = _date_key(val)
            _apply_and_close({val})
        ent.bind("<Return>", _apply_from_entry)

        # seleccionar todo toggle
        def _on_toggle_all():
            _set_all_checks(var_all.get())
        var_all.trace_add("write", lambda *_: _on_toggle_all())

        # ajuste de tamaño y posición (sin cerrar por clic-fuera)
        def _fit_height_and_place():
            if not (_alive["ok"] and _exists(top) and _exists(frm)):
                return
            try:
                top.update_idletasks()
                req_h = frm.winfo_reqheight()
            except Exception:
                return

            pop_h = min(req_h, MAX_H)
            if req_h > MAX_H and _exists(canvas):
                try:
                    cur_h = canvas.winfo_height() or 220
                    overflow = max(0, req_h - MAX_H)
                    canvas.config(height=max(120, cur_h - overflow))
                    top.update_idletasks()
                    req2 = frm.winfo_reqheight()
                    pop_h = min(req2, MAX_H)
                except Exception:
                    pass

            screen_w = top.winfo_screenwidth()
            screen_h = top.winfo_screenheight()
            px = max(MARGIN, min(base_x, screen_w - MAX_W - MARGIN))
            py = max(MARGIN, min(base_y, screen_h - pop_h - MARGIN))
            try:
                top.geometry(f"{MAX_W}x{pop_h}+{px}+{py}")
            except Exception:
                pass

        def _debounced_fit():
            if not _exists(top):
                return
            try:
                if _after_id["id"] is not None:
                    top.after_cancel(_after_id["id"])
            except Exception:
                pass
            _after_id["id"] = top.after(0, _fit_height_and_place)

        # cierre seguro único (sin unbinds globales)
        _state = {"closed": False}
        def _safe_close():
            if _state["closed"]:
                return
            _state["closed"] = True
            _alive["ok"] = False
            # cancela after
            try:
                if _after_id["id"] is not None and _exists(top):
                    top.after_cancel(_after_id["id"])
            except Exception:
                pass
            _after_id["id"] = None
            # quita trace
            try:
                if _qtrace["id"] is not None:
                    qvar.trace_remove("write", _qtrace["id"])
            except Exception:
                pass
            _qtrace["id"] = None
            # destruye popup
            try:
                if _exists(top):
                    top.destroy()
            except Exception:
                pass

        # binds de cierre
        top.bind("<Escape>", lambda e: _safe_close())
        top.bind("<Destroy>", lambda e: _safe_close())

        # pinta items iniciales y acomoda popup
        _rebuild_items("")
        _fit_height_and_place()






    # ---------------- Lógica original (detalle, ctx, editores, PDF) ----------------
    def _on_select_pedido(self, event=None):
        for item in self.tree_detalle.get_children():
            self.tree_detalle.delete(item)

        sel = self.tree_pedidos.selection()
        if not sel:
            self._current_pedido = None
            self._current_descuento = "0"
            return

        vals = self.tree_pedidos.item(sel[0])["values"]
        id_pedido = vals[0]
        self._current_pedido = id_pedido
        self._current_descuento = str(vals[6]) if len(vals) > 6 else "0"
        estado = (vals[5] or "").strip().lower() if len(vals) > 5 else ""

        try:
            items = leer_items_por_pedido(id_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el detalle.\n{e}")
            return

        for it in items:
            cant = int(it.get("cantidad") or 0)
            comp = int(it.get("cantidad_completada") or 0)
            pend = max(0, cant - comp)
            tag = "d_cancelado" if estado == "cancelado" else self._detail_tag_for(cant, comp)
            self.tree_detalle.insert(
                "", "end",
                values=(it.get("id_linea",""), it.get("producto",""),
                        str(cant), str(comp), str(pend),
                        it.get("precio_unitario",""), it.get("importe","")),
                tags=(tag,)
            )

    # --------- menú contextual ---------
    def _show_ctx_menu(self, event):
        rowid = self.tree_pedidos.identify_row(event.y)
        if rowid:
            self.tree_pedidos.selection_set(rowid)
            vals = self.tree_pedidos.item(rowid).get("values", [])
            if self._is_row_cancelado(vals):
                return
            try:
                self._ctx_menu.entryconfig("Asignar fecha de entrega…", state="normal")
                self._ctx_menu.entryconfig("Cancelar pedido…", state="normal")
            except Exception:
                pass
            self._ctx_menu.post(event.x_root, event.y_root)

    def _ctx_cancelar_pedido(self):
        sel = self.tree_pedidos.selection()
        if not sel:
            messagebox.showwarning("Atención", "Selecciona un pedido para cancelar.")
            return
        vals = self.tree_pedidos.item(sel[0])["values"]
        id_pedido = str(vals[0]) if vals else None
        cliente = str(vals[3]) if len(vals) > 3 else ""  # columna correcta: cliente
        if not id_pedido:
            messagebox.showwarning("Atención", "No se pudo determinar el ID del pedido.")
            return

        if not messagebox.askyesno(
            "Confirmar cancelación",
            f"¿Cancelar el pedido {id_pedido} de '{cliente}'?\n"
            f"Se pondrán 'Completado'=0 en sus líneas y el estado será 'Cancelado'."
        ):
            return

        try:
            ok = cancelar_pedido(id_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cancelar el pedido.\n{e}")
            return

        if ok:
            messagebox.showinfo("Cancelado", f"Pedido {id_pedido} cancelado.")
        else:
            messagebox.showinfo("Info", "No se realizaron cambios.")

        self.refrescar()
        for item in self.tree_detalle.get_children():
            self.tree_detalle.delete(item)
        self._current_pedido = None
        self._emit_refresh_all()

    def _is_row_cancelado(self, vals):
        estado = (str(vals[5]).strip().lower() if len(vals) > 5 else "")
        return estado in {"cancelado", "cancelada", "canceled", "cancelled"}

    # -------- Editor masivo / Editor pedido --------
    def _abrir_editor_masivo(self):
        iid = self.tree_pedidos.selection()
        if not iid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        vals = self.tree_pedidos.item(iid[0])["values"]
        if not vals:
            return

        id_pedido = str(vals[0])
        estado = (str(vals[5]) if len(vals) > 5 else "").strip().lower()
        es_fantasma = _es_fantasma_id_estado(id_pedido, estado)

        try:
            items = leer_items_por_pedido(id_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer las líneas.\n{e}")
            return

        def _saved():
            self.refrescar()
            self._emit_refresh_all()

        EditorMasivo(
            self.frame, id_pedido, items, on_saved=_saved,
            frame_style=self.frame_style, button_style=self.button_style, label_style=self.label_style,
            use_sync=es_fantasma,
        )

    def _abrir_editor_pedido(self):
        iid = self.tree_pedidos.selection()
        if not iid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        vals = self.tree_pedidos.item(iid[0])["values"]
        if not vals:
            return

        # Columnas: ("id_pedido","fecha","fecha_entrega","cliente","total","estado","descuento")
        id_pedido = str(vals[0])
        fecha     = str(vals[1] or "")
        cliente   = str(vals[3] or "")
        desc_flag = str(vals[6] or "").strip().lower() in ("1", "true", "sí", "si", "y", "yes")

        try:
            items = leer_items_por_pedido(id_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer las líneas del pedido.\n{e}")
            return

        def _saved():
            self.refrescar()
            self._emit_refresh_all()

        EditorPedido(
            self.frame, id_pedido, cliente, fecha, items, desc_flag,
            on_saved=_saved,
            frame_style=self.frame_style, button_style=self.button_style, label_style=self.label_style
        )

    # -------- Generar PDF --------
    def _generar_pdf_pedido_sel(self):
        iid = self.tree_pedidos.selection()
        if not iid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        vals = self.tree_pedidos.item(iid[0])["values"]
        if not vals:
            return
        id_pedido = str(vals[0])
        cliente   = str(vals[3]) if len(vals) > 3 else ""  # cliente correcto
        fecha     = str(vals[1]) if len(vals) > 1 else datetime.now().strftime("%Y-%m-%d %H:%M")
        estado    = (vals[5] or "").strip().lower() if len(vals) > 5 else ""

        items_raw = leer_items_por_pedido(id_pedido)
        if not items_raw:
            messagebox.showwarning("Atención", "Este pedido no tiene líneas.")
            return

        items = []
        for r in items_raw:
            c = int(r.get("cantidad") or 0)
            comp = int(r.get("cantidad_completada") or 0)
            if c > 0 and comp >= c:  # SOLO las completadas
                try:
                    punit = float(str(r.get("precio_unitario","0")).replace(",", "."))
                except:
                    punit = 0.0
                importe = punit * c
                items.append({
                    "cantidad": c,
                    "producto": r.get("producto",""),
                    "precio_unitario": f"{punit:.2f}",
                    "importe": f"{importe:.2f}",
                })

        if not items:
            messagebox.showwarning("Atención", "No hay productos completados para generar la nota.")
            return

        try:
            pdf_path = generar_pdf_pedido(
                id_pedido=id_pedido,
                cliente=cliente,
                fecha_str=fecha,
                items=items,
                logo_path="logo.png",
                qr_kind="QR",
                cancelado = (estado == "cancelado"),
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF.\n{e}")
            return

        abrir_pdf(pdf_path)
        messagebox.showinfo("Listo", f"Nota generada (reemplazada si existía).\n\n{os.path.basename(pdf_path)}")

    def _get_selected_pedido_id(self):
        sel = self.tree_pedidos.selection()
        if not sel:
            return None
        vals = self.tree_pedidos.item(sel[0])["values"]
        return str(vals[0]) if vals else None

    def _ctx_set_fecha_entrega(self):
        pid = self._get_selected_pedido_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return

        win = tk.Toplevel(self.frame)
        win.title(f"Fecha de entrega – {pid}")
        win.transient(self.frame.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=12, style=self.frame_style)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Fecha de entrega:", style=self.label_style).grid(row=0, column=0, sticky="w")

        now = datetime.now()
        if '_HAS_TKCAL' in globals() and _HAS_TKCAL:
            self._date_picker = DateEntry(frm, width=14, year=now.year, month=now.month, day=now.day, date_pattern="yyyy-mm-dd")
            self._date_picker.grid(row=1, column=0, sticky="w", pady=(2,6))
        else:
            row2 = ttk.Frame(frm, style=self.frame_style); row2.grid(row=1, column=0, sticky="w", pady=(2,6))
            self._spn_year  = ttk.Spinbox(row2, from_=now.year-5, to=now.year+5, width=6);  self._spn_year.set(str(now.year))
            self._spn_month = ttk.Spinbox(row2, from_=1, to=12,           width=4);         self._spn_month.set(str(now.month))
            self._spn_day   = ttk.Spinbox(row2, from_=1, to=31,           width=4);         self._spn_day.set(str(now.day))
            ttk.Label(row2, text="Año", style=self.label_style).pack(side="left", padx=(0,4)); self._spn_year.pack(side="left")
            ttk.Label(row2, text="Mes", style=self.label_style).pack(side="left", padx=(8,4)); self._spn_month.pack(side="left")
            ttk.Label(row2, text="Día", style=self.label_style).pack(side="left", padx=(8,4)); self._spn_day.pack(side="left")

        row_time = ttk.Frame(frm, style=self.frame_style); row_time.grid(row=2, column=0, sticky="w", pady=(4,2))
        ttk.Label(row_time, text="Hora:", style=self.label_style).pack(side="left", padx=(0,4))
        self._spn_hour = ttk.Spinbox(row_time, from_=0, to=23, width=4); self._spn_hour.set(f"{now.hour:02d}"); self._spn_hour.pack(side="left")
        ttk.Label(row_time, text="Min:", style=self.label_style).pack(side="left", padx=(8,4))
        self._spn_min  = ttk.Spinbox(row_time, from_=0, to=59, width=4, increment=5); self._spn_min.set(f"{now.minute:02d}"); self._spn_min.pack(side="left")

        btns = ttk.Frame(frm, style=self.frame_style); btns.grid(row=3, column=0, sticky="ew", pady=(10,0))
        def _use_now():
            t = datetime.now()
            if '_HAS_TKCAL' in globals() and _HAS_TKCAL:
                self._date_picker.set_date(t.date())
            else:
                self._spn_year.set(str(t.year)); self._spn_month.set(str(t.month)); self._spn_day.set(str(t.day))
            self._spn_hour.set(f"{t.hour:02d}"); self._spn_min.set(f"{t.minute:02d}")

        def _clear():
            try:
                ok = set_fecha_entrega(pid, "")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo limpiar la fecha de entrega.\n{e}", parent=win)
                return
            if ok:
                messagebox.showinfo("Listo", f"Se limpió la fecha de entrega para {pid}.", parent=win)
                try: win.grab_release()
                except: pass
                win.destroy(); self.refrescar(); self._emit_refresh_all()

        def _save():
            try:
                hh = int(self._spn_hour.get()); mm = int(self._spn_min.get())
                if not (0 <= hh <= 23 and 0 <= mm <= 59): raise ValueError
            except Exception:
                messagebox.showerror("Error", "Hora o minuto inválidos.", parent=win); return
            try:
                if '_HAS_TKCAL' in globals() and _HAS_TKCAL:
                    d = self._date_picker.get_date(); y, m, d_ = d.year, d.month, d.day
                else:
                    y = int(self._spn_year.get()); m = int(self._spn_month.get()); d_ = int(self._spn_day.get())
                dt = datetime(year=y, month=m, day=d_, hour=hh, minute=mm)
            except Exception:
                messagebox.showerror("Error", "Fecha inválida.", parent=win); return

            try:
                ok = set_fecha_entrega(pid, dt.strftime("%Y-%m-%d %H:%M"))
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo establecer la fecha de entrega.\n{e}", parent=win)
                return

            if ok:
                messagebox.showinfo("Listo", f"Fecha de entrega actualizada para {pid}.", parent=win)
                try: win.grab_release()
                except: pass
                win.destroy(); self.refrescar(); self._emit_refresh_all()
            else:
                messagebox.showinfo("Info", "No se realizaron cambios.", parent=win)

        ttk.Button(btns, text="Usar ahora", command=_use_now,  style=self.button_style).pack(side="left")
        ttk.Button(btns, text="Limpiar",    command=_clear,    style=self.button_style).pack(side="left", padx=(8,0))
        ttk.Button(btns, text="Guardar",    command=_save,     style=self.button_style).pack(side="right")
        ttk.Button(btns, text="Cancelar",   command=lambda:(win.grab_release(), win.destroy()), style=self.button_style).pack(side="right", padx=(0,8))

        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")


# ---------------- Ventana: editor masivo (completados) ----------------
class EditorMasivo(tk.Toplevel):
    def __init__(self, parent, id_pedido, items, on_saved,
                 frame_style="Dark.TFrame",
                 button_style="Dark.TButton",
                 label_style="Dark.TLabel",
                 use_sync=False):
        
        super().__init__(parent)
        self.title(f"Editar líneas · Pedido {id_pedido}")
        self.transient(parent); self.grab_set(); self.resizable(True, True)

        self.id_pedido = id_pedido
        self.items = items
        self.on_saved = on_saved
        self.frame_style = frame_style
        self.button_style = button_style
        self.label_style = label_style

        self.use_sync = bool(use_sync)

        # Importamos aquí para evitar circularidad
        if self.use_sync:
            self._actualizar_batch = actualizar_cantidades_completadas_batch_sync  # <-- usa sync
        else:
            self._actualizar_batch = actualizar_cantidades_completadas_batch       # <-- normal

        rootf = ttk.Frame(self, style=self.frame_style); rootf.pack(fill="both", expand=True)
        header = ttk.Frame(rootf, style=self.frame_style); header.pack(fill="x", padx=15, pady=(12, 6))
        ttk.Label(header, text=f"Pedido: {id_pedido}", style=self.label_style).pack(side="left")

        container = ttk.Frame(rootf, style=self.frame_style); container.pack(fill="both", expand=True, padx=15, pady=5)
        canvas = tk.Canvas(container, highlightthickness=0, bg="#1e1e1e")
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollf = ttk.Frame(canvas, style=self.frame_style)
        scrollf_id = canvas.create_window((0, 0), window=scrollf, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        scrollf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(scrollf_id, width=e.width))
        canvas.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")

        row = 0
        for txt, col in [("ID Línea",0),("Producto",1),("Cant.",2),("Completado",3),("Pendiente",4)]:
            ttk.Label(scrollf, text=txt, style=self.label_style).grid(row=row, column=col, sticky="w", padx=6, pady=4)

        vcmd = (self.register(self._validate_int_or_empty), "%P")

        self._line_vars = []
        for it in self.items:
            row += 1
            id_linea = it.get("id_linea","")
            producto = it.get("producto","")
            cant = int(it.get("cantidad") or 0)
            comp = int(it.get("cantidad_completada") or 0)
            pend = max(0, cant - comp)

            ttk.Label(scrollf, text=id_linea, style=self.label_style).grid(row=row, column=0, sticky="w", padx=6, pady=3)
            ttk.Label(scrollf, text=producto, style=self.label_style).grid(row=row, column=1, sticky="w", padx=6, pady=3)
            ttk.Label(scrollf, text=str(cant), style=self.label_style).grid(row=row, column=2, sticky="e", padx=6, pady=3)

            var = tk.IntVar(value=comp)
            spin = ttk.Spinbox(
                scrollf, from_=0, to=cant, textvariable=var, width=8,
                validate="key", validatecommand=vcmd
            )
            spin.grid(row=row, column=3, sticky="e", padx=6, pady=3)

            lbl_pend = ttk.Label(scrollf, text=str(pend), style=self.label_style)
            lbl_pend.grid(row=row, column=4, sticky="e", padx=6, pady=3)

            var.trace_add("write", lambda *_,
                          v=var, c=cant, lab=lbl_pend: self._on_spin_change(v, c, lab))

            self._line_vars.append((id_linea, cant, var))

        btns = ttk.Frame(rootf, style=self.frame_style); btns.pack(fill="x", padx=15, pady=(6, 12))
        ttk.Button(btns, text="Completar todo", command=self._completar_todo, style=self.button_style).pack(side="left")
        ttk.Button(btns, text="Guardar cambios", command=self._guardar, style=self.button_style).pack(side="right", padx=(6,0))
        ttk.Button(btns, text="Cancelar", command=self.destroy, style=self.button_style).pack(side="right", padx=(6,0))
        self.geometry("900x600+120+80")

    # ===== Helpers de validación/lectura segura =====
    def _validate_int_or_empty(self, proposed: str) -> bool:
        if proposed == "":
            return True
        return proposed.isdigit()

    def _safe_int(self, var: tk.Variable) -> int:
        try:
            val = var.get()
            return int(float(str(val))) if str(val).strip() != "" else 0
        except Exception:
            return 0

    def _on_spin_change(self, var: tk.Variable, cantidad_total: int, label_pend: ttk.Label):
        val = self._safe_int(var)
        val = max(0, min(val, cantidad_total))
        label_pend.config(text=str(max(0, cantidad_total - val)))

    def _completar_todo(self):
        for (_id, cant, var) in self._line_vars:
            var.set(cant)

    def _guardar(self):
        updates = []
        for (id_linea, cant_total, var) in self._line_vars:
            val = self._safe_int(var)
            val = max(0, min(val, cant_total))
            updates.append((id_linea, val))
        if not updates:
            self.destroy(); 
            return

        try:
            if self.use_sync:
                # Fantasma: SIEMPRE usa la función sincronizada y pasa id_pedido
                res = actualizar_cantidades_completadas_batch_sync(self.id_pedido, updates)
            else:
                # Pedido normal
                res = actualizar_cantidades_completadas_batch(updates)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el lote.\n{e}")
            return

        # Mensajería
        if isinstance(res, dict) and res:
            if len(res) > 1:
                resumen = "\n".join([f"{k}: {v}" for k, v in sorted(res.items())])
                messagebox.showinfo("Éxito", f"Cambios guardados.\nEstados:\n{resumen}")
            else:
                nuevo_estado = res.get(self.id_pedido)
                if nuevo_estado:
                    messagebox.showinfo("Éxito", f"Cambios guardados.\nNuevo estado: {nuevo_estado}")
                else:
                    messagebox.showinfo("Éxito", "Cambios guardados.")
        else:
            messagebox.showinfo("Éxito", "Cambios guardados.")

        if callable(self.on_saved):
            self.on_saved()
        self.destroy()



# ---------------- Ventana: editor completo del pedido ----------------
class EditorPedido(tk.Toplevel):
    """
    - Sugiere productos conforme tecleas (Entry + Listbox flotante por fila)
    - Si el pedido fue hecho con descuento, usa precio_desc al elegir producto.
      Si no, usa precio normal.
    - No sobreescribe P.Unit si ya tiene un valor > 0.
    """
    def __init__(self, parent, id_pedido, cliente, fecha, items, use_discount,
                 on_saved,
                 frame_style="Dark.TFrame",
                 button_style="Dark.TButton",
                 label_style="Dark.TLabel"):
        super().__init__(parent)
        self.title(f"Editar pedido · {id_pedido}")
        self.transient(parent); self.grab_set(); self.resizable(True, True)

        self.id_pedido = id_pedido
        self.on_saved = on_saved
        self.items = items
        self.use_discount = bool(use_discount)
        self.frame_style = frame_style
        self.button_style = button_style
        self.label_style = label_style

        try:
            catalogo = cargar_productos()
        except Exception:
            catalogo = []
        self.product_names = sorted([p["producto"] for p in catalogo if p.get("producto")])
        self.price_normal = {}
        self.price_desc = {}
        for p in catalogo:
            name = p.get("producto","")
            if not name: continue
            try:
                pn = float((p.get("precio") or "0").replace(",", "."))
            except:
                pn = 0.0
            try:
                pd = float((p.get("precio_desc") or p.get("precio") or "0").replace(",", "."))
            except:
                pd = pn
            self.price_normal[name] = pn
            self.price_desc[name] = pd

        rootf = ttk.Frame(self, style=self.frame_style); rootf.pack(fill="both", expand=True)

        head = ttk.Frame(rootf, style=self.frame_style); head.pack(fill="x", padx=15, pady=(12,6))
        ttk.Label(head, text="Cliente:", style=self.label_style).grid(row=0, column=0, sticky="e", padx=(0,6))
        self.var_cliente = tk.StringVar(value=cliente)
        ttk.Entry(head, textvariable=self.var_cliente, width=40).grid(row=0, column=1, sticky="w")

        ttk.Label(head, text="Fecha (YYYY-MM-DD HH:MM):", style=self.label_style).grid(row=0, column=2, sticky="e", padx=(12,6))
        self.var_fecha = tk.StringVar(value=fecha or datetime.now().strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(head, textvariable=self.var_fecha, width=22).grid(row=0, column=3, sticky="w")

        info = ttk.Frame(rootf, style=self.frame_style); info.pack(fill="x", padx=15, pady=(0,6))
        ttk.Label(info, text=f"Precios por defecto: {'CON DESCUENTO' if self.use_discount else 'NORMALES'}",
                  style=self.label_style).pack(side="left")

        cont = ttk.Frame(rootf, style=self.frame_style); cont.pack(fill="both", expand=True, padx=15, pady=5)
        canvas = tk.Canvas(cont, highlightthickness=0, bg="#1e1e1e")
        vsb = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
        self.tablef = ttk.Frame(canvas, style=self.frame_style)
        table_id = canvas.create_window((0, 0), window=self.tablef, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        self.tablef.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(table_id, width=e.width))
        canvas.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")

        row = 0
        for txt, col, anchor in [("ID Línea",0,"w"),("Producto",1,"w"),("Cantidad",2,"e"),("P.Unit",3,"e"),("Importe",4,"e")]:
            ttk.Label(self.tablef, text=txt, style=self.label_style).grid(row=row, column=col, sticky=anchor, padx=6, pady=4)

        self._rows = []
        for it in self.items:
            row += 1
            id_linea = it.get("id_linea","")
            prod = it.get("producto","")
            cant = int(it.get("cantidad") or 0)
            punit = str(it.get("precio_unitario","") or "0")
            imp = it.get("importe","") or "0"

            ttk.Label(self.tablef, text=id_linea, style=self.label_style).grid(row=row, column=0, sticky="w", padx=6, pady=3)

            vprod = tk.StringVar(value=prod)
            ent_prod = ttk.Entry(self.tablef, textvariable=vprod, width=36)
            ent_prod.grid(row=row, column=1, sticky="w", padx=6, pady=3)
            sugg = SuggestPopup(self, ent_prod, self.product_names,
                                on_pick=lambda name, vp=vprod, r=row: self._on_pick_product(name, vp, r))

            vcant = tk.IntVar(value=cant)
            sp = ttk.Spinbox(self.tablef, from_=0, to=999999, textvariable=vcant, width=10)
            sp.grid(row=row, column=2, sticky="e", padx=6, pady=3)

            vpu = tk.StringVar(value=punit)
            ent_pu = ttk.Entry(self.tablef, textvariable=vpu, width=12)
            ent_pu.grid(row=row, column=3, sticky="e", padx=6, pady=3)

            limpp = ttk.Label(self.tablef, text=str(imp), style=self.label_style)
            limpp.grid(row=row, column=4, sticky="e", padx=6, pady=3)

            def make_recalc(vq=vcant, vpu=vpu, lbl=limpp):
                def _do(*_):
                    try:
                        q = max(0, int(str(vq.get() or "0")))
                    except:
                        q = 0
                    try:
                        pu = float(str(vpu.get()).replace("$","").replace(",","").strip() or "0")
                    except:
                        pu = 0.0
                    lbl.config(text=f"{q*pu:.2f}")
                return _do
            vcant.trace_add("write", make_recalc())
            vpu.trace_add("write", make_recalc())

            self._rows.append((id_linea, ent_prod, vprod, vcant, vpu, limpp, sugg))

        # --- debajo de la tabla, botones ---
        line_btns = ttk.Frame(rootf, style=self.frame_style); line_btns.pack(fill="x", padx=15, pady=(6,0))
        ttk.Button(line_btns, text="Agregar línea", command=self._add_line, style=self.button_style).pack(side="left")

        bottom = ttk.Frame(rootf, style=self.frame_style); bottom.pack(fill="x", padx=15, pady=(8,12))
        ttk.Label(bottom, text="Total:", style=self.label_style).pack(side="left")
        self.lbl_total = ttk.Label(bottom, text="0.00", style=self.label_style); self.lbl_total.pack(side="left", padx=(6,0))
        ttk.Button(bottom, text="Guardar", command=self._guardar, style=self.button_style).pack(side="right")
        ttk.Button(bottom, text="Cancelar", command=self.destroy, style=self.button_style).pack(side="right", padx=(6,0))

        self._recalc_total()
        self.geometry("1000x650+120+80")

    # ----- helpers/validación EditorPedido -----
    def _validate_int_or_empty(self, value: str) -> bool:
        return value == "" or value.isdigit()

    # ----- callbacks EditorPedido -----
    def _on_pick_product(self, name: str, vprod: tk.StringVar, rowindex: int):
        vprod.set(name)
        for (_id, ent_prod, vp, vcant, vpu, limpp, sugg) in self._rows:
            if vp is vprod:
                current = (vpu.get() or "0").strip()
                try:
                    current_val = float(current.replace(",", "."))
                except:
                    current_val = 0.0
                if current == "" or current_val == 0.0:
                    price = self.price_desc.get(name, 0.0) if self.use_discount else self.price_normal.get(name, 0.0)
                    vpu.set(f"{price:.2f}")
                break
        self._recalc_total()

    def _add_line(self):
        """Agrega una única fila de edición sin duplicados."""
        pref = f"{self.id_pedido}-"
        max_n = 0
        for (rid, *_rest) in self._rows:
            if rid and str(rid).startswith(pref):
                try:
                    max_n = max(max_n, int(str(rid).split("-")[-1]))
                except Exception:
                    pass
        new_id = f"{self.id_pedido}-{max_n + 1}"

        row = len(self._rows) + 1

        ttk.Label(self.tablef, text=new_id, style=self.label_style)\
            .grid(row=row, column=0, sticky="w", padx=6, pady=3)

        vprod = tk.StringVar(value="")
        ent_prod = ttk.Entry(self.tablef, textvariable=vprod, width=36)
        ent_prod.grid(row=row, column=1, sticky="w", padx=6, pady=3)

        vcant = tk.IntVar(value=0)
        sp_q = ttk.Spinbox(
            self.tablef, from_=0, to=999999, textvariable=vcant, width=10,
            validate="key",
            validatecommand=(self.register(self._validate_int_or_empty), "%P"),
        )
        sp_q.grid(row=row, column=2, sticky="e", padx=6, pady=3)

        vpu = tk.StringVar(value="0")
        ent_pu = ttk.Entry(self.tablef, textvariable=vpu, width=12)
        ent_pu.grid(row=row, column=3, sticky="e", padx=6, pady=3)

        limpp = ttk.Label(self.tablef, text="0.00", style=self.label_style)
        limpp.grid(row=row, column=4, sticky="e", padx=6, pady=3)

        try:
            sugg = SuggestPopup(
                self, ent_prod, self.product_names,
                on_pick=lambda name, v=vprod, r=row: self._on_pick_product(name, v, r),
            )
        except NameError:
            sugg = None

        ent_prod.bind("<Return>", lambda e: "break")
        sp_q.bind("<Return>", lambda e: "break")
        ent_pu.bind("<Return>", lambda e: "break")

        def recalc(*_):
            try:
                q = max(0, int(str(vcant.get() or "0")))
            except Exception:
                q = 0
            pu_txt = str(vpu.get() or "0").replace("$", "").replace(",", "").strip()
            try:
                pu = float(pu_txt or "0")
            except Exception:
                pu = 0.0
            limpp.config(text=f"{q * pu:.2f}")
            self._recalc_total()

        vcant.trace_add("write", recalc)
        vpu.trace_add("write", recalc)

        self._rows.append((new_id, ent_prod, vprod, vcant, vpu, limpp, sugg))
        self._recalc_total()

    def _purge_empty(self):
        self._recalc_total()
        messagebox.showinfo("Info", "Al guardar, las líneas sin producto o con cantidad 0 no se guardarán.")

    def _recalc_total(self):
        total = 0.0
        for (_id, ent, vprod, q, vpu, limpp, sugg) in self._rows:
            try:
                total += float(limpp.cget("text") or "0")
            except:
                pass
        if hasattr(self, "lbl_total"):
            self.lbl_total.config(text=f"{total:.2f}")

    def _guardar(self):
        # --- Validación encabezado ---
        cliente = (self.var_cliente.get() or "").strip()
        fecha = (self.var_fecha.get() or "").strip()
        if not cliente:
            messagebox.showerror("Error", "Cliente no puede estar vacío.")
            return
        try:
            dt = _parse_fecha_flexible(fecha)
            # normaliza a canónico antes de guardar
            fecha = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            messagebox.showerror(
                "Error",
                "Fecha inválida. Usa por ejemplo:\n"
                "• 2025-10-20 19:12  (YYYY-MM-DD HH:MM)\n"
                "• 20/10/2025 19:12  (DD/MM/YYYY HH:MM)"
            )
            return

        def norm_price(txt: str) -> float:
            if txt is None:
                return 0.0
            s = str(txt).strip().replace(" ", "").replace("$", "")
            if not s:
                return 0.0
            has_c = "," in s; has_d = "." in s
            if has_c and has_d:
                if s.rfind(",") > s.rfind("."):
                    s = s.replace(".", ""); s = s.replace(",", ".")
                else:
                    s = s.replace(",", "")
            elif has_c and not has_d:
                s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
            else:
                if s.count(".") > 1:
                    parts = s.split("."); s = "".join(parts[:-1]) + "." + parts[-1]
            try:
                return float(s)
            except Exception:
                return 0.0

        nuevas = []
        seen_ids = set()
        for (id_linea, ent, vprod, q, vpu, limpp, _sugg) in self._rows:
            line_id = str(id_linea or "").strip()
            prod = (vprod.get() or "").strip()
            try:
                cant = int(q.get() or 0)
            except Exception:
                cant = 0
            pu_val = norm_price((vpu.get() or "0").strip())
            if cant <= 0 or not prod:
                continue
            if line_id in seen_ids:
                continue
            seen_ids.add(line_id)
            nuevas.append({
                "id_linea": line_id,
                "producto": prod,
                "cantidad": cant,
                "precio_unitario": f"{pu_val:.2f}",
                "importe": f"{cant * pu_val:.2f}",
            })

        if not nuevas:
            if not messagebox.askyesno("Confirmar", "Todas las líneas quedaron en 0 o vacías.\n¿Guardar el pedido SIN líneas?"):
                return

        try:
            actualizar_pedido_completo(self.id_pedido, cliente, fecha, nuevas)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el pedido.\n{e}")
            return

        messagebox.showinfo("Éxito", "Pedido actualizado.")
        if callable(self.on_saved):
            self.on_saved()
        self.destroy()


# ---------- Sugerencias tipo “Nueva Nota” ----------
class SuggestPopup:
    """
    Lista de sugerencias flotante para un Entry.
    - Filtra por subcadena (case-insensitive) mientras se escribe.
    - Flechas ↑/↓ navegan; Enter selecciona; Escape cierra.
    """
    def __init__(self, parent_window, entry: ttk.Entry, options: list[str], on_pick):
        self.parent = parent_window
        self.entry = entry
        self.all_options = options[:]
        self.on_pick = on_pick

        self.popup = None
        self.listbox = None

        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Down>", self._focus_list)
        self.entry.bind("<Escape>", lambda e: self._hide())

    def _on_key(self, event):
        text = (self.entry.get() or "").lower().strip()
        if not text:
            self._hide()
            return
        matches = [o for o in self.all_options if text in o.lower()]
        if not matches:
            self._hide()
            return
        self._show(matches)

    def _show(self, items):
        if self.popup is None:
            self.popup = tk.Toplevel(self.entry)
            self.popup.wm_overrideredirect(True)
            self.popup.configure(bg="#1e1e1e")
            self.listbox = tk.Listbox(self.popup, height=6, bg="#2d2d2d", fg="white", selectbackground="#3a3a3a")
            self.listbox.pack(fill="both", expand=True)
            self.listbox.bind("<Double-Button-1>", self._choose)
            self.listbox.bind("<Return>", self._choose)
            self.listbox.bind("<Escape>", lambda e: self._hide())
            self.listbox.bind("<Up>", self._nav)
            self.listbox.bind("<Down>", self._nav)

        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = self.entry.winfo_width()
        self.popup.geometry(f"{w}x140+{x}+{y}")

        self.listbox.delete(0, tk.END)
        for it in items:
            self.listbox.insert(tk.END, it)
        self.popup.deiconify()

    def _hide(self):
        if self.popup:
            self.popup.withdraw()

    def _focus_list(self, event):
        if self.popup and self.listbox and self.listbox.size() > 0:
            self.listbox.focus_set()
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
            return "break"

    def _choose(self, event):
        if not (self.popup and self.listbox):
            return
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        try:
            self.on_pick(name)
        finally:
            self._hide()

    def _nav(self, event):
        if not self.listbox: return
        size = self.listbox.size()
        if size == 0: return
        sel = self.listbox.curselection()
        idx = sel[0] if sel else -1
        if event.keysym == "Down":
            idx = min(size-1, idx+1)
        elif event.keysym == "Up":
            idx = max(0, idx-1)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        return "break"
