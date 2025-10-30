import tkinter as tk
from tkinter import ttk, messagebox
from data.csv_manager import (
    leer_pedidos,
    registrar_abono,
    total_abonado,
    estado_pago,
    leer_abonos,
    total_cobro_actual,
    eliminar_abono,
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

        self._abono_win = None          # evita ventanas duplicadas
        self._abono_in_msg = False      # evita shake mientras hay pop-up (messagebox)

        self._build_ui()
        self._configure_grid()
        self._init_row_tags()
        self.refrescar()

    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()

    def _build_ui(self):
        top = ttk.Frame(self.frame, style=self.frame_style)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8,6))
        top.grid_columnconfigure(99, weight=1)

        box = ttk.Frame(top, style=self.frame_style)
        box.grid(row=0, column=0, sticky="w")

        ttk.Label(box, text="Pedido #:", style=self.label_style).pack(side="left", padx=(0,6))
        self.var_buscar = tk.StringVar()
        ent = ttk.Entry(box, textvariable=self.var_buscar, width=18)
        ent.pack(side="left"); ent.bind("<Return>", lambda e: self.refrescar())

        ttk.Label(box, text="Estado de pago:", style=self.label_style).pack(side="left", padx=(12,6))
        self.cmb_pago = ttk.Combobox(box, values=["Todos","Pago Pendiente","Pago Parcial","Pago Completo"],
                                     state="readonly", width=18)
        self.cmb_pago.set("Todos"); self.cmb_pago.pack(side="left")
        self.cmb_pago.bind("<<ComboboxSelected>>", lambda e: self.refrescar())

        ttk.Button(box, text="Buscar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=(8,0))
        ttk.Button(box, text="Limpiar", command=self._limpiar, style=self.button_style)\
            .pack(side="left", padx=(6,0))

        act = ttk.Frame(top, style=self.frame_style)
        act.grid(row=0, column=1, sticky="e")

        ttk.Button(act, text="Registrar abono…", command=self._registrar_abono, style=self.button_style)\
            .pack(side="left", padx=(8,0))
        ttk.Button(act, text="Ver pagos…", command=self._ver_pagos, style=self.button_style)\
            .pack(side="left", padx=(8,0))
        ttk.Button(act, text="Refrescar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=(8,0))

        cols = ("id_pedido","fecha","cliente","total","total_cobro_actual","abonado","saldo_actual","estado_pago")
        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=18, style=self.tree_style)
        headers = {
            "id_pedido":"ID","fecha":"Fecha","cliente":"Cliente","total":"Total",
            "total_cobro_actual":"Total a cobrar (actual)","abonado":"Abonado","saldo_actual":"Saldo (actual)",
            "estado_pago":"Estado de pago"
        }
        for c in cols:
            self.tree.heading(c, text=headers[c]); self.tree.column(c, anchor="center")

        self._ctx = tk.Menu(self.frame, tearoff=0)
        self._ctx.add_command(label="Registrar abono…", command=self._registrar_abono)
        self._ctx.add_command(label="Ver pagos…", command=self._ver_pagos)
        self.tree.bind("<Button-3>", self._show_ctx)
        self.tree.bind("<Control-Button-1>", self._show_ctx)

        sy = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.hsb = ttk.Scrollbar(self.frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.hsb.set)

        self.tree.grid(row=1, column=0, sticky="nsew", padx=(15,0), pady=(6,0))
        sy.grid(row=1, column=1, sticky="ns", pady=(6,0))
        self.hsb.grid(row=2, column=0, sticky="ew", padx=(15,0), pady=(0,12))

        self._current = None

    def _configure_grid(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

    def _init_row_tags(self):
        self.tree.tag_configure("pay_pend", background="#00bcd4", foreground="#000000")
        self.tree.tag_configure("pay_parc", background="#f1c40f", foreground="#000000")
        self.tree.tag_configure("pay_comp", background="#2ecc71", foreground="#000000")

    def _show_ctx(self, event):
        iid = self.tree.identify_row(event.y)
        if iid: self.tree.selection_set(iid); self.tree.focus(iid)
        try: self._ctx.tk_popup(event.x_root, event.y_root)
        finally: self._ctx.grab_release()

    def _limpiar(self):
        self.var_buscar.set(""); self.cmb_pago.set("Todos"); self.refrescar()

    def _filtrados(self):
        try: rows = leer_pedidos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer pedidos.\n{e}"); return []
        rows = [r for r in rows if (r.get("estado","").strip().lower()!="cancelado")]
        q = (self.var_buscar.get() or "").strip()
        if q: rows = [r for r in rows if q in (r.get("id_pedido",""))]
        fp = (self.cmb_pago.get() or "Todos").strip().lower()
        if fp!="todos":
            out=[]
            for r in rows:
                est,_,_ = estado_pago(r.get("id_pedido",""))
                if (fp=="pago pendiente" and est=="Pago Pendiente") or \
                   (fp=="pago parcial" and est=="Pago Parcial") or \
                   (fp=="pago completo" and est=="Pago Completo"):
                    out.append(r)
            rows=out
        return rows

    def refrescar(self):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        self._current=None
        for r in self._filtrados():
            objetivo_actual,_,_ = total_cobro_actual(r.get("id_pedido",""))
            try: total = float((r.get("total") or "0").replace(",","").strip())
            except: total = 0.0
            abon = total_abonado(r.get("id_pedido",""))
            saldo = max(0.0, (objetivo_actual or total) - abon)
            estp,_,_ = estado_pago(r.get("id_pedido",""))
            tag = "pay_pend" if estp=="Pago Pendiente" else ("pay_parc" if estp=="Pago Parcial" else "pay_comp")
            self.tree.insert("", "end",
                values=(r.get("id_pedido",""), r.get("fecha",""), r.get("cliente",""),
                        f"{total:.2f}", f"{(objetivo_actual or total):.2f}", f"{abon:.2f}", f"{saldo:.2f}", estp),
                tags=(tag,))

    def _get_selected_id(self):
        sel=self.tree.selection()
        if not sel: return None
        vals=self.tree.item(sel[0])["values"]
        return str(vals[0]) if vals else None

    # ------------------- Utilidades de UI ----------------------
    def _shake_window(self, win, cycles=8, amplitude=10):
        try:
            geo = win.geometry()
            parts = geo.split("+")
            if len(parts) < 3:
                return
            base_x = int(parts[-2]); base_y = int(parts[-1])
        except Exception:
            return

        offsets = [amplitude, -amplitude] * (cycles // 2) + [0]
        def _step(i=0):
            if i >= len(offsets):
                try:
                    win.geometry(f"+{base_x}+{base_y}")
                except:
                    pass
                return
            dx = offsets[i]
            try:
                win.geometry(f"+{base_x + dx}+{base_y}")
            except:
                return
            win.after(18, _step, i+1)
        _step()

    def _flash_focus(self, win: tk.Toplevel):
        try: win.bell()
        except: pass
        try:
            win.attributes("-topmost", True)
            win.focus_force()
        except: pass
        self._shake_window(win)

    # ------------------- Acciones ----------------------
    def _registrar_abono(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido."); return

        if self._abono_win and self._abono_win.winfo_exists():
            self._flash_focus(self._abono_win)
            return

        win = tk.Toplevel(self.frame); self._abono_win = win
        win.title(f"Registrar abono · {pid}")

        # --- Siempre visible y modal ---
        try:
            master = self.frame.winfo_toplevel()
            win.transient(master)
        except:
            pass
        try:
            win.attributes("-topmost", True)
        except:
            pass
        try:
            win.grab_set()
        except:
            pass

        def _on_close():
            try: win.grab_release()
            except: pass
            try: win.destroy()
            finally: self._abono_win = None

        win.protocol("WM_DELETE_WINDOW", _on_close)

        def _on_focus_out(_evt=None):
            if self._abono_in_msg:
                return  # no parpadear mientras un messagebox está abierto
            if win.winfo_exists():
                self._flash_focus(win)
        win.bind("<FocusOut>", _on_focus_out)

        ttk.Label(win, text="Monto:", style=self.label_style).grid(row=0, column=0, padx=10, pady=(12,6), sticky="e")

        vcmd = (win.register(self._validate_amount), "%P")
        var_m = tk.StringVar()
        ent = ttk.Entry(win, textvariable=var_m, width=14, validate="key", validatecommand=vcmd)
        ent.grid(row=0, column=1, padx=10, pady=(12,6), sticky="w"); ent.focus()

        obj_act, _, _ = total_cobro_actual(pid); abon = total_abonado(pid)
        saldo = max(0.0, obj_act - abon)
        lbl_saldo = ttk.Label(win, text=f"Saldo actual: ${saldo:,.2f}", style=self.label_style)
        lbl_saldo.grid(row=1, column=0, columnspan=2, padx=10, pady=(0,6), sticky="w")

        # Helpers de mensajes MODALES, seguros con grab + parent
        def _err(msg: str, title="Error"):
            self._abono_in_msg = True
            try:
                messagebox.showerror(title, msg, parent=win)
            finally:
                self._abono_in_msg = False

        def _info(msg: str, title="Listo"):
            self._abono_in_msg = True
            try:
                messagebox.showinfo(title, msg, parent=win)
            finally:
                self._abono_in_msg = False

        def _ok():
            txt = (var_m.get() or "").strip()
            try: monto = float(txt.replace("$","").replace(",",""))
            except: monto = -1
            if monto <= 0:
                _err("Ingresa un monto válido (> 0)."); return

            obj_act2, _, _ = total_cobro_actual(pid)
            abon2 = total_abonado(pid)
            saldo2 = max(0.0, obj_act2 - abon2)
            if saldo2 <= 0:
                _err("Este pedido ya no tiene saldo por cubrir."); return
            if monto > saldo2 + 1e-9:
                _err(f"El monto excede el saldo actual (${saldo2:.2f})."); return

            try:
                registrar_abono(pid, monto)
            except Exception as e:
                _err(f"No se pudo registrar el abono.\n{e}")
                return

            estp, abon_tot, obj = estado_pago(pid)
            _info(f"Abono registrado.\nEstado: {estp}\nAbonado: ${abon_tot:,.2f} de ${obj:,.2f}")

            _on_close()
            self.refrescar(); self._emit_refresh_all()

        ttk.Button(win, text="Guardar", command=_ok, style=self.button_style)\
            .grid(row=2, column=0, padx=10, pady=(8,12))
        ttk.Button(win, text="Cancelar", command=_on_close, style=self.button_style)\
            .grid(row=2, column=1, padx=10, pady=(8,12))

        win.update_idletasks()
        try:
            master = self.frame.winfo_toplevel()
            mx = master.winfo_rootx(); my = master.winfo_rooty()
            mw = master.winfo_width(); mh = master.winfo_height()
            ww = win.winfo_width(); wh = win.winfo_height()
            x = mx + (mw - ww)//2; y = my + (mh - wh)//3
            win.geometry(f"+{max(0,x)}+{max(0,y)}")
        except:
            pass

    def _validate_amount(self, proposed: str) -> bool:
        s = proposed.strip()
        if s == "": return True
        if s.count(".") > 1: return False
        if s.startswith("."): s = "0" + s
        for ch in s:
            if not (ch.isdigit() or ch == "."):
                return False
        return True

    def _ver_pagos(self):
        pid = self._get_selected_id()
        if not pid:
            messagebox.showwarning("Atención", "Selecciona un pedido."); return

        win = tk.Toplevel(self.frame); win.title(f"Pagos del pedido {pid}")
        frm = ttk.Frame(win, style=self.frame_style); frm.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("id_pago","fecha","monto")
        tree = ttk.Treeview(frm, columns=cols, show="headings", height=12, style=self.tree_style, selectmode="browse")
        for c,t in {"id_pago":"ID pago","fecha":"Fecha","monto":"Monto"}.items():
            tree.heading(c, text=t); tree.column(c, anchor="center")
        sy = ttk.Scrollbar(frm, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=sy.set)
        tree.grid(row=0, column=0, sticky="nsew"); sy.grid(row=0, column=1, sticky="ns")
        frm.grid_rowconfigure(0, weight=1); frm.grid_columnconfigure(0, weight=1)

        info = ttk.Label(frm, text="", style=self.label_style); info.grid(row=1, column=0, sticky="e", pady=(8,0))

        btns = ttk.Frame(frm, style=self.frame_style); btns.grid(row=2, column=0, sticky="e", pady=(10,0))
        del_btn = ttk.Button(btns, text="Eliminar abono seleccionado…", style=self.button_style)
        del_btn.grid(row=0, column=0, padx=(0,8))
        ttk.Button(btns, text="Cerrar", command=win.destroy, style=self.button_style).grid(row=0, column=1)

        def _reload():
            for iid in tree.get_children(): tree.delete(iid)
            try: pagos = leer_abonos(pid)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudieron leer los pagos.\n{e}", parent=win); return
            total_ab = 0.0
            for p in pagos:
                try: m=float((p.get("monto") or "0").replace(",", ""))
                except: m=0.0
                total_ab += m
                tree.insert("", "end", values=(p.get("id_pago",""), p.get("fecha",""), f"{m:.2f}"))
            obj_act, pct, dias = total_cobro_actual(pid)
            info.configure(text=f"Total abonado: ${total_ab:,.2f}   |   Total a cobrar (actual): ${obj_act:,.2f}   "
                                f"|   Saldo (actual): ${max(0.0, obj_act - total_ab):,.2f}"
                                + (f"   |   Pronto-pago hoy: {pct:.0f}% (día {dias})" if pct>0 else ""))

        def _eliminar_sel():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Atención", "Selecciona un abono en la lista.", parent=win); return
            vals = tree.item(sel[0])["values"]
            if not vals: return
            id_pago = str(vals[0])
            if not messagebox.askyesno("Confirmar", f"¿Eliminar el abono {id_pago}?", parent=win): return
            try:
                ok, _ = eliminar_abono(id_pago)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar el abono.\n{e}", parent=win); return
            if ok:
                messagebox.showinfo("Listo", f"Se eliminó el abono {id_pago}.", parent=win)
                _reload(); self.refrescar(); self._emit_refresh_all()
            else:
                messagebox.showinfo("Info", "No fue posible eliminar el abono seleccionado.", parent=win)

        del_btn.configure(command=_eliminar_sel)
        _reload()
