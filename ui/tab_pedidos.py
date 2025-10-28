import tkinter as tk
import os
from tkinter import ttk, messagebox
from datetime import datetime
from ui.pdf_utils import generar_pdf_pedido, abrir_pdf
from data.csv_manager import (
    leer_pedidos,
    leer_items_por_pedido,
    actualizar_cantidades_completadas_batch,
    actualizar_pedido_completo,
    cargar_productos,
    eliminar_pedido,
)

class TabPedidos:
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
        self._init_row_tags()       # <--- Colores por estado
        self.refrescar()
    
    # ------------------- Emitir refresh ----------------------
    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()

    # ---------------- UI ----------------
    def _build_ui(self):
        # ---- Barra superior: filtro + búsqueda + acciones ----
        top_bar = ttk.Frame(self.frame, style=self.frame_style)
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
        top_bar.grid_columnconfigure(99, weight=1)  # separador elástico

        filtro_box = ttk.Frame(top_bar, style=self.frame_style)
        filtro_box.grid(row=0, column=0, sticky="w")

        ttk.Label(filtro_box, text="Estado:", style=self.label_style).pack(side="left", padx=(0,6))
        self.cmb_estado = ttk.Combobox(
            filtro_box, values=["Todos","Pendiente","Parcial","Completado"],
            state="readonly", width=15
        )
        self.cmb_estado.set("Todos")
        self.cmb_estado.pack(side="left")
        self.cmb_estado.bind("<<ComboboxSelected>>", lambda e: self.refrescar())

        # ---- Búsqueda por # de pedido ----
        ttk.Label(filtro_box, text="Pedido #:", style=self.label_style).pack(side="left", padx=(12,6))
        self.var_buscar = tk.StringVar()
        ent_buscar = ttk.Entry(filtro_box, textvariable=self.var_buscar, width=18)
        ent_buscar.pack(side="left")
        ent_buscar.bind("<Return>", lambda e: self.refrescar())

        ttk.Button(filtro_box, text="Buscar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=(6,0))
        ttk.Button(filtro_box, text="Limpiar", command=self._limpiar_busqueda, style=self.button_style)\
            .pack(side="left", padx=(6,0))

        # ---- Botones de acciones ----
        btn_bar = ttk.Frame(top_bar, style=self.frame_style)
        btn_bar.grid(row=0, column=1, sticky="e")
        ttk.Button(btn_bar, text="Refrescar", command=self.refrescar, style=self.button_style)\
            .pack(side="left", padx=8)
        ttk.Button(btn_bar, text="Editar líneas…", command=self._abrir_editor_masivo, style=self.button_style)\
            .pack(side="left", padx=8)
        ttk.Button(btn_bar, text="Editar pedido…", command=self._abrir_editor_pedido, style=self.button_style)\
            .pack(side="left", padx=8)

        # Botón Generar Nota PDF (usar grid, no pack)
        self.btn_pdf = ttk.Button(
            top_bar,
            text="Generar Nota PDF",
            style=self.button_style,
            command=self._generar_pdf_pedido_sel
        )
        self.btn_pdf.grid(row=0, column=10, padx=(6, 0), sticky="w")

        # ---- Tabla de pedidos ----
        cols_p = ("id_pedido", "fecha", "cliente", "total", "estado", "descuento")
        self.tree_pedidos = ttk.Treeview(self.frame, columns=cols_p, show="headings",
                                         height=11, style=self.tree_style)
        headers = {
            "id_pedido":"ID", "fecha":"Fecha", "cliente":"Cliente",
            "total":"Total", "estado":"Estado", "descuento":"Desc."
        }
        for col in cols_p:
            self.tree_pedidos.heading(col, text=headers[col])
            self.tree_pedidos.column(col, anchor="center")
        self.tree_pedidos.bind("<<TreeviewSelect>>", self._on_select_pedido)

        y1 = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree_pedidos.yview)
        self.tree_pedidos.configure(yscrollcommand=y1.set)

        self.tree_pedidos.grid(row=1, column=0, sticky="nsew", padx=(15,0), pady=(10,5))

        # ---- Menú contextual (click derecho) para eliminar pedido ----
        self._ctx_menu = tk.Menu(self.frame, tearoff=0)
        self._ctx_menu.add_command(label="Eliminar pedido…", command=self._ctx_eliminar_pedido)
        self.tree_pedidos.bind("<Button-3>", self._show_ctx_menu)         # Windows/Linux
        self.tree_pedidos.bind("<Control-Button-1>", self._show_ctx_menu) # macOS (fallback)

        y1.grid(row=1, column=1, sticky="ns", pady=(10,5))

        # ---- Tabla de detalle ----
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
        self.tree_detalle.configure(yscrollcommand=y2.set)

        self.tree_detalle.grid(row=2, column=0, sticky="nsew", padx=(15,0), pady=(5,15))
        y2.grid(row=2, column=1, sticky="ns", pady=(5,15))

        # Estado actual
        self._current_pedido = None
        self._current_descuento = "0"  # "1" si fue con descuento

    def _configure_grid(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)
        self.frame.grid_rowconfigure(2, weight=2)

    # ---- Colores por estado (tags de Treeview) ----
    def _init_row_tags(self):
        # Verde (Completado), Amarillo (Parcial), Celeste (Pendiente)
        self.tree_pedidos.tag_configure("row_completado", background="#2ecc71", foreground="#000000")
        self.tree_pedidos.tag_configure("row_parcial",    background="#f1c40f", foreground="#000000")
        self.tree_pedidos.tag_configure("row_pendiente",  background="#00bcd4", foreground="#000000")

        self.tree_detalle.tag_configure("d_completado", background="#2ecc71", foreground="#000000")
        self.tree_detalle.tag_configure("d_parcial",    background="#f1c40f", foreground="#000000")
        self.tree_detalle.tag_configure("d_pendiente",  background="#00bcd4", foreground="#000000")

    def _detail_tag_for(self, cantidad: int, completado: int) -> str:
        try:
            c = int(cantidad); comp = int(completado)
        except Exception:
            return "d_pendiente"
        if comp <= 0:
            return "d_pendiente"            # todo pendiente
        if comp >= c:
            return "d_completado"           # completo
        return "d_parcial"                  # parcial

    # ---------------- Lógica ----------------
    def _obtener_pedidos_filtrados(self):
        try:
            pedidos = leer_pedidos()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer los pedidos.\n{e}")
            return []

        # Filtro por estado
        estado = (self.cmb_estado.get() or "Todos").strip().lower()
        if estado != "todos":
            pedidos = [p for p in pedidos if (p.get("estado","").strip().lower() == estado)]

        # Filtro por texto (id de pedido)
        q = (self.var_buscar.get() or "").strip()
        if q:
            pedidos = [p for p in pedidos if q in (p.get("id_pedido",""))]

        return pedidos

    def _limpiar_busqueda(self):
        self.var_buscar.set("")
        self.refrescar()

    def refrescar(self):
        # limpia tablas
        for t in (self.tree_pedidos, self.tree_detalle):
            for item in t.get_children():
                t.delete(item)
        self._current_pedido = None
        self._current_descuento = "0"

        # inserta pedidos con tag por estado
        for p in self._obtener_pedidos_filtrados():
            estado = (p.get("estado","") or "").strip().lower()
            tag = "row_pendiente"
            if estado == "completado":
                tag = "row_completado"
            elif estado == "parcial":
                tag = "row_parcial"

            self.tree_pedidos.insert(
                "", "end",
                values=(p.get("id_pedido",""), p.get("fecha",""),
                        p.get("cliente",""), p.get("total",""),
                        p.get("estado",""), p.get("descuento","0")),
                tags=(tag,)
            )

    def _on_select_pedido(self, event=None):
        # limpia detalle
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
        self._current_descuento = str(vals[5]) if len(vals) > 5 else "0"

        try:
            items = leer_items_por_pedido(id_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el detalle.\n{e}")
            return

        for it in items:
            cant = int(it.get("cantidad") or 0)
            comp = int(it.get("cantidad_completada") or 0)
            pend = max(0, cant - comp)
            tag = self._detail_tag_for(cant, comp)
            self.tree_detalle.insert(
                "", "end",
                values=(it.get("id_linea",""), it.get("producto",""),
                        str(cant), str(comp), str(pend),
                        it.get("precio_unitario",""), it.get("importe","")),
                tags=(tag,)
            )

    # -------- Editor masivo (completados) --------
    def _abrir_editor_masivo(self):
        if not self._current_pedido:
            messagebox.showwarning("Atención", "Selecciona un pedido para editar líneas.")
            return
        try:
            items = leer_items_por_pedido(self._current_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el detalle.\n{e}")
            return
        if not items:
            messagebox.showinfo("Info", "Este pedido no tiene líneas.")
            return

        def _after():
            self._on_editor_guardado()
            self._emit_refresh_all()   # <-- NUEVO

        EditorMasivo(self.frame, self._current_pedido, items,
                    on_saved=_after,
                    frame_style=self.frame_style,
                    button_style=self.button_style,
                    label_style=self.label_style)

    def _on_editor_guardado(self):
        # Guarda el pedido seleccionado antes del refresh
        last = self._current_pedido
        # Muestra todo para que no desaparezca si cambió de estado
        self.cmb_estado.set("Todos")
        self.refrescar()
        # Reseleccionar el pedido editado
        if last:
            for iid in self.tree_pedidos.get_children():
                vals = self.tree_pedidos.item(iid)["values"]
                if vals and str(vals[0]) == str(last):
                    self.tree_pedidos.selection_set(iid)
                    self.tree_pedidos.see(iid)
                    self._on_select_pedido()
                    break

    # -------- Editor completo del pedido (con sugerencias y precio según descuento) --------
    def _abrir_editor_pedido(self):
        if not self._current_pedido:
            messagebox.showwarning("Atención", "Selecciona un pedido para editar.")
            return
        try:
            items = leer_items_por_pedido(self._current_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el detalle.\n{e}")
            return
        if not items:
            messagebox.showinfo("Info", "Este pedido no tiene líneas.")
            return

        sel = self.tree_pedidos.selection()
        vals = self.tree_pedidos.item(sel[0])["values"]
        fecha = vals[1]; cliente = vals[2]
        use_desc = (self._current_descuento == "1")

        def _after():
            self._on_editor_guardado()
            self._emit_refresh_all()

        EditorPedido(self.frame, self._current_pedido, cliente, fecha, items, use_desc,
                    on_saved=_after,
                    frame_style=self.frame_style,
                    button_style=self.button_style,
                    label_style=self.label_style)

    def _show_ctx_menu(self, event):
        # Selecciona la fila bajo el cursor antes de mostrar el menú
        iid = self.tree_pedidos.identify_row(event.y)
        if iid:
            self.tree_pedidos.selection_set(iid)
            self.tree_pedidos.focus(iid)
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _ctx_eliminar_pedido(self):
        sel = self.tree_pedidos.selection()
        if not sel:
            messagebox.showwarning("Atención", "Selecciona un pedido para eliminar.")
            return
        vals = self.tree_pedidos.item(sel[0])["values"]
        id_pedido = str(vals[0]) if vals else None
        cliente = str(vals[2]) if len(vals) > 2 else ""
        if not id_pedido:
            messagebox.showwarning("Atención", "No se pudo determinar el ID del pedido.")
            return

        # Confirmación
        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar el pedido {id_pedido} de '{cliente}'?\n"
            f"Esta acción no se puede deshacer."
        ):
            return

        try:
            ok = eliminar_pedido(id_pedido)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo eliminar el pedido.\n{e}")
            return

        if ok:
            messagebox.showinfo("Eliminado", f"Pedido {id_pedido} eliminado.")
        else:
            messagebox.showinfo("Info", "No se realizaron cambios (ya no existía).")

        # Refresca y limpia el detalle
        self.refrescar()
        for item in self.tree_detalle.get_children():
            self.tree_detalle.delete(item)
        self._current_pedido = None
        self._emit_refresh_all()  # <-- NUEVO


    def _generar_pdf_pedido_sel(self):
        iid = self.tree_pedidos.selection()
        if not iid:
            messagebox.showwarning("Atención", "Selecciona un pedido.")
            return
        vals = self.tree_pedidos.item(iid[0])["values"]
        if not vals:
            return
        id_pedido = str(vals[0])
        cliente   = str(vals[2]) if len(vals) > 2 else ""
        fecha     = str(vals[1]) if len(vals) > 1 else datetime.now().strftime("%Y-%m-%d %H:%M")

        # Cargar líneas desde CSV
        items_raw = leer_items_por_pedido(id_pedido)
        if not items_raw:
            messagebox.showwarning("Atención", "Este pedido no tiene líneas.")
            return

        # Normaliza a lo que espera el generador
        items = []
        for r in items_raw:
            items.append({
                "cantidad": int(r.get("cantidad") or 0),
                "producto": r.get("producto",""),
                "precio_unitario": r.get("precio_unitario","0"),
                "importe": r.get("importe","0"),
            })

        try:
            pdf_path = generar_pdf_pedido(
                id_pedido=id_pedido,
                cliente=cliente,
                fecha_str=fecha,
                items=items,
                logo_path="logo.png",
                qr_kind="QR",  # o "CODE128"
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF.\n{e}")
            return

        abrir_pdf(pdf_path)
        messagebox.showinfo("Listo", f"Nota generada (reemplazada si existía).\n\n{os.path.basename(pdf_path)}")


# ---------------- Ventana: editor masivo (completados) ----------------
class EditorMasivo(tk.Toplevel):
    def __init__(self, parent, id_pedido, items, on_saved,
                 frame_style="Dark.TFrame",
                 button_style="Dark.TButton",
                 label_style="Dark.TLabel"):
        super().__init__(parent)
        self.title(f"Editar líneas · Pedido {id_pedido}")
        self.transient(parent); self.grab_set(); self.resizable(True, True)

        self.id_pedido = id_pedido
        self.items = items
        self.on_saved = on_saved
        self.frame_style = frame_style
        self.button_style = button_style
        self.label_style = label_style

        # Importamos aquí para evitar circularidad
        self._actualizar_batch = actualizar_cantidades_completadas_batch

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

        # Validador opcional para Spinbox
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
            self.destroy(); return

        try:
            res = self._actualizar_batch(updates)  # dict { id_pedido: estado }
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el lote.\n{e}")
            return

        nuevo_estado = None
        if isinstance(res, dict):
            nuevo_estado = res.get(self.id_pedido)

        if nuevo_estado:
            messagebox.showinfo("Éxito", f"Cambios guardados.\nNuevo estado: {nuevo_estado}")
        else:
            messagebox.showinfo("Éxito", "Cambios guardados.")

        if callable(self.on_saved):
            self.on_saved()
        self.destroy()


# ---------------- Ventana: editor completo del pedido (sugerencias + precio según descuento) ----------------
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

        # Catálogo para sugerencias y precios
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

        # Filas editables con sugerencias
        self._rows = []  # [(id_linea, entry_prod, var_prod, var_cant, var_pu, lbl_imp, sugg_win), ...]
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

        # Sugerencias
        try:
            sugg = SuggestPopup(
                self, ent_prod, self.product_names,
                on_pick=lambda name, v=vprod, r=row: self._on_pick_product(name, v, r),
            )
        except NameError:
            sugg = None

        # Evita dobles submits por Enter
        ent_prod.bind("<Return>", lambda e: "break")
        sp_q.bind("<Return>", lambda e: "break")
        ent_pu.bind("<Return>", lambda e: "break")

        # Recalcular importe y total
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
            # Formato esperado: YYYY-MM-DD HH:MM
            datetime.strptime(fecha, "%Y-%m-%d %H:%M")
        except Exception:
            messagebox.showerror("Error", "Fecha inválida. Usa formato YYYY-MM-DD HH:MM")
            return

        # --- Normalizador de precio ---
        def norm_price(txt: str) -> float:
            if txt is None:
                return 0.0
            s = str(txt).strip().replace(" ", "").replace("$", "")
            if not s:
                return 0.0
            has_c = "," in s; has_d = "." in s
            if has_c and has_d:
                # si la última coma está después del último punto -> coma decimal
                if s.rfind(",") > s.rfind("."):
                    s = s.replace(".", "")
                    s = s.replace(",", ".")
                else:
                    s = s.replace(",", "")
            elif has_c and not has_d:
                s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
            else:
                if s.count(".") > 1:
                    parts = s.split(".")
                    s = "".join(parts[:-1]) + "." + parts[-1]
            try:
                return float(s)
            except Exception:
                return 0.0

        # --- Construcción de líneas válidas evitando duplicados ---
        nuevas = []
        seen_ids = set()
        for (id_linea, ent, vprod, q, vpu, limpp, _sugg) in self._rows:
            line_id = str(id_linea or "").strip()
            prod = (vprod.get() or "").strip()

            # cantidad
            try:
                cant = int(q.get() or 0)
            except Exception:
                cant = 0

            # precio unitario normalizado
            pu_val = norm_price((vpu.get() or "0").strip())

            # *** REGLA CLAVE: si cantidad == 0, NO guardamos esta línea ***
            if cant <= 0:
                continue

            # si no hay producto, descartar también
            if not prod:
                continue

            # evita duplicados de id_linea
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

        # --- Persistencia ---
        try:
            actualizar_pedido_completo(self.id_pedido, cliente, fecha, nuevas)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el pedido.\n{e}")
            return

        messagebox.showinfo("Éxito", "Pedido actualizado.")
        if callable(self.on_saved):
            self.on_saved()
        self.destroy()



# ---------- Sugerencias tipo “Nueva Nota” (Entry + Listbox flotante) ----------
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
