import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
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
)

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

        self.frame = ttk.Frame(notebook, style=self.frame_style)
        self._dlg_abono = None   # ventana de abonos (evitar múltiples)

        self._build_ui()
        self._configure_grid()
        self._init_row_tags()
        self.refrescar()

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

        ttk.Button(box, text="Buscar", command=self.refrescar, style=self.button_style).pack(side="left", padx=(8,0))
        ttk.Button(box, text="Limpiar", command=self._limpiar, style=self.button_style).pack(side="left", padx=(6,0))

        cols = (
            "id_pedido","fecha","fecha_entrega","cliente","total",
            "preferencial","estado_surtido","pagado",
            "elegible10","dias_entrega",
            "total_cobro_actual","abonado","saldo",
            "desc_fijo_pct","total_fijo"
        )
        headers = {
            "id_pedido":"ID",
            "fecha":"Fecha pedido",
            "fecha_entrega":"Fecha entrega",
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
        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=18, style=self.tree_style)

        for c in cols:
            self.tree.heading(c, text=headers[c])
            width_map = {
                "id_pedido":110, "fecha":120, "fecha_entrega":140, "cliente":220, "total":100,
                "preferencial":95, "estado_surtido":110, "pagado":70, "elegible10":95,
                "dias_entrega":120, "total_cobro_actual":160, "abonado":110, "saldo":110,
                "desc_fijo_pct":105, "total_fijo":110
            }
            self.tree.column(c, anchor="center", width=width_map.get(c, 100), stretch=False)

        # Menú contextual
        self._ctx = tk.Menu(self.frame, tearoff=0)
        # índices: 0:fecha, 1:sep, 2:abono, 3:historial, 4:sep, 5:aplicar desc, 6:quitar desc
        self._ctx.add_command(label="Registrar abono…", command=self._menu_registrar_abono)
        self._ctx.add_command(label="Ver historial de abonos…", command=self._menu_historial_abonos)
        self._ctx.add_separator()
        self._ctx.add_command(label="Aplicar descuento forzado 10%…", command=self._aplicar_desc_forzado)
        self._ctx.add_command(label="Quitar descuento forzado…", command=self._quitar_desc_forzado)

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
                # columnas: 0:id,1:fecha,2:fecha_entrega,3:cliente,4:total,5:preferencial,6:estado,7:pagado,...
                pagado_txt = str(vals[7]).strip().lower() if len(vals) > 7 else "no"
                pagado_si = (pagado_txt in ("sí", "si", "yes", "1"))

                pref_txt = str(vals[5]).strip().lower() if len(vals) > 5 else "no"
                pref_si = (pref_txt in ("sí", "si", "yes", "1"))
        except Exception:
            pagado_si = False
            pref_si = False

        # Índices en el menú contextual:
        # 0: fecha, 1: sep, 2: registrar abono, 3: historial, 4: sep, 5: aplicar desc, 6: quitar desc
        try:
            # Deshabilitar opciones de descuento si está pagado O si es preferencial
            disable_discounts = (pagado_si or pref_si)
            self._ctx.entryconfigure(5, state=("disabled" if disable_discounts else "normal"))
            self._ctx.entryconfigure(6, state=("disabled" if disable_discounts else "normal"))
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

    def _filtrados(self):
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

    def refrescar(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._current = None

        for r in self._filtrados():
            pid = r.get("id_pedido","")
            fecha = r.get("fecha","")
            fecha_entrega = r.get("fecha_entrega","")
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

            # Etiqueta por estado de pago
            tag = "pend"
            if abs(saldo) < 0.01 and objetivo_actual > 0:
                tag = "comp"
            elif abonado > 0:
                tag = "parc"

            self.tree.insert(
                "", "end",
                values=(
                    pid, fecha, fecha_entrega, cliente, f"{total_pedido:.2f}",
                    preferencial, estado_surtido, pagado,
                    elegible, (dias_entrega if isinstance(dias_entrega, int) else "N/A"),
                    f"{objetivo_actual:.2f}", f"{abonado:.2f}", f"{saldo:.2f}",
                    desc_fijo_pct, total_fijo
                ),
                tags=(tag,)
            )

    

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
