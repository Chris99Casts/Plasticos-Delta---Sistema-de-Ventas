# tab_pendientes.py
import os, csv, tkinter as tk
from tkinter import ttk, messagebox

# Compatibilidad con tu estructura (con/sin paquete data/)
try:
    from data.csv_manager import cargar_productos, leer_pedidos
    from data.paths import PEDIDOS_DETALLE_PATH
except ImportError:
    from data.csv_manager import cargar_productos, leer_pedidos
    from data.paths import PEDIDOS_DETALLE_PATH

def _to_int(v):
    try:
        return int(str(v).strip())
    except Exception:
        return 0

# tab_pendientes.py
import os, csv, tkinter as tk
from tkinter import ttk, messagebox

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
      - "Por producto": la vista existente de pendientes por producto (respeta orden del catálogo).
      - "Por entregar": pedidos con 'Días desde entrega' N/A, 0 o negativos (entrega hoy/futura o sin fecha).
    """
    def __init__(self, notebook):
        self.frame = ttk.Frame(notebook)

        # ====== Estilos oscuros (reusa los existentes) ======
        self._setup_dark_styles()

        # ====== Sub-notebook ======
        self.nb = ttk.Notebook(self.frame)  # usa el estilo por defecto del tema "oscuro" del app
        self.nb.pack(fill="both", expand=True)

        # --- Tab: Por producto (lo que ya existía) ---
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
        self.tree_prod.pack(fill="both", expand=True)
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
            # anchos razonables
            width_map = {"id_pedido":120, "cliente":240, "fecha_entrega":140, "dias_entrega":140,
                         "estado":110, "total":100, "abonado":100, "saldo":100}
            self.tree_ent.column(c, anchor="center", width=width_map.get(c, 110))
        self.tree_ent.pack(fill="both", expand=True)
        self.tree_ent.tag_configure("odd", background="#242424")
        self.tree_ent.tag_configure("even", background="#1e1e1e")

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
        Equivale a: entrega sin fecha o futura/hoy (lo que en Cobranza ves como N/A o números negativos/cero).
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

