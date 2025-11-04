# tab_pendientes.py
import os, csv, tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

# Compatibilidad con tu estructura (con/sin paquete data/)
try:
    from data.csv_manager import cargar_productos, leer_pedidos, total_cobro_actual, total_abonado
    from data.paths import PEDIDOS_DETALLE_PATH
except ImportError:
    from data.csv_manager import cargar_productos, leer_pedidos, total_cobro_actual, total_abonado
    from data.paths import PEDIDOS_DETALLE_PATH


def _to_int(v):
    try:
        return int(str(v).strip())
    except Exception:
        return 0


class TabPendientes:
    """
    Pestaña con sub-tabs:
      - "Por producto": pendientes acumulados por producto (respeta orden del catálogo).
      - "Por entregar": pedidos con 'Días desde entrega' N/A, 0 o negativos.
      - "Detalle de Entregas": tabla dinámica Clientes × Productos por fecha (completado/rollover, con opción +7 días).
    """
    def __init__(self, notebook):
        self.frame = ttk.Frame(notebook)

        # ====== Estilos oscuros ======
        self._setup_dark_styles()

        # ====== Sub-notebook ======
        self.nb = ttk.Notebook(self.frame)  # usa el estilo por defecto del tema oscuro
        self.nb.pack(fill="both", expand=True)

        # --- Tab: Por producto ---
        self.tab_prod = ttk.Frame(self.nb, style="Pend.TFrame")
        self.nb.add(self.tab_prod, text="Por producto")

        top = ttk.Frame(self.tab_prod, style="Pend.TFrame"); top.pack(fill="x", padx=12, pady=(10,4))
        ttk.Label(top, text="Pendientes por producto", style="Pend.TLabel").pack(side="left")

        self.var_hide_zeros = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top, text="Ocultar = 0", variable=self.var_hide_zeros,
            command=self._refrescar_vista_prod, style="Pend.TCheckbutton"
        ).pack(side="left", padx=(12,0))

        ttk.Button(top, text="Refrescar", command=self.refrescar, style="Pend.TButton")\
            .pack(side="right")

        body = ttk.Frame(self.tab_prod, style="Pend.TFrame"); body.pack(fill="both", expand=True, padx=12, pady=8)
        cols = ("producto", "pendiente")
        self.tree_prod = ttk.Treeview(body, columns=cols, show="headings", style="Pend.Treeview")
        self.tree_prod.heading("producto", text="Producto")
        self.tree_prod.heading("pendiente", text="Pendiente")
        self.tree_prod.column("producto", anchor="w", width=520)
        self.tree_prod.column("pendiente", anchor="center", width=120)

        sy_prod = ttk.Scrollbar(body, orient="vertical", command=self.tree_prod.yview)
        sx_prod = ttk.Scrollbar(body, orient="horizontal", command=self.tree_prod.xview)
        self.tree_prod.configure(yscrollcommand=sy_prod.set, xscrollcommand=sx_prod.set)

        self.tree_prod.grid(row=0, column=0, sticky="nsew")
        sy_prod.grid(row=0, column=1, sticky="ns")
        sx_prod.grid(row=1, column=0, sticky="ew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.tree_prod.tag_configure("odd", background="#242424")
        self.tree_prod.tag_configure("even", background="#1e1e1e")

        # cache para "Por producto"
        self._rows_full = []

        # --- Tab: Por entregar (N/A, <= 0) ---
        self.tab_ent = ttk.Frame(self.nb, style="Pend.TFrame")
        self.nb.add(self.tab_ent, text="Por entregar")

        top2 = ttk.Frame(self.tab_ent, style="Pend.TFrame"); top2.pack(fill="x", padx=12, pady=(10,4))
        ttk.Label(top2, text="Pedidos por entregar (N/A, ≤ 0 días)", style="Pend.TLabel").pack(side="left")
        ttk.Button(top2, text="Refrescar", command=self.refrescar, style="Pend.TButton").pack(side="right")

        body2 = ttk.Frame(self.tab_ent, style="Pend.TFrame"); body2.pack(fill="both", expand=True, padx=12, pady=8)
        cols2 = ("id_pedido","cliente","fecha_entrega","dias_entrega","estado","total","abonado","saldo")
        headers2 = {
            "id_pedido":"ID",
            "cliente":"Cliente",
            "fecha_entrega":"Fecha entrega",
            "dias_entrega":"Días desde entrega",
            "estado":"Estado",
            "total":"Total",
            "abonado":"Abonado",
            "saldo":"Saldo"
        }
        self.tree_ent = ttk.Treeview(body2, columns=cols2, show="headings", style="Pend.Treeview")
        for c in cols2:
            self.tree_ent.heading(c, text=headers2[c])
            width_map = {"id_pedido":120, "cliente":240, "fecha_entrega":140, "dias_entrega":140,
                         "estado":110, "total":100, "abonado":100, "saldo":100}
            self.tree_ent.column(c, anchor="center", width=width_map.get(c, 110))

        sy_ent = ttk.Scrollbar(body2, orient="vertical", command=self.tree_ent.yview)
        sx_ent = ttk.Scrollbar(body2, orient="horizontal", command=self.tree_ent.xview)
        self.tree_ent.configure(yscrollcommand=sy_ent.set, xscrollcommand=sx_ent.set)

        self.tree_ent.grid(row=0, column=0, sticky="nsew")
        sy_ent.grid(row=0, column=1, sticky="ns")
        sx_ent.grid(row=1, column=0, sticky="ew")
        body2.grid_rowconfigure(0, weight=1)
        body2.grid_columnconfigure(0, weight=1)

        self.tree_ent.tag_configure("odd", background="#242424")
        self.tree_ent.tag_configure("even", background="#1e1e1e")

        # --- Tab: Detalle de Entregas (Pivot Clientes × Productos) ---
        self.tab_pivot = ttk.Frame(self.nb, style="Pend.TFrame")
        self.nb.add(self.tab_pivot, text="Detalle de Entregas")

        hdr = ttk.Frame(self.tab_pivot, style="Pend.TFrame"); hdr.pack(fill="x", padx=12, pady=(10,4))

        ttk.Label(hdr, text="Fecha base (YYYY-MM-DD):", style="Pend.TLabel").pack(side="left", padx=(0,6))
        self.var_fecha = tk.StringVar()
        ent_fecha = ttk.Entry(hdr, textvariable=self.var_fecha, width=12)
        ent_fecha.pack(side="left")

        self.var_semana = tk.BooleanVar(value=True)
        ttk.Checkbutton(hdr, text="Próximos 7 días", variable=self.var_semana, style="Pend.TCheckbutton")\
            .pack(side="left", padx=(12,0))

        self.var_modo = tk.StringVar(value="completado")  # "completado" | "rollover"
        ttk.Label(hdr, text="Mostrar:", style="Pend.TLabel").pack(side="left", padx=(12,6))
        ttk.Radiobutton(hdr, text="Completado", value="completado", variable=self.var_modo, style="Pend.TCheckbutton")\
            .pack(side="left")
        ttk.Radiobutton(hdr, text="Pendiente (rollover)", value="rollover", variable=self.var_modo, style="Pend.TCheckbutton")\
            .pack(side="left", padx=(8,0))

        ttk.Button(hdr, text="Generar", command=self._refresh_pivot, style="Pend.TButton").pack(side="right")

        wrap = ttk.Frame(self.tab_pivot, style="Pend.TFrame"); wrap.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree_pivot = ttk.Treeview(wrap, columns=("cliente",), show="headings", style="Pend.Treeview")
        self.tree_pivot.heading("cliente", text="Cliente")
        self.tree_pivot.column("cliente", anchor="w", width=260)

        sy = ttk.Scrollbar(wrap, orient="vertical", command=self.tree_pivot.yview)
        sx = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree_pivot.xview)
        self.tree_pivot.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        self.tree_pivot.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        self.tree_pivot.tag_configure("odd", background="#242424")
        self.tree_pivot.tag_configure("even", background="#1e1e1e")

        # Primera carga
        self.refrescar()

    # ==================== Estilos ====================
    def _setup_dark_styles(self):
        style = ttk.Style()
        style.configure("Pend.TFrame", background="#1b1b1b")
        style.configure("Pend.TLabel", background="#1b1b1b", foreground="#ffffff")
        style.configure("Pend.TButton", background="#2b2b2b", foreground="#ffffff")
        style.map("Pend.TButton", background=[('active', '#333333'), ('pressed', '#3a3a3a')])
        style.configure("Pend.TCheckbutton", background="#1b1b1b", foreground="#ffffff")
        style.configure("Pend.Treeview",
                        background="#1e1e1e",
                        fieldbackground="#1e1e1e",
                        foreground="#ffffff",
                        rowheight=24,
                        bordercolor="#3a3a3a",
                        borderwidth=0)
        style.map("Pend.Treeview",
                  background=[('selected', '#334155')],
                  foreground=[('selected', '#ffffff')])
        style.configure("Pend.Treeview.Heading",
                        background="#2a2a2a",
                        foreground="#ffffff",
                        relief="flat")
        style.map("Pend.Treeview.Heading",
                  background=[('active', '#323232')])

    # ==================== Utilidades Pivot ====================
    def _parse_dt_safe(self, s: str):
        s = (s or "").strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
        return None

    def _leer_detalle_raw(self):
        rows = []
        if not os.path.exists(PEDIDOS_DETALLE_PATH):
            return rows
        try:
            with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer {PEDIDOS_DETALLE_PATH}.\n{e}")
        return rows

    def _rango_fechas(self, base: datetime, incluir_semana: bool):
        if incluir_semana:
            return [base + timedelta(days=i) for i in range(0, 8)]  # base + 0..7
        return [base]

    def _productos_orden(self):
        # Respeta orden del catálogo ya usado en "Por producto"
        try:
            cats = cargar_productos() or []
        except Exception:
            cats = []
        productos = [(p.get("producto") or "").strip() for p in cats if (p.get("producto") or "").strip()]
        if productos:
            return productos
        # fallback: deducir desde detalle
        detalle = self._leer_detalle_raw()
        return sorted({(r.get("producto") or "").strip() for r in detalle if r.get("producto")})

    # ==================== Datos (Por producto) ====================
    def _orden_catalogo(self) -> list[str]:
        try:
            catalogo = cargar_productos() or []
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer productos.\n{e}")
            catalogo = []
        return [(p.get("producto") or "").strip()
                for p in catalogo if (p.get("producto") or "").strip()]

    def _pedidos_activos(self) -> set[str]:
        try:
            pedidos = leer_pedidos() or []
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer pedidos.\n{e}")
            return set()
        vivos = { (p.get("id_pedido") or "").strip()
                  for p in pedidos
                  if (p.get("estado","").strip().lower() != "cancelado") }
        return {x for x in vivos if x}

    def _acumular_pendientes(self, activos: set[str]) -> dict[str, int]:
        res = {}
        if not os.path.exists(PEDIDOS_DETALLE_PATH):
            return res
        try:
            with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
                rd = csv.DictReader(f)
                for r in rd:
                    pid = (r.get("id_pedido") or "").strip()
                    if pid not in activos:
                        continue
                    prod = (r.get("producto") or "").strip()
                    if not prod:
                        continue
                    cant = _to_int(r.get("cantidad"))
                    comp = _to_int(r.get("cantidad_completada"))
                    pend = max(0, cant - comp)
                    if pend:
                        res[prod] = res.get(prod, 0) + pend
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer {PEDIDOS_DETALLE_PATH}.\n{e}")
        return res

    def _llenar_cache_prod(self, orden: list[str], pendientes_map: dict[str,int]):
        rows = []
        for prod in orden:
            pend = pendientes_map.get(prod, 0)
            rows.append((prod, pend))
        self._rows_full = rows

    def _pintar_prod(self, rows):
        for iid in self.tree_prod.get_children():
            self.tree_prod.delete(iid)
        for i, tup in enumerate(rows):
            tag = "odd" if i % 2 else "even"
            self.tree_prod.insert("", "end", values=tup, tags=(tag,))

    def _refrescar_vista_prod(self):
        if self.var_hide_zeros.get():
            rows = [r for r in self._rows_full if r[1] != 0]
        else:
            rows = self._rows_full
        self._pintar_prod(rows)

    # ==================== Datos (Por entregar) ====================
    def _pintar_ent(self, rows):
        for iid in self.tree_ent.get_children():
            self.tree_ent.delete(iid)
        for i, tup in enumerate(rows):
            tag = "odd" if i % 2 else "even"
            self.tree_ent.insert("", "end", values=tup, tags=(tag,))

    def _refrescar_entregar(self):
        """
        Muestra pedidos con 'días desde entrega' N/A o ≤ 0.
        Equivale a: entrega sin fecha o futura/hoy.
        """
        try:
            pedidos = leer_pedidos() or []
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer pedidos.\n{e}")
            return

        rows = []
        for p in pedidos:
            if (p.get("estado","").strip().lower() == "cancelado"):
                continue

            pid = p.get("id_pedido","")
            cliente = p.get("cliente","")
            fecha_entrega = p.get("fecha_entrega","")
            estado = p.get("estado","")

            # total, abonado, saldo, y días desde entrega (firmado)
            try:
                objetivo, _, dias_disp = total_cobro_actual(pid)
            except Exception:
                objetivo, dias_disp = 0.0, "N/A"
            try:
                abonado = total_abonado(pid)
            except Exception:
                abonado = 0.0
            saldo = max(0.0, float(objetivo) - float(abonado))

            # Criterio de filtro: N/A o entero <= 0
            show = False
            if isinstance(dias_disp, str):
                show = (dias_disp.strip().upper() == "N/A")
            else:
                try:
                    show = (int(dias_disp) <= 0)
                except Exception:
                    show = False

            if show:
                rows.append((
                    pid,
                    cliente,
                    fecha_entrega or "—",
                    dias_disp if isinstance(dias_disp, int) else "N/A",
                    estado,
                    f"{objetivo:.2f}",
                    f"{abonado:.2f}",
                    f"{saldo:.2f}",
                ))

        self._pintar_ent(rows)

    # ==================== Pivot (Detalle de Entregas) ====================
    def _build_pivot_data(self, base_date: datetime, incluir_semana: bool, modo: str):
        """
        Devuelve:
          - productos: lista de productos (en orden del catálogo si existe)
          - matrix: dict[day_key][cliente][producto] = cantidad (según modo)
        'modo' = "completado" | "rollover"
        """
        try:
            pedidos = leer_pedidos() or []
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron leer pedidos.\n{e}")
            return [], {}

        pedidos = [p for p in pedidos if (p.get("estado","").strip().lower() != "cancelado")]
        detalle = self._leer_detalle_raw()

        # Índices
        by_id = { (p.get("id_pedido") or "").strip(): p for p in pedidos }
        productos = self._productos_orden()

        # Construcción por rango de días
        dias = self._rango_fechas(base_date, incluir_semana)
        dias_key = [d.strftime("%Y-%m-%d") for d in dias]
        matrix = { dk: {} for dk in dias_key }

        for r in detalle:
            pid = (r.get("id_pedido") or "").strip()
            prod = (r.get("producto") or "").strip()
            if not (pid and prod):
                continue
            pinfo = by_id.get(pid)
            if not pinfo:
                continue
            if (pinfo.get("estado","").strip().lower() == "cancelado"):
                continue

            cliente = (pinfo.get("cliente") or "").strip()
            dt_ent = self._parse_dt_safe(pinfo.get("fecha_entrega",""))  # puede ser None
            if not dt_ent:
                # sin fecha de entrega no participa en el pivot por fecha
                continue

            day_key_ent = dt_ent.strftime("%Y-%m-%d")
            cant = _to_int(r.get("cantidad"))
            comp = _to_int(r.get("cantidad_completada"))
            comp = max(0, min(comp, cant))
            pend = max(0, cant - comp)

            if modo == "completado":
                if day_key_ent in matrix:
                    row = matrix[day_key_ent].setdefault(cliente, {})
                    row[prod] = row.get(prod, 0) + comp
            else:
                # Modo rollover:
                # - Lo completado se considera 0 en la fecha original (solo para mantener estructura)
                if day_key_ent in matrix and comp > 0:
                    row0 = matrix[day_key_ent].setdefault(cliente, {})
                    row0.setdefault(prod, row0.get(prod, 0))  # no sumamos comp; mantenemos 0 para claridad
                # - Lo pendiente se empuja a D+1
                if pend > 0:
                    next_day = dt_ent + timedelta(days=1)
                    nd_key = next_day.strftime("%Y-%m-%d")
                    if nd_key in matrix:
                        rowp = matrix[nd_key].setdefault(cliente, {})
                        rowp[prod] = rowp.get(prod, 0) + pend

        return productos, matrix

    def _paint_one_pivot_day(self, day_key: str, productos: list, data: dict):
        """Pinta una tabla para un día específico (day_key) en self.tree_pivot."""
        # Configurar columnas dinámicas: cliente + productos
        cols = ["cliente"] + productos
        self.tree_pivot.configure(columns=cols)
        for c in cols:
            if c == "cliente":
                self.tree_pivot.heading(c, text="Cliente")
                self.tree_pivot.column(c, anchor="w", width=260, stretch=True)
            else:
                self.tree_pivot.heading(c, text=c)
                self.tree_pivot.column(c, anchor="center", width=110, stretch=False)

        # Encabezado de día como fila separadora
        self.tree_pivot.insert("", "end", values=(f"— {day_key} —", *[""]*(len(cols)-1)), tags=("even",))

        rows_map = data.get(day_key, {})  # {cliente: {prod: val}}
        clientes = sorted(rows_map.keys())
        for i, cli in enumerate(clientes):
            vals = [cli]
            per_prod = rows_map.get(cli, {})
            for p in productos:
                v = per_prod.get(p, 0)
                vals.append(str(v) if v else "")
            tag = "odd" if i % 2 else "even"
            self.tree_pivot.insert("", "end", values=tuple(vals), tags=(tag,))

    def _refresh_pivot(self):
        # limpiar
        for iid in self.tree_pivot.get_children():
            self.tree_pivot.delete(iid)

        # fecha base
        raw = (self.var_fecha.get() or "").strip()
        base = self._parse_dt_safe(raw) if raw else datetime.now()
        # normalizamos a solo fecha
        base = datetime(year=base.year, month=base.month, day=base.day)

        productos, matrix = self._build_pivot_data(base, bool(self.var_semana.get()), self.var_modo.get())
        if not productos:
            # aseguramos al menos la columna cliente
            self.tree_pivot.configure(columns=("cliente",))
            self.tree_pivot.heading("cliente", text="Cliente")
            self.tree_pivot.column("cliente", anchor="w", width=260, stretch=True)

        # Pintar: uno o varios días
        day_keys = sorted(matrix.keys())
        if not self.var_semana.get():
            day_keys = [base.strftime("%Y-%m-%d")]
        for dk in day_keys:
            self._paint_one_pivot_day(dk, productos, matrix)

    # ==================== Público ====================
    def refrescar(self):
        # Por producto
        orden = self._orden_catalogo()
        activos = self._pedidos_activos()
        pendientes_map = self._acumular_pendientes(activos)
        self._llenar_cache_prod(orden, pendientes_map)
        self._refrescar_vista_prod()

        # Por entregar
        self._refrescar_entregar()

        # Pivot (si ya hay una fecha, mantener; si no, hoy)
        # No auto-generamos para evitar demoras si dataset es grande; puedes habilitar:
        # self._refresh_pivot()
