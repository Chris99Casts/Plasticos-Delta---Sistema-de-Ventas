import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from data.csv_manager import (
    leer_pedidos,
    marcar_pagado,
    deshacer_pago,
)

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

        self._build_ui()
        self._configure_grid()
        self._init_row_tags()
        self.refrescar()
    # ------------------- Emitir refresh ----------------------
    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()


    def _build_ui(self):
        # Barra superior: filtros/búsqueda/acciones
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

        ttk.Label(box, text="Estado de pago:", style=self.label_style).pack(side="left", padx=(12,6))
        self.cmb_pago = ttk.Combobox(box, values=["Todos","Pagado","No pagado"], state="readonly", width=14)
        self.cmb_pago.set("Todos")
        self.cmb_pago.pack(side="left")
        self.cmb_pago.bind("<<ComboboxSelected>>", lambda e: self.refrescar())

        ttk.Button(box, text="Buscar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=(8,0))
        ttk.Button(box, text="Limpiar", command=self._limpiar, style=self.button_style)\
            .pack(side="left", padx=(6,0))

        act = ttk.Frame(top, style=self.frame_style)
        act.grid(row=0, column=1, sticky="e")

        ttk.Label(act, text="Descuento cobranza (%):", style=self.label_style)\
            .pack(side="left", padx=(0,6))
        self.var_desc = tk.StringVar(value="0")
        self.ent_desc = ttk.Entry(act, textvariable=self.var_desc, width=5)
        self.ent_desc.pack(side="left")

        ttk.Button(act, text="Marcar como pagado", command=self._marcar_pagado, style=self.button_style)\
            .pack(side="left", padx=(8,0))
        ttk.Button(act, text="Refrescar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=(8,0))

        # Tabla
        cols = ("id_pedido","fecha","cliente","total","desc_precio","estado","pagado","desc_cobranza","total_cobro")
        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=18, style=self.tree_style)
        headers = {
            "id_pedido":"ID",
            "fecha":"Fecha",
            "cliente":"Cliente",
            "total":"Total",
            "desc_precio":"Desc.(precio)",
            "estado":"Estado",
            "pagado":"Pagado",
            "desc_cobranza":"Desc.cobranza(%)",
            "total_cobro":"Total a cobrar"
        }
        for c in cols:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, anchor="center")
        self.tree.bind("<<TreeviewSelect>>", lambda e: None)

        # Menú contextual para deshacer pago
        self._ctx = tk.Menu(self.frame, tearoff=0)
        self._ctx.add_command(label="Deshacer pago…", command=self._deshacer_pago)
        self.tree.bind("<Button-3>", self._show_ctx)
        self.tree.bind("<Control-Button-1>", self._show_ctx)

        sy = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)

        self.tree.grid(row=1, column=0, sticky="nsew", padx=(15,0), pady=(6,12))
        sy.grid(row=1, column=1, sticky="ns", pady=(6,12))

        # Estado interno
        self._current = None

    def _configure_grid(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

    def _init_row_tags(self):
        # Reusa colores de estado de surtido (no pago), y resalta pagado
        self.tree.tag_configure("pend", background="#00bcd4", foreground="#000000")
        self.tree.tag_configure("parc", background="#f1c40f", foreground="#000000")
        self.tree.tag_configure("comp", background="#2ecc71", foreground="#000000")
        self.tree.tag_configure("paid", background="#9be7a6", foreground="#000000")  # verde suave pagado

    def _show_ctx(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        try:
            self._ctx.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx.grab_release()

    def _limpiar(self):
        self.var_buscar.set("")
        self.cmb_pago.set("Todos")
        self.var_desc.set("0")
        self.refrescar()

    def _filtrados(self):
        try:
            rows = leer_pedidos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer pedidos.\n{e}")
            return []

        # Filtro por pago
        fp = (self.cmb_pago.get() or "Todos").strip().lower()
        if fp == "pagado":
            rows = [r for r in rows if (r.get("pagado","0") == "1")]
        elif fp == "no pagado":
            rows = [r for r in rows if (r.get("pagado","0") != "1")]

        # Filtro por id
        q = (self.var_buscar.get() or "").strip()
        if q:
            rows = [r for r in rows if q in (r.get("id_pedido",""))]

        return rows

    def refrescar(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._current = None

        for r in self._filtrados():
            estado = (r.get("estado","") or "").strip().lower()
            tag = "pend"
            if estado == "parcial":
                tag = "parc"
            elif estado == "completado":
                tag = "comp"

            # Si está pagado, sobreescribe tag para resaltar pago
            if r.get("pagado","0") == "1":
                tag = "paid"

            self.tree.insert(
                "", "end",
                values=(
                    r.get("id_pedido",""),
                    r.get("fecha",""),
                    r.get("cliente",""),
                    r.get("total",""),
                    "Sí" if r.get("descuento","0") == "1" else "No",
                    r.get("estado",""),
                    "Sí" if r.get("pagado","0") == "1" else "No",
                    r.get("descuento_pago_pct",""),
                    r.get("total_cobro",""),
                ),
                tags=(tag,)
            )

    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0])["values"]
        if not vals:
            return None
        return str(vals[0])

    def _parse_pct(self, txt: str) -> float:
        s = (txt or "").strip().replace("%","").replace(",", ".")
        if not s:
            return 0.0
        try:
            v = float(s)
        except Exception:
            return 0.0
        # clamp 0..100
        return max(0.0, min(100.0, v))

    def _marcar_pagado(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        pct = self._parse_pct(self.var_desc.get())
        try:
            ok, total_cobro = marcar_pagado(pid, pct)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo marcar pagado.\n{e}")
            return
        if ok:
            messagebox.showinfo("Listo", f"Pedido {pid} marcado como pagado.\n"
                                         f"Descuento: {pct:.2f}%\n"
                                         f"Total a cobrar: ${total_cobro:.2f}")
            self.refrescar()
        else:
            messagebox.showwarning("Atención", "No se realizaron cambios.")
        self._emit_refresh_all()


    def _deshacer_pago(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        if not messagebox.askyesno("Confirmar", f"¿Deshacer pago del pedido {pid}?"):
            return
        try:
            ok = deshacer_pago(pid)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo deshacer el pago.\n{e}")
            return
        if ok:
            messagebox.showinfo("Listo", f"Pago deshecho para {pid}.")
            self.refrescar()
        else:
            messagebox.showinfo("Info", "No se realizaron cambios.")
        self._emit_refresh_all()

