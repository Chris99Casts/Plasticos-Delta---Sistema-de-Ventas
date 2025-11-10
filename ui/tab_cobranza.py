import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
from tkinter import simpledialog 
import os, json, secrets, hashlib
from data.csv_manager import (
    leer_pedidos,
    total_cobro_actual,
    total_abonado,
    descuento_eligibilidad,
    set_fecha_entrega,
    aplicar_descuento_forzado,
    quitar_descuento_forzado,
    registrar_abono,
    leer_abonos,
    set_no_factura,
)

# Misma ruta/usuario/semilla que TabNuevaNota
ADMIN_CFG = os.path.join(os.getcwd(), "admin_cfg.json")
ADMIN_USER = "JPerez"
DEFAULT_ADMIN_PASS = "18062002"

def _try_parse_dt(s: str):
    s = (s or "").strip()
    if not s: return None
    formatos = [
        "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M", "%Y.%m.%d %H:%M",
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y.%m.%d"
    ]
    for f in formatos:
        try: return datetime.strptime(s, f)
        except: pass
    return None

def _fmt_dt_show(s: str) -> str:
    dt = _try_parse_dt(s)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else (s or "")

def _date_key(s: str) -> str:
    dt = _try_parse_dt(s)
    return dt.strftime("%Y-%m-%d") if dt else (s or "")

# Intentar importar tkcalendar (mini calendario)
_HAS_TKCAL = False
try:
    from tkcalendar import DateEntry
    _HAS_TKCAL = True
except Exception:
    _HAS_TKCAL = False


class TabCobranza:
    def __init__(self, notebook,
                 frame_style="Dark.TFrame",
                 tree_style="Dark.Treeview",
                 button_style="Dark.TButton",
                 on_refresh_all=None,
                 label_style="Dark.TLabel"):
        self.frame_style = frame_style
        self.tree_style = tree_style
        self.button_style = button_style
        self.label_style = label_style
        self.on_refresh_all = on_refresh_all

        # --- Estado filtros tipo Excel ---
        self._active_filters = {}      # {col_id: set(valores)}
        self._raw_rows = []            # filas ya "enriquecidas" para mostrar/filtrar

        self.frame = ttk.Frame(notebook, style=self.frame_style)
        self._dlg_abono = None   # ventana de abonos (evitar múltiples)

        # Estado inicial bloqueado
        self._unlocked = False
        self.tree = None  # <- importante para que refrescar() pueda checar
        self._build_locked_gate()
    
    # ------------------- Admin -----------------------------

    def _admin_load_cfg(self):
        # si no existe, inicializa con pass por defecto (mismo comportamiento que Nueva Nota)
        try:
            with open(ADMIN_CFG, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"user": ADMIN_USER, "salt": secrets.token_hex(16), "hash": ""}

        if not data.get("hash"):
            # primer uso: genera hash de DEFAULT_ADMIN_PASS
            data["user"] = ADMIN_USER
            if not data.get("salt"):
                data["salt"] = secrets.token_hex(16)
            data["hash"] = hashlib.sha256((DEFAULT_ADMIN_PASS + data["salt"]).encode("utf-8")).hexdigest()
            try:
                with open(ADMIN_CFG, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return data

    def _admin_check(self, user, password):
        cfg = self._admin_load_cfg()
        if (user or "").strip() != (cfg.get("user") or ADMIN_USER):
            return False
        salt = cfg.get("salt") or ""
        expect = cfg.get("hash") or ""
        h = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return h == expect


    # ------------------- Emitir refresh ----------------------
    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()

    # ------------------- UI principal ------------------------
    def _build_ui(self):
        top = ttk.Frame(self.frame, style=self.frame_style)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8,6))
        top.grid_columnconfigure(99, weight=1)

        box = ttk.Frame(top, style=self.frame_style)
        box.grid(row=0, column=0, sticky="w")

        ttk.Label(box, text="Pedido #:", style=self.label_style).pack(side="left", padx=(0,6))
        self.var_buscar = tk.StringVar()
        ent = ttk.Entry(box, textvariable=self.var_buscar, width=18)
        ent.pack(side="left")
        ent.bind("<Return>", lambda e: self.refrescar())

        ttk.Button(box, text="Buscar", command=self.refrescar, style=self.button_style)\
        .pack(side="left", padx=(8,0))
        ttk.Button(box, text="Limpiar", command=self._limpiar, style=self.button_style)\
        .pack(side="left", padx=(6,0))
        ttk.Button(box, text="Quitar filtros", command=self._reset_header_filters, style=self.button_style)\
        .pack(side="left", padx=(6,0))

        

        cols = (
            "id_pedido","fecha","fecha_entrega","no_factura","cliente","total",
            "preferencial","estado_surtido","pagado",
            "elegible10","dias_entrega",
            "total_cobro_actual","abonado","saldo",
            "desc_fijo_pct","total_fijo"
        )
        headers = {
            "id_pedido":"ID",
            "fecha":"Fecha pedido",
            "fecha_entrega":"Fecha entrega",
            "no_factura":"No. factura",
            "cliente":"Cliente",
            "total":"Total",
            "preferencial":"Preferencial",
            "estado_surtido":"Estado surtido",
            "pagado":"Pagado",
            "elegible10":"Elegible 10%",
            "dias_entrega":"Días desde entrega",
            "total_cobro_actual":"Total a cobrar (actual)",
            "abonado":"Abonado",
            "saldo":"Saldo",
            "desc_fijo_pct":"Desc. fijo (%)",
            "total_fijo":"Total fijo",
        }
        self._cols = cols  # ← mantener orden para pintado/filtrado
        self.DATE_COLS = {"fecha", "fecha_entrega"}  # ← filtran por día

        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=18, style=self.tree_style)

        for c in cols:
            # Encabezado "clicable" para abrir popup de filtro por columna
            self.tree.heading(c, text=headers[c], command=lambda col=c: self._open_filter_popup_for_column(col))
            width_map = {
                "id_pedido":110, "fecha":150, "fecha_entrega":160, "no_factura":130,"cliente":220, "total":100,
                "preferencial":95, "estado_surtido":110, "pagado":70, "elegible10":95,
                "dias_entrega":120, "total_cobro_actual":160, "abonado":110, "saldo":110,
                "desc_fijo_pct":105, "total_fijo":110
            }
            self.tree.column(c, anchor="center", width=width_map.get(c, 100), stretch=False)

        # Menú contextual
        self._ctx = tk.Menu(self.frame, tearoff=0)
        # índices: 0:abono, 1:historial, 2:sep, 3:aplicar desc, 4:quitar desc, 5:registrar factura, 6:sep
        self._ctx.add_command(label="Registrar abono…", command=self._menu_registrar_abono)
        self._ctx.add_command(label="Ver historial de abonos…", command=self._menu_historial_abonos)
        self._ctx.add_separator()
        self._ctx.add_command(label="Aplicar descuento forzado 10%…", command=self._aplicar_desc_forzado)
        self._ctx.add_command(label="Quitar descuento forzado…", command=self._quitar_desc_forzado)
        self._ctx.add_command(label="Registrar factura…", command=self._menu_registrar_factura)
        self._ctx.add_separator()

        self.tree.bind("<Button-3>", self._show_ctx)
        self.tree.bind("<Control-Button-1>", self._show_ctx)

        # Scrollbars
        sy = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.hsb = ttk.Scrollbar(self.frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.hsb.set)

        # Layout
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(15,0), pady=(6,0))
        sy.grid(row=1, column=1, sticky="ns", pady=(6,0))
        self.hsb.grid(row=2, column=0, sticky="ew", padx=(15,0), pady=(0,12))

        self._current = None

    def _configure_grid(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

    def _init_row_tags(self):
        # Colores: celeste=Pago Pendiente, amarillo=Pago Parcial, verde=Pago Completo
        self.tree.tag_configure("pend", background="#00bcd4", foreground="#000000")
        self.tree.tag_configure("parc", background="#f1c40f", foreground="#000000")
        self.tree.tag_configure("comp", background="#2ecc71", foreground="#000000")

    # ------------------- Helpers -----------------------------
    def _show_ctx(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)

        # Detectar estado pagado y preferencial desde la fila seleccionada
        pagado_si = False
        pref_si = False
        try:
            sel = self.tree.selection()
            if sel:
                vals = self.tree.item(sel[0])["values"]
                # columnas: 0:id,1:fecha,2:fecha_entrega,3:no_factura,4:cliente,5:total,6:preferencial,7:estado,8:pagado,...
                pagado_txt = str(vals[8]).strip().lower() if len(vals) > 8 else "no"
                pagado_si = (pagado_txt in ("sí", "si", "yes", "1"))

                pref_txt = str(vals[6]).strip().lower() if len(vals) > 6 else "no"
                pref_si = (pref_txt in ("sí", "si", "yes", "1"))
        except Exception:
            pagado_si = False
            pref_si = False

        try:
            # Deshabilitar opciones de descuento si está pagado O si es preferencial
            disable_discounts = (pagado_si or pref_si)
            # Índices del menú contextual según _ctx.add_command arriba:
            self._ctx.entryconfigure(2, state="disabled")  # es el separador, se ignora
            self._ctx.entryconfigure(3, state=("disabled" if disable_discounts else "normal"))
            self._ctx.entryconfigure(4, state=("disabled" if disable_discounts else "normal"))
        except Exception:
            pass

        try:
            self._ctx.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx.grab_release()

    def _limpiar(self):
        self.var_buscar.set("")
        self.refrescar()

    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0])["values"]
        if not vals:
            return None
        return str(vals[0])

    def _filtrados_basicos(self):
        """Filtro rápido por pedido # y excluir cancelados (previo a filtros por encabezado)."""
        try:
            rows = leer_pedidos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer pedidos.\n{e}")
            return []
        rows = [r for r in rows if (r.get("estado","").strip().lower() != "cancelado")]
        q = (self.var_buscar.get() or "").strip()
        if q:
            rows = [r for r in rows if q in (r.get("id_pedido",""))]
        return rows

    # =========================
    #  Refrescar (ahora “enriquece” filas y guarda en _raw_rows)
    # =========================
    def refrescar(self, *args, **kwargs):
        # Si aún no está desbloqueado o no existe el Treeview, no hacer nada
        if not getattr(self, "_unlocked", False) or getattr(self, "tree", None) is None:
            return
       
        # Limpia pintado actual
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._current = None

        # Construye filas enriquecidas (display) y guarda en _raw_rows
        enriched = []
        for r in self._filtrados_basicos():
            pid = r.get("id_pedido","")
            fecha = _fmt_dt_show(r.get("fecha",""))
            fecha_entrega = _fmt_dt_show(r.get("fecha_entrega",""))
            cliente = r.get("cliente","")
            total_txt = r.get("total","0")
            try:
                total_pedido = float((total_txt or "0").replace(",",".")) if total_txt else 0.0
            except Exception:
                total_pedido = 0.0

            try:
                objetivo_actual, pct_hoy, dias_entrega = total_cobro_actual(pid)
            except Exception:
                objetivo_actual, pct_hoy, dias_entrega = 0.0, 0.0, "N/A"
            try:
                abonado = total_abonado(pid)
            except Exception:
                abonado = 0.0
            saldo = max(0.0, objetivo_actual - abonado)

            try:
                el = descuento_eligibilidad(pid)
                elegible = "Sí" if el.get("eligible", False) else "No"
            except Exception:
                elegible = "No"

            preferencial = "Sí" if r.get("descuento","0") == "1" else "No"
            estado_surtido = r.get("estado","")
            pagado = "Sí" if r.get("pagado","0") == "1" else "No"

            desc_fijo_pct = r.get("descuento_pago_pct","").strip()
            total_fijo = r.get("total_cobro","").strip()

            no_factura = (r.get("no_factura","") or "").strip() or "N/A"

            enriched.append({
                "id_pedido": pid,
                "fecha": fecha,
                "fecha_entrega": fecha_entrega,
                "no_factura": no_factura,
                "cliente": cliente,
                "total": f"{total_pedido:.2f}",
                "preferencial": preferencial,
                "estado_surtido": estado_surtido,
                "pagado": pagado,
                "elegible10": elegible,
                "dias_entrega": (dias_entrega if isinstance(dias_entrega, int) else "N/A"),
                "total_cobro_actual": f"{objetivo_actual:.2f}",
                "abonado": f"{abonado:.2f}",
                "saldo": f"{saldo:.2f}",
                "desc_fijo_pct": desc_fijo_pct,
                "total_fijo": total_fijo
            })

        self._raw_rows = enriched
        self._pintar_tree_aplicando_filtros_y_orden()

    # =========================
    #  Aplicación de filtros + pintado
    # =========================
    def _aplicar_filtros_header(self, rows):
        if not self._active_filters:
            return rows
        out = []
        for r in rows:
            ok = True
            for col_key, allowed in self._active_filters.items():
                if not allowed:
                    ok = False; break
                val = r.get(col_key, "")
                # Para columnas de fecha, la comparación es por día
                if col_key in self.DATE_COLS:
                    val = _date_key(val)
                if val not in allowed:
                    ok = False; break
            if ok:
                out.append(r)
        return out

    def _pintar_tree_aplicando_filtros_y_orden(self):
        # limpia
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        datos = self._aplicar_filtros_header(self._raw_rows or [])

        # Inserta con tags por estado de pago (como antes)
        for r in datos:
            # estado de pago por 'saldo' y 'abonado'
            try:
                saldo_val = float(str(r.get("saldo","0")).replace(",",".")) if r.get("saldo") else 0.0
                objetivo_val = float(str(r.get("total_cobro_actual","0")).replace(",",".")) if r.get("total_cobro_actual") else 0.0
                abonado_val = float(str(r.get("abonado","0")).replace(",",".")) if r.get("abonado") else 0.0
            except Exception:
                saldo_val, objetivo_val, abonado_val = 0.0, 0.0, 0.0

            tag = "pend"
            if abs(saldo_val) < 0.01 and objetivo_val > 0:
                tag = "comp"
            elif abonado_val > 0:
                tag = "parc"

            self.tree.insert(
                "", "end",
                values=tuple(r.get(c,"") for c in self._cols),
                tags=(tag,)
            )

    # =========================
    #  Popup de filtros (estable)
    # =========================
    def _open_filter_popup_for_column(self, key, event=None):
        # cierra si hay otro abierto
        try:
            if hasattr(self, "_filter_popup") and self._filter_popup and self._filter_popup.winfo_exists():
                self._filter_popup.destroy()
        except Exception:
            pass

        MAX_W, MAX_H, MARGIN = 300, 420, 10
        # coloca bajo el header; si no hay event, usa el centro del widget
        if event:
            base_x = self.tree.winfo_rootx() + event.x
            base_y = self.tree.winfo_rooty() + event.y + 20
        else:
            base_x = self.tree.winfo_rootx() + self.tree.winfo_width()//2
            base_y = self.tree.winfo_rooty() + 40

        top = tk.Toplevel(self.tree)
        top.wm_overrideredirect(True)     # estilo popup
        top.attributes("-topmost", True)
        self._filter_popup = top

        _alive = {"ok": True}
        _after_id = {"id": None}
        _qtrace = {"id": None}

        def _exists(w):
            try: return bool(w and w.winfo_exists())
            except: return False

        frm = ttk.Frame(top, padding=8, style=self.frame_style); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"Filtrar por: {key}", style=self.label_style).pack(anchor="w")

        qvar = tk.StringVar()
        ent = ttk.Entry(frm, textvariable=qvar); ent.pack(fill="x", pady=(4,6)); ent.focus_set()

        # Valores únicos (fechas → por día)
        if key in self.DATE_COLS:
            vals = sorted({ _date_key(r.get(key,"")) for r in (self._raw_rows or []) })
        else:
            vals = sorted({ (str(r.get(key,"")) or "") for r in (self._raw_rows or []) })

        all_values_set = set(vals)
        preset = set(self._active_filters.get(key, set())) or set(vals)

        listfrm = ttk.Frame(frm, style=self.frame_style); listfrm.pack(fill="both", expand=True, pady=(2,6))
        var_all = tk.BooleanVar(value=(preset == set(vals)))
        sel_all_cb = ttk.Checkbutton(listfrm, text="(Seleccionar todo)", variable=var_all, style=self.label_style)
        sel_all_cb.pack(anchor="w")

        canvas = tk.Canvas(listfrm, highlightthickness=0, bg="#1e1e1e")
        sby = ttk.Scrollbar(listfrm, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style=self.frame_style)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sby.set)
        canvas.pack(side="left", fill="both", expand=True)
        sby.pack(side="right", fill="y")

        item_vars = []

        def _safe_close():
            if not _alive["ok"]: return
            _alive["ok"] = False
            try:
                if _after_id["id"] is not None and _exists(top):
                    top.after_cancel(_after_id["id"])
            except Exception:
                pass
            _after_id["id"] = None
            try:
                if _qtrace["id"] is not None:
                    qvar.trace_remove("write", _qtrace["id"])
            except Exception:
                pass
            _qtrace["id"] = None
            try:
                if _exists(top): top.destroy()
            except Exception:
                pass

        def _pintar_estado_sel_all():
            # actualiza el estado de var_all con base en lo visible
            subset_vars = [var for (_v, var) in item_vars]
            if not subset_vars:
                var_all.set(True)
                return
            checked = sum(1 for var in subset_vars if var.get())
            var_all.set(checked == len(subset_vars))

        def _apply_and_close(selected:set, all_values:set):
            """
            - Si selected está vacío o contiene todos los valores → elimina el filtro (columna libre).
            - En otro caso → aplica el conjunto seleccionado.
            """
            if not selected or selected == all_values:
                self._active_filters.pop(key, None)
            else:
                self._active_filters[key] = selected
            self._pintar_tree_aplicando_filtros_y_orden()
            _safe_close()

        def _apply_single(value):
            _apply_and_close({value}, all_values_set)

        def _rebuild_items(filter_text=""):
            if not (_alive["ok"] and _exists(inner)): return

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
                # doble clic / Enter → aplica sólo ese valor
                cb.bind("<Double-Button-1>", lambda e, vv=v: _apply_single(vv))
                cb.bind("<Return>",          lambda e, vv=v: _apply_single(vv))
                item_vars.append((v, var))

            _pintar_estado_sel_all()
            _debounced_fit()

        def _set_all_checks(state: bool):
            for _, var in item_vars:
                var.set(state)

        def on_q_changed(*_):
            if not (_alive["ok"] and _exists(top) and _exists(inner)): return
            _rebuild_items(qvar.get())
        _qtrace["id"] = qvar.trace_add("write", on_q_changed)

        # Toggle seleccionar todo afecta sólo lo visible
        def _on_toggle_all(*_):
            _set_all_checks(bool(var_all.get()))
        var_all.trace_add("write", lambda *_: _on_toggle_all())

        btns = ttk.Frame(frm, style=self.frame_style); btns.pack(fill="x")
        ttk.Button(btns, text="Aplicar", style=self.button_style,
                command=lambda: _apply_and_close({v for v, var in item_vars if var.get()}, all_values_set))\
            .pack(side="right")
        ttk.Button(btns, text="Limpiar", style=self.button_style,
                command=lambda: _apply_and_close(set(), all_values_set))\
            .pack(side="right", padx=(6,0))
        ttk.Button(btns, text="Cerrar",  style=self.button_style,
                command=lambda: _safe_close())\
            .pack(side="left")

        def _apply_from_entry(_e=None):
            val = (qvar.get() or "").strip()
            if not val:
                # vacío → elimina filtro de esta columna
                _apply_and_close(set(), all_values_set)
                return
            if key in self.DATE_COLS:
                val = _date_key(val)
            _apply_and_close({val}, all_values_set)
        ent.bind("<Return>", _apply_from_entry)

        def _fit_height_and_place():
            if not (_alive["ok"] and _exists(top) and _exists(frm)): return
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

            screen_w = top.winfo_screenwidth(); screen_h = top.winfo_screenheight()
            px = max(MARGIN, min(base_x, screen_w - MAX_W - MARGIN))
            py = max(MARGIN, min(base_y, screen_h - pop_h - MARGIN))
            try:
                top.geometry(f"{MAX_W}x{pop_h}+{px}+{py}")
            except Exception:
                pass

        def _debounced_fit():
            if not _exists(top): return
            try:
                if _after_id["id"] is not None:
                    top.after_cancel(_after_id["id"])
            except Exception:
                pass
            _after_id["id"] = top.after(0, _fit_height_and_place)

        top.bind("<Escape>",  lambda e: _safe_close())
        top.bind("<Destroy>", lambda e: _safe_close())

        _rebuild_items("")
        _fit_height_and_place()


    # --- Registrar abono (modal blindado)
    def _menu_registrar_abono(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return

        # Si ya hay una ventana abierta, traerla al frente y parpadear
        if self._dlg_abono and self._dlg_abono.winfo_exists():
            try:
                self._dlg_abono.lift()
                self._dlg_abono.attributes("-topmost", True)
                self._dlg_abono.after(200, lambda: self._dlg_abono.attributes("-topmost", False))
                self._dlg_abono.bell()
            except Exception:
                pass
            return

        # Datos de saldo actuales
        objetivo, _, _ = total_cobro_actual(pid)
        abon = total_abonado(pid)
        saldo = max(0.0, objetivo - abon)

        win = tk.Toplevel(self.frame)
        self._dlg_abono = win
        win.title(f"Registrar abono – {pid}")
        win.transient(self.frame.winfo_toplevel())
        win.resizable(False, False)
        win.grab_set()  # modal

        # Si el usuario cierra la ventana, limpiar referencia
        def _on_close():
            try:
                win.grab_release()
            except Exception:
                pass
            self._dlg_abono = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        frm = ttk.Frame(win, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text=f"Total actual: ${objetivo:.2f}", style=self.label_style).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text=f"Abonado: ${abon:.2f}", style=self.label_style).grid(row=1, column=0, sticky="w", pady=(2,0))
        ttk.Label(frm, text=f"Saldo: ${saldo:.2f}", style=self.label_style).grid(row=2, column=0, sticky="w", pady=(0,6))

        ttk.Label(frm, text="Monto del abono:", style=self.label_style).grid(row=3, column=0, sticky="w")
        self.var_monto_abono = tk.StringVar(value="")
        ent = ttk.Entry(frm, textvariable=self.var_monto_abono, width=18)
        ent.grid(row=4, column=0, sticky="w", pady=(2,6))
        ent.focus_set()

        # Validación: solo números y punto
        def _validate_monto(P):
            s = (P or "").strip()
            if s == "":
                return True
            if s.count(".") > 1:
                return False
            return all(ch.isdigit() or ch == "." for ch in s)
        vcmd = (win.register(_validate_monto), "%P")
        ent.configure(validate="key", validatecommand=vcmd)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, sticky="ew", pady=(8,0))

        def _error_modal(msg: str):
            try: win.grab_release()
            except Exception: pass
            messagebox.showerror("Error", msg, parent=win)
            try: win.grab_set()
            except Exception: pass

        def _guardar():
            raw = self.var_monto_abono.get().strip()
            if raw == "":
                _error_modal("Ingresa un monto.")
                return
            try:
                monto = float(raw)
            except Exception:
                _error_modal("Monto no válido.")
                return
            if monto <= 0:
                _error_modal("El monto debe ser mayor a 0.")
                return

            obj, _, _ = total_cobro_actual(pid)
            ab = total_abonado(pid)
            sal = max(0.0, obj - ab)
            if monto > sal + 1e-9:
                _error_modal(f"El abono excede el saldo actual (${sal:.2f}).")
                return

            try:
                registrar_abono(pid, monto)
            except Exception as e:
                _error_modal(str(e))
                return

            messagebox.showinfo("Listo", f"Abono registrado: ${monto:.2f}", parent=win)
            _on_close()
            self.refrescar()
            self._emit_refresh_all()

        ttk.Button(btns, text="Guardar", command=_guardar, style=self.button_style).pack(side="right")
        ttk.Button(btns, text="Cancelar", command=_on_close, style=self.button_style).pack(side="right", padx=(0,8))

        # Centrar
        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")

    # --- Historial de abonos (solo lectura)
    def _menu_historial_abonos(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return

        pagos = []
        try:
            pagos = leer_abonos(pid)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el historial.\n{e}")
            return

        win = tk.Toplevel(self.frame)
        win.title(f"Historial de abonos – {pid}")
        win.transient(self.frame.winfo_toplevel())
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        cols = ("id_pago","fecha","monto")
        tv = ttk.Treeview(frm, columns=cols, show="headings", height=10, style=self.tree_style)
        tv.heading("id_pago", text="ID Pago"); tv.column("id_pago", width=160, anchor="center")
        tv.heading("fecha", text="Fecha"); tv.column("fecha", width=130, anchor="center")
        tv.heading("monto", text="Monto"); tv.column("monto", width=90, anchor="e")
        for r in pagos:
            tv.insert("", "end", values=(r.get("id_pago",""), r.get("fecha",""), r.get("monto","")))
        tv.grid(row=0, column=0, sticky="nsew")
        ttk.Button(frm, text="Cerrar", command=win.destroy, style=self.button_style).grid(row=1, column=0, pady=(8,0))

        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")

    # --- Descuento forzado
    def _aplicar_desc_forzado(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        if not messagebox.askyesno("Confirmar", f"Aplicar DESCUENTO FORZADO del 10% a {pid}?"):
            return
        try:
            ok = aplicar_descuento_forzado(pid, 10.0)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo aplicar el descuento forzado.\n{e}")
            return
        if ok:
            messagebox.showinfo("Listo", f"Descuento forzado aplicado a {pid}.")
            self.refrescar(); self._emit_refresh_all()
        else:
            messagebox.showinfo("Info", "No se realizaron cambios.")

    def _quitar_desc_forzado(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        if not messagebox.askyesno("Confirmar", f"Quitar el DESCUENTO FORZADO de {pid}?"):
            return
        try:
            ok = quitar_descuento_forzado(pid)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo quitar el descuento forzado.\n{e}")
            return
        if ok:
            messagebox.showinfo("Listo", f"Descuento forzado eliminado en {pid}.")
            self.refrescar(); self._emit_refresh_all()
        else:
            messagebox.showinfo("Info", "No se realizaron cambios.")
    
    # --- Registrar No. de factura
    def _menu_registrar_factura(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        # Pide el No. de factura (permite también limpiar dejándolo vacío)
        nofac = simpledialog.askstring("Registrar factura", "No. de factura (deja vacío para limpiar):",
                                    parent=self.frame)
        if nofac is None:
            return  # cancelado
        try:
            ok = set_no_factura(pid, nofac.strip())
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar la factura.\n{e}")
            return
        if ok:
            messagebox.showinfo("Listo", f"Factura {'registrada' if nofac.strip() else 'eliminada'} para {pid}.")
            self.refrescar()
            self._emit_refresh_all()
        else:
            messagebox.showinfo("Info", "No se realizaron cambios.")
    
    # ------------------- Pantalla bloqueada ------------------------
    def _build_locked_gate(self):
        # Limpia por si acaso
        for w in self.frame.winfo_children():
            w.destroy()
        gate = ttk.Frame(self.frame, style=self.frame_style, padding=20)
        gate.grid(row=0, column=0, sticky="nsew")
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        lbl = ttk.Label(gate, text="Cobranza bloqueada", style=self.label_style)
        lbl.grid(row=0, column=0, pady=(0,10))
        btn = ttk.Button(gate, text="Acceder…", command=self._login_gate, style=self.button_style)
        btn.grid(row=1, column=0)
        btn.focus_set()

    def _login_gate(self):
        win = tk.Toplevel(self.frame)
        win.title("Acceso a Cobranza")
        win.transient(self.frame.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=12); frm.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frm, text="Usuario:", style=self.label_style).grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        v_user = tk.StringVar(value=ADMIN_USER)
        ttk.Entry(frm, textvariable=v_user, width=26).grid(row=0, column=1, sticky="w")

        ttk.Label(frm, text="Contraseña:", style=self.label_style).grid(row=1, column=0, sticky="e", padx=(0,6), pady=4)
        v_pass = tk.StringVar()
        ttk.Entry(frm, textvariable=v_pass, width=26, show="•").grid(row=1, column=1, sticky="w")

        btns = ttk.Frame(frm, style=self.frame_style); btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8,0))
        def _ok():
            if self._admin_check(v_user.get(), v_pass.get()):
                try:
                    win.grab_release()
                except Exception:
                    pass
                win.destroy()
                self._unlock_and_build()
            else:
                messagebox.showerror("Acceso", "Usuario o contraseña incorrectos.", parent=win)

        ttk.Button(btns, text="Entrar", command=_ok, style=self.button_style).pack(side="right")
        ttk.Button(btns, text="Cancelar", command=win.destroy, style=self.button_style).pack(side="right", padx=(0,8))

        win.update_idletasks()
        parent = self.frame.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width()//2 - win.winfo_width()//2)
        y = parent.winfo_rooty() + (parent.winfo_height()//2 - win.winfo_height()//2)
        win.geometry(f"+{x}+{y}")

    def _unlock_and_build(self):
        self._unlocked = True
        # Reemplaza la pantalla bloqueada por la UI real:
        for w in self.frame.winfo_children():
            w.destroy()
        self._build_ui()
        self._configure_grid()
        self._init_row_tags()
        self.refrescar()

    def _reset_header_filters(self):
        """Quita todos los filtros tipo Excel (encabezado) y repinta."""
        self._active_filters.clear()
        # Si también quieres limpiar el campo 'Pedido #', descomenta la siguiente línea:
        # self.var_buscar.set("")
        self._pintar_tree_aplicando_filtros_y_orden()
