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

class TabPendientes:
    """
    Tabla oscura de pendientes por producto.
    - Muestra TODOS los productos en el mismo orden que productos.csv (aunque estén en 0).
    - Solo columnas: Producto, Pendiente.
    - Check para ocultar/mostrar los pendientes=0 sin alterar el orden.
    """
    def __init__(self, notebook):
        self.frame = ttk.Frame(notebook)
        self._rows_full = []  # cache [(producto, pendiente)]

        # ====== Estilos oscuros ======
        self._setup_dark_styles()

        # ====== Top bar ======
        top = ttk.Frame(self.frame, style="Pend.TFrame"); top.pack(fill="x", padx=12, pady=(10,4))
        ttk.Label(top, text="Pendientes por producto", style="Pend.TLabel").pack(side="left")

        self.var_hide_zeros = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top, text="Ocultar = 0", variable=self.var_hide_zeros,
            command=self._refrescar_vista, style="Pend.TCheckbutton"
        ).pack(side="left", padx=(12,0))

        ttk.Button(top, text="Refrescar", command=self.refrescar, style="Pend.TButton")\
            .pack(side="right")

        # ====== Tabla ======
        body = ttk.Frame(self.frame, style="Pend.TFrame"); body.pack(fill="both", expand=True, padx=12, pady=8)

        cols = ("producto", "pendiente")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", style="Pend.Treeview")
        self.tree.heading("producto", text="Producto")
        self.tree.heading("pendiente", text="Pendiente")

        self.tree.column("producto", anchor="w", width=520)
        self.tree.column("pendiente", anchor="center", width=120)
        self.tree.pack(fill="both", expand=True)

        # Alternado de filas (oscuro)
        self.tree.tag_configure("odd", background="#242424")
        self.tree.tag_configure("even", background="#1e1e1e")

        # Primera carga
        self.refrescar()

    # ==================== Estilos ====================
    def _setup_dark_styles(self):
        style = ttk.Style()
        # Base frame/labels/buttons oscuros
        style.configure("Pend.TFrame", background="#1b1b1b")
        style.configure("Pend.TLabel", background="#1b1b1b", foreground="#ffffff")
        style.configure("Pend.TButton", background="#2b2b2b", foreground="#ffffff")
        style.map("Pend.TButton",
                  background=[('active', '#333333'), ('pressed', '#3a3a3a')])
        style.configure("Pend.TCheckbutton", background="#1b1b1b", foreground="#ffffff")

        # Treeview oscuro
        style.configure("Pend.Treeview",
                        background="#1e1e1e",
                        fieldbackground="#1e1e1e",
                        foreground="#ffffff",
                        rowheight=26,
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

    # ==================== Datos ====================
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
        """
        Regresa {producto: pendiente_total} considerando solo líneas con id_pedido ∈ activos.
        pendiente = max(0, cantidad - cantidad_completada)
        """
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

    # ==================== Render ====================
    def _llenar_cache(self, orden: list[str], pendientes_map: dict[str,int]):
        """Cachea TODOS los productos en orden, con 0 cuando aplique."""
        rows = []
        for prod in orden:
            pend = pendientes_map.get(prod, 0)
            rows.append((prod, pend))
        self._rows_full = rows

    def _pintar(self, rows):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for i, tup in enumerate(rows):
            tag = "odd" if i % 2 else "even"
            self.tree.insert("", "end", values=tup, tags=(tag,))

    def _refrescar_vista(self):
        if self.var_hide_zeros.get():
            rows = [r for r in self._rows_full if r[1] != 0]
        else:
            rows = self._rows_full
        self._pintar(rows)

    # ==================== Público ====================
    def refrescar(self):
        orden = self._orden_catalogo()
        activos = self._pedidos_activos()
        pendientes_map = self._acumular_pendientes(activos)
        self._llenar_cache(orden, pendientes_map)
        self._refrescar_vista()
