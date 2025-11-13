# ui/tab_control_entregas.py
# Pestaña: Control de entregas con "Cerrar viaje"
# - Botón "Cerrar viaje": genera pedidos fantasma con lo pendiente de los pedidos del día seleccionado (Fecha base).
# - Modo 1: Completado (día seleccionado): matriz suma 'cantidad_completada' de pedidos reales con esa fecha_entrega.
# - Modo 2: Pendiente (fantasmas por fecha): matriz suma cantidades de pedidos con es_fantasma=1 cuya fecha_entrega == día seleccionado.
# - Menú contextual en el detalle: "Asignar fecha de entrega…" para pedidos fantasma (obligatorio para que entren a la matriz).
# - Los renglones fantasma en el detalle se pintan de rojo.

import csv
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, date
from collections import defaultdict
import subprocess
import sys
import re

# --------- Imports de datos con compatibilidad de rutas ---------
_HAS_ITEMS_LOADER = False
_HAS_READER = False
_HAS_PRODUCTS = False
cargar_productos = None  # type: ignore
try:
    from data.csv_manager import leer_pedidos, leer_items_por_pedido, cargar_productos  # type: ignore
    _HAS_ITEMS_LOADER = True
    _HAS_READER = True
    _HAS_PRODUCTS = True
except Exception:
    try:
        from csv_manager import leer_pedidos, leer_items_por_pedido, cargar_productos  # type: ignore
        _HAS_ITEMS_LOADER = True
        _HAS_READER = True
        _HAS_PRODUCTS = True
    except Exception:
        _HAS_ITEMS_LOADER = False
        _HAS_READER = False
        _HAS_PRODUCTS = False

_HAS_RL = False
try:
    from reportlab.lib.pagesizes import landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet
    _HAS_RL = True
except Exception:
    _HAS_RL = False
    
# 8.5" x 13.0" en puntos (1in = 72pt)
OFICIO = (72*8.5, 72*13.0)   # (612, 936)


# Paths para fallback de IO directo
PEDIDOS_PATH = None
PEDIDOS_DETALLE_PATH = None
try:
    from data.paths import PEDIDOS_PATH as _P_PATH, PEDIDOS_DETALLE_PATH as _PD_PATH  # type: ignore
    PEDIDOS_PATH, PEDIDOS_DETALLE_PATH = _P_PATH, _PD_PATH
except Exception:
    try:
        from paths import PEDIDOS_PATH as _P_PATH2, PEDIDOS_DETALLE_PATH as _PD_PATH2  # type: ignore
        PEDIDOS_PATH, PEDIDOS_DETALLE_PATH = _P_PATH2, _PD_PATH2
    except Exception:
        pass

# --------- Date picker opcional ---------
_HAS_TKCAL = False
try:
    from tkcalendar import DateEntry
    _HAS_TKCAL = True
except Exception:
    _HAS_TKCAL = False

# --------- Parseo flexible de fechas ---------
_FECHA_FORMATOS = [
    "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    "%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S",
    "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y",
]

# --------- Colores desde productos (matrix_cc) ---------
def _normalize_color(val: str) -> str:
    if not val:
        return ""
    s = str(val).strip().replace(" ", "")

    # Hex tipo #RRGGBB o RRGGBB
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", s):
        return s if s.startswith("#") else "#" + s

    # RGB tipo "r,g,b" o "r;g;b"
    m = re.fullmatch(r"(\d{1,3})[,;](\d{1,3})[,;](\d{1,3})", s)
    if m:
        r, g, b = (max(0, min(255, int(x))) for x in m.groups())
        return f"#{r:02X}{g:02X}{b:02X}"

    # Fallback: quizá nombre de color Tk ("red", etc.)
    return s


def _load_matrix_colors():
    # Lee el CSV de productos y arma un dict {producto: color_hex}
    colores = {}
    if not _HAS_PRODUCTS or cargar_productos is None:
        return colores
    try:
        for prod_row in cargar_productos():  # type: ignore
            nombre = (prod_row.get("producto") or "").strip()
            color_raw = (prod_row.get("matrix_cc") or "").strip()
            color = _normalize_color(color_raw)
            if nombre and color:
                colores[nombre] = color
    except Exception:
        # No queremos romper la pestaña por un problema de colores
        pass
    return colores



def _load_matrix_colors():
    colores = {}
    if not _HAS_PRODUCTS or cargar_productos is None:
        return colores
    try:
        for prod_row in cargar_productos():  # type: ignore
            nombre = (prod_row.get("producto") or "").strip()
            color_raw = (prod_row.get("matrix_cc") or "").strip()
            color = _normalize_color(color_raw)
            if nombre and color:
                colores[nombre] = color
    except Exception:
        pass
    return colores

def _parse_fecha_multi(s: str):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in _FECHA_FORMATOS:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None

# --------- Lectura genérica ---------
def _leer_pedidos_any():
    if _HAS_READER:
        return leer_pedidos()  # type: ignore
    # Fallback CSV
    rows = []
    if not PEDIDOS_PATH or not os.path.exists(PEDIDOS_PATH):
        return rows
    with open(PEDIDOS_PATH, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append(r)
    return rows

def _leer_items_por_pedido_any(pid: str):
    if _HAS_ITEMS_LOADER:
        try:
            return leer_items_por_pedido(pid)  # type: ignore
        except Exception:
            pass
    # Fallback CSV por id_pedido
    rows = []
    if not PEDIDOS_DETALLE_PATH or not os.path.exists(PEDIDOS_DETALLE_PATH):
        return rows
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            if str(r.get("id_pedido","")).strip() == str(pid).strip():
                rows.append(r)
    return rows

# --------- Escritura de "pedidos fantasma" ---------
_PEDIDOS_HEADERS_MIN = [
    "id_pedido","cliente","fecha_creacion","fecha_entrega","estado",
    "es_fantasma","id_origen"
]
_DETALLE_HEADERS_MIN = ["id_linea","id_pedido","producto","cantidad","cantidad_completada","precio_unitario"]

def _csv_ensure_headers(path, headers):
    """
    Se asegura de que el CSV exista y tenga al menos las columnas indicadas en `headers`.
    Si el archivo ya existe pero le faltan columnas, reescribe el encabezado
    agregando las columnas nuevas y rellena esas columnas con "" en las filas viejas.
    """
    if not path:
        raise RuntimeError("No hay ruta CSV.")

    # Si no existe o está vacío → crear desde cero
    if (not os.path.exists(path)) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=headers)
            wr.writeheader()
        return list(headers)

    # Leer encabezado actual + resto de filas
    with open(path, newline="", encoding="utf-8") as f:
        rdr = csv.reader(f)
        try:
            cur = next(rdr)
        except StopIteration:
            cur = []
        data_rows = list(rdr)

    cur = [c.strip() for c in cur]
    if not cur:
        # Archivo sin encabezado útil → reescribimos directo
        with open(path, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=headers)
            wr.writeheader()
        return list(headers)

    final_headers = list(cur)
    changed = False
    for h in headers:
        if h not in final_headers:
            final_headers.append(h)
            changed = True

    # Si no hubo cambios, regresamos lo que ya había
    if not changed:
        return final_headers

    # Reescribir archivo con el nuevo encabezado
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=final_headers)
        wr.writeheader()
        for row in data_rows:
            row_dict = {cur[i]: val for i, val in enumerate(row) if i < len(cur)}
            out = {h: row_dict.get(h, "") for h in final_headers}
            wr.writerow(out)

    return final_headers


def _csv_append_row(path, headers, row):
    """
    Agrega una fila al CSV garantizando que tenga exactamente las columnas de `headers`.
    """
    row = row or {}
    clean_row = {h: row.get(h, "") for h in headers}
    with open(path, "a", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=headers)
        # El encabezado ya debió haberse escrito por _csv_ensure_headers
        wr.writerow(clean_row)



def _new_fantasma_id(base_id: str):
    """
    Genera un id de pedido fantasma corto, único por pedido origen.
    Formato: PH-<id_origen>-NN
    Ejemplo: PH-202511-003-01
    """
    base_id = str(base_id).strip()
    prefix = f"PH-{base_id}-"

    # Si no tenemos archivo o path, usa un sufijo mínimo de emergencia
    if not PEDIDOS_PATH or not os.path.exists(PEDIDOS_PATH):
        return f"{prefix}01"

    max_seq = 0
    try:
        with open(PEDIDOS_PATH, newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                fid = (row.get("id_pedido") or "").strip()
                if not fid.startswith(prefix):
                    continue
                parts = fid.split("-")
                # Última parte como entero (el NN)
                try:
                    seq = int(parts[-1])
                    if seq > max_seq:
                        max_seq = seq
                except Exception:
                    continue
    except Exception:
        # Si algo falla al leer, regresamos al primer sufijo
        return f"{prefix}01"

    return f"{prefix}{max_seq + 1:02d}"


def _crear_pedido_fantasma(origen, cliente, items, fecha_creacion=None):
    """
    Crea el encabezado y detalle de un pedido fantasma:
    - origen: id del pedido original
    - cliente: nombre del cliente
    - items: lista de dicts {producto, cantidad}  (completada=0)
    - fecha_creacion: ahora si no se indica
    Devuelve id_pedido del fantasma.
    """
    if not PEDIDOS_PATH or not PEDIDOS_DETALLE_PATH:
        raise RuntimeError("Rutas CSV no configuradas (PEDIDOS_PATH / PEDIDOS_DETALLE_PATH).")

    pid_f = _new_fantasma_id(origen)
    fecha_crea = (fecha_creacion or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

    # Encabezado (sin fecha_entrega; estado= "fantasma")
    ped_headers = _csv_ensure_headers(PEDIDOS_PATH, _PEDIDOS_HEADERS_MIN)
    row_h = {
        "id_pedido": pid_f,
        "cliente": cliente,
        "fecha_creacion": fecha_crea,
        "fecha_entrega": "",  # obligará a asignar antes de entrar a matriz
        "estado": "fantasma",
        "es_fantasma": "1",
        "id_origen": origen
    }
    # Completa llaves que existan en archivo pero no en row_h
    for h in ped_headers:
        row_h.setdefault(h, "")
    _csv_append_row(PEDIDOS_PATH, ped_headers, row_h)

    # Detalle
    det_headers = _csv_ensure_headers(PEDIDOS_DETALLE_PATH, _DETALLE_HEADERS_MIN)
    for i, it in enumerate(items, start=1):
        row_d = {
            "id_linea": f"{pid_f}-{i}",               # <-- NUEVO: id único por línea del fantasma
            "id_pedido": pid_f,
            "producto": it.get("producto",""),
            "cantidad": int(it.get("cantidad") or 0),
            "cantidad_completada": 0,
            "precio_unitario": it.get("precio_unitario","")
        }
        for h in det_headers:
            row_d.setdefault(h, "")
        _csv_append_row(PEDIDOS_DETALLE_PATH, det_headers, row_d)

    return pid_f

def _asignar_fecha_entrega_csv(id_pedido: str, fecha_str: str):
    """Escribe fecha_entrega para un pedido en PEDIDOS_PATH."""
    if not PEDIDOS_PATH or not os.path.exists(PEDIDOS_PATH):
        raise RuntimeError("No se encontró PEDIDOS_PATH.")
    # Cargar todo, modificar y re-escribir
    with open(PEDIDOS_PATH, newline="", encoding="utf-8") as f:
        rdr = list(csv.DictReader(f))
        headers = rdr[0].keys() if rdr else _PEDIDOS_HEADERS_MIN
    changed = False
    for r in rdr:
        if str(r.get("id_pedido","")).strip() == str(id_pedido).strip():
            r["fecha_entrega"] = fecha_str
            changed = True
    with open(PEDIDOS_PATH, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=headers)
        wr.writeheader()
        for r in rdr:
            wr.writerow(r)
    return changed

# ---------- Clase principal ----------
class TabControlEntregas:
   

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

        self.frame = ttk.Frame(notebook, style=self.frame_style)
        self._build_ui()
        self._configure_grid()
        self.refrescar()

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self.frame, style=self.frame_style)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10,6))
        top.grid_columnconfigure(99, weight=1)

        # Fecha base
        ttk.Label(top, text="Fecha base:", style=self.label_style).grid(row=0, column=0, sticky="w")
        today = date.today()
        if _HAS_TKCAL:
            self.dtp = DateEntry(top, width=12, date_pattern="yyyy-mm-dd",
                                 year=today.year, month=today.month, day=today.day, )
            self.dtp.grid(row=0, column=1, padx=(6,10), sticky="w")

            self.dtp.bind("<<DateEntrySelected>>", lambda e: self.refrescar())
            # Opcional: refrescar también si el usuario escribe manualmente y sale del control
            self.dtp.bind("<FocusOut>", lambda e: self.refrescar())
            self.dtp.bind("<Return>",   lambda e: self.refrescar())

        else:
            self._spn_y = ttk.Spinbox(top, from_=today.year-5, to=today.year+5, width=6); self._spn_y.set(str(today.year))
            self._spn_y.configure(command=self.refrescar)
            self._spn_m = ttk.Spinbox(top, from_=1, to=12, width=4);            self._spn_m.set(str(today.month))
            self._spn_m.configure(command=self.refrescar)
            self._spn_d = ttk.Spinbox(top, from_=1, to=31, width=4);            self._spn_d.set(str(today.day))
            self._spn_d.configure(command=self.refrescar)
            box = ttk.Frame(top, style=self.frame_style); box.grid(row=0, column=1, padx=(6,10), sticky="w")
            ttk.Label(box, text="Año", style=self.label_style).pack(side="left"); self._spn_y.pack(side="left", padx=(0,6))
            ttk.Label(box, text="Mes", style=self.label_style).pack(side="left"); self._spn_m.pack(side="left", padx=(0,6))
            ttk.Label(box, text="Día", style=self.label_style).pack(side="left"); self._spn_d.pack(side="left")
            
            # Dispara cuando el usuario termina de escribir
            for spn in (self._spn_y, self._spn_m, self._spn_d):
                spn.bind("<Return>",   lambda e: self.refrescar())
                spn.bind("<FocusOut>", lambda e: self.refrescar())


        # Botón Cerrar viaje (siempre disponible)
        self.btn_cerrar = ttk.Button(
            top, text="Cerrar viaje",
            command=self._cerrar_viaje_click, style=self.button_style
        )
        self.btn_cerrar.grid(row=0, column=99, sticky="e", padx=(12,0))

        # Botón Imprimir matriz (si ReportLab está disponible)
        self.btn_print = ttk.Button(
            top, text="Imprimir matriz",
            command=self._imprimir_matriz_click, style=self.button_style
        )
        self.btn_print.grid(row=0, column=98, sticky="e", padx=(12,0))


        # --- MATRIZ RESUMEN ---
        self.tree_res = ttk.Treeview(self.frame, show="headings", height=10, style=self.tree_style)
        sy1 = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree_res.yview)
        sx1 = ttk.Scrollbar(self.frame, orient="horizontal", command=self.tree_res.xview)
        self.tree_res.configure(yscrollcommand=sy1.set, xscrollcommand=sx1.set)
        self.tree_res.grid(row=1, column=0, sticky="nsew", padx=(12,0))
        sy1.grid(row=1, column=1, sticky="ns")
        sx1.grid(row=2, column=0, sticky="ew", padx=(12,0))

        # Separador
        sep = ttk.Separator(self.frame, orient="horizontal")
        sep.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(8,2))

        # --- DETALLE ---
        cols_d = ("id_pedido","cliente","producto","cant","comp","pend","estado","es_fantasma","id_origen")
        self.tree_det = ttk.Treeview(self.frame, columns=cols_d, show="headings", height=12, style=self.tree_style)
        headers = {
            "id_pedido":"ID Pedido","cliente":"Cliente","producto":"Producto",
            "cant":"Cant.","comp":"Comp.","pend":"Pend.","estado":"Estado",
            "es_fantasma":"Fantasma","id_origen":"ID Origen"
        }
        widths = {"id_pedido":140,"cliente":200,"producto":220,"cant":80,"comp":80,"pend":80,"estado":100,"es_fantasma":90,"id_origen":140}
        for c in cols_d:
            self.tree_det.heading(c, text=headers[c])
            self.tree_det.column(c, width=widths[c], anchor=("e" if c in ("cant","comp","pend") else "w"), stretch=True)

        # Tags para color rojo en fantasmas
        self.tree_det.tag_configure("fantasma", foreground="#C62828")

        sy2 = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree_det.yview)
        self.tree_det.configure(yscrollcommand=sy2.set)
        self.tree_det.grid(row=4, column=0, sticky="nsew", padx=(12,0), pady=(8,10))
        sy2.grid(row=4, column=1, sticky="ns", pady=(8,10))

        # Menú contextual detalle
        self._popup = tk.Menu(self.frame, tearoff=0)
        self._popup.add_command(label="Asignar fecha de entrega…", command=self._ctx_asignar_fecha)
        self.tree_det.bind("<Button-3>", self._show_context)

    def _configure_grid(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)  # matriz
        self.frame.grid_rowconfigure(4, weight=2)  # detalle
    
    def _matrix_snapshot(self):
        """Lee columnas y filas actuales de tree_res (ignorando la fila separadora vacía)."""
        cols = list(self.tree_res["columns"])
        rows = []
        for iid in self.tree_res.get_children(""):
            vals = list(self.tree_res.item(iid, "values"))
            # ignora filas vacías (separador) si las hay
            if not any(str(v).strip() for v in vals):
                continue
            rows.append(vals)
        return cols, rows
    
    def _imprimir_matriz_click(self):
        cols, rows = self._matrix_snapshot()
        fecha_str = self._selected_date().strftime("%Y-%m-%d")
        if not rows:
            messagebox.showinfo("Info", "No hay datos para imprimir en la matriz.")
            return

        out_dir = os.path.join(os.getcwd(), "reportes")
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, f"matriz_entregas_{fecha_str}.pdf")

        if _HAS_RL:
            try:
                self._export_matrix_pdf(pdf_path, cols, rows, fecha_str)
                self._open_file(pdf_path)
                messagebox.showinfo("Listo", f"Se generó el PDF de la matriz:\n{os.path.basename(pdf_path)}")
                return
            except Exception as e:
                messagebox.showwarning("Aviso", f"No se pudo generar PDF ({e}). Se intentará CSV.")
        # Fallback CSV
        csv_path = os.path.join(out_dir, f"matriz_entregas_{fecha_str}.csv")
        try:
            import csv
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            self._open_file(csv_path)
            messagebox.showinfo("Listo", f"No hubo PDF. Se generó CSV:\n{os.path.basename(csv_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar la matriz.\n{e}")
    
    def _export_matrix_pdf(self, pdf_path, cols, rows, fecha_str):
        # Documento en OFICIO apaisado con márgenes compactos
        from reportlab.lib.units import mm
        page_w, page_h = landscape(OFICIO)
        left = right = 10 * mm
        top  = bottom = 10 * mm

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=(page_w, page_h),
            leftMargin=left, rightMargin=right, topMargin=top, bottomMargin=bottom
        )

        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        title_style.fontSize = 14
        title_style.leading = 16

        story = []
        story.append(Paragraph(f"<b>Control de Entregas – Matriz {fecha_str}</b>", title_style))


    def _open_file(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.call(["open", path])
            else:
                subprocess.call(["xdg-open", path])
        except Exception:
            pass




    # ---------- Helpers ----------
    def _selected_date(self) -> date:
        if _HAS_TKCAL:
            return self.dtp.get_date()
        y = int(self._spn_y.get()); m = int(self._spn_m.get()); d = int(self._spn_d.get())
        return date(year=y, month=m, day=d)

    def _emit_refresh_all(self):
        if callable(self.on_refresh_all):
            self.on_refresh_all()

    # --- Configura columnas de la matriz (cliente + productos + total) ---
        # --- Configura columnas de la matriz (PRODUCTO x CLIENTE + total) ---
    def _reconfig_matrix_columns(self, clientes):
        """
        Filas  : productos
        Columnas: clientes + columna de Total al final.
        """
        cols = ["producto"] + list(clientes) + ["Total"]
        self.tree_res["columns"] = cols

        self.tree_res.heading("producto", text="Producto")
        self.tree_res.column("producto", width=260, anchor="w", stretch=False)

        for c in clientes:
            self.tree_res.heading(c, text=c)
            self.tree_res.column(c, width=110, anchor="e", stretch=False)

        self.tree_res.heading("Total", text="Total")
        self.tree_res.column("Total", width=110, anchor="e", stretch=False)




    # --- Llena filas de la matriz y agrega totales ---
    def _fill_matrix(self, matriz_prod, productos, clientes, color_map):
        """
        Filas : productos (cada fila se colorea según `color_map`).
        Columnas : clientes + Total.
        """
        # Limpiar
        for iid in self.tree_res.get_children():
            self.tree_res.delete(iid)

        # Filas por producto
        for prod in productos:
            row_cliente = matriz_prod.get(prod, {})
            row_vals = [prod]
            total_row = 0
            for cli in clientes:
                v = row_cliente.get(cli, 0)
                row_vals.append("" if v == 0 else str(v))
                total_row += v
            row_vals.append("" if total_row == 0 else str(total_row))

            tags = ()
            color = color_map.get(prod)
            if color:
                safe = re.sub(r"[^a-zA-Z0-9_]", "_", prod) or "prod"
                tag_name = f"prod_{safe}"
                # Configuramos el tag (si ya existe no pasa nada)
                self.tree_res.tag_configure(tag_name, background=color)
                tags = (tag_name,)

            self.tree_res.insert("", "end", values=row_vals, tags=tags)

        # Fila de totales por cliente
        col_totales = []
        for cli in clientes:
            s = 0
            for prod in productos:
                s += matriz_prod.get(prod, {}).get(cli, 0)
            col_totales.append(s)
        total_general = sum(col_totales)

        footer = ["Total"] + [("" if s == 0 else str(s)) for s in col_totales] + [
            "" if total_general == 0 else str(total_general)
        ]
        # Línea en blanco de separación
        self.tree_res.insert("", "end", values=[""] * len(footer))
        # Fila de totales
        self.tree_res.insert("", "end", values=footer)


    # ---------- Carga/Refresco ----------
    def refrescar(self):
        for tv in (self.tree_res, self.tree_det):
            for iid in tv.get_children():
                tv.delete(iid)

        pedidos = _leer_pedidos_any()
       
        dia = self._selected_date()
        color_map = _load_matrix_colors()

        matriz = defaultdict(lambda: defaultdict(int))   # cliente -> producto -> cantidad
        productos_set = set()
        clientes_set = set()


        for p in pedidos:
            estado = (p.get("estado","") or "").strip().lower()
            es_fantasma = str(p.get("es_fantasma","") or "").strip() in ("1","true","yes","y")
            cliente = (p.get("cliente","") or "")

            dt = _parse_fecha_multi(p.get("fecha_entrega",""))
            dt_date = dt.date() if dt else None

            # Matriz: “Completado (día seleccionado)” para pedidos REALES y FANTASMA (excepto cancelados)
            if (estado != "cancelado") and (dt_date == dia):
                pid = p.get("id_pedido","")
                items = _leer_items_por_pedido_any(pid)
                for it in items:
                    prod = (it.get("producto","") or "").strip()
                    try:
                        cant = int(it.get("cantidad") or 0)
                        comp = int(it.get("cantidad_completada") or 0)
                    except Exception:
                        cant, comp = 0, 0
                    comp_ok = max(0, min(comp, cant))
                    if comp_ok > 0:
                        matriz[cliente][prod] += comp_ok
                        clientes_set.add(cliente)
                        if prod:
                            productos_set.add(prod)



            # Detalle (se mantiene para diagnóstico)
            pid = p.get("id_pedido","")
            id_origen = p.get("id_origen","")
            items = _leer_items_por_pedido_any(pid)
            for it in items:
                prod = (it.get("producto","") or "").strip()
                try:
                    cant = int(it.get("cantidad") or 0)
                    comp = int(it.get("cantidad_completada") or 0)
                except Exception:
                    cant, comp = 0, 0
                comp_ok = max(0, min(comp, cant))
                pend = max(0, cant - comp_ok)
                tags = ("fantasma",) if es_fantasma else ()
                self.tree_det.insert(
                    "", "end",
                    values=(pid, cliente, prod, str(cant), str(comp_ok), str(pend),
                            p.get("estado",""), "1" if es_fantasma else "0", id_origen),
                    tags=tags
                )


        # Listas ordenadas de clientes y productos
        clientes = sorted(clientes_set, key=lambda s: s.lower())
        productos = sorted(productos_set, key=lambda s: s.lower())

        # Transponer la matriz: de cliente→producto a producto→cliente
        matriz_prod = defaultdict(lambda: defaultdict(int))
        for cli, prods in matriz.items():
            for prod, qty in prods.items():
                matriz_prod[prod][cli] += qty

        # Colores por producto desde el CSV de productos
        color_map = _load_matrix_colors()

        # Configurar columnas (PRODUCTO x CLIENTE) y llenar filas
        self._reconfig_matrix_columns(clientes)
        self._fill_matrix(matriz_prod, productos, clientes, color_map)



    # ---------- Cerrar viaje (genera fantasmas del día seleccionado) ----------
    def _cerrar_viaje_click(self):
        base_day = self._selected_date()
        if not messagebox.askyesno(
            "Confirmación",
            f"¿Cerrar el viaje del {base_day.strftime('%Y-%m-%d')}?\n\n"
            "Se generarán pedidos ‘fantasma’ con lo PENDIENTE de cada pedido de ese día.\n"
            "Estos pedidos quedarán SIN fecha de entrega hasta que se asigne."
        ):
            return

        pedidos = _leer_pedidos_any()
        creados = 0
        for p in pedidos:
            if (p.get("estado","").strip().lower() == "cancelado"):
                continue
            # No generamos fantasmas de fantasmas
            if str(p.get("es_fantasma","") or "").strip() in ("1","true","yes","y"):
                continue

            dt = _parse_fecha_multi(p.get("fecha_entrega",""))
            if (dt is None) or (dt.date() != base_day):
                continue

            pid = p.get("id_pedido","")
            cliente = p.get("cliente","")
            items = _leer_items_por_pedido_any(pid)

            # Construir lista de pendientes por producto
            pend_items = []
            for it in items:
                try:
                    cant = int(it.get("cantidad") or 0)
                    comp = int(it.get("cantidad_completada") or 0)
                except Exception:
                    cant, comp = 0, 0
                comp_ok = max(0, min(comp, cant))
                pend = max(0, cant - comp_ok)
                if pend > 0:
                    pend_items.append({
                        "producto": it.get("producto",""),
                        "cantidad": pend,
                        "precio_unitario": it.get("precio_unitario","")
                    })

            if pend_items:
                try:
                    _crear_pedido_fantasma(origen=pid, cliente=cliente, items=pend_items)
                    creados += 1
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo crear pedido fantasma de {pid}\n{e}")

        if creados == 0:
            messagebox.showinfo("Sin pendientes", "No se encontraron pendientes para generar pedidos fantasma.")
        else:
            messagebox.showinfo(
                "Viaje cerrado",
                f"Se generaron {creados} pedido(s) fantasma sin fecha de entrega.\n"
                f"Asigna la fecha con clic derecho en el detalle."
            )
        self.refrescar()
        self._emit_refresh_all()

    # ---------- Menú contextual / asignar fecha ----------
    def _show_context(self, event):
        iid = self.tree_det.identify_row(event.y)
        if iid:
            self.tree_det.selection_set(iid)
            self._popup.tk_popup(event.x_root, event.y_root)

    def _ctx_asignar_fecha(self):
        sel = self.tree_det.selection()
        if not sel:
            return
        row = self.tree_det.item(sel[0])["values"]
        pid = row[0]
        es_fantasma = str(row[7]) == "1"
        if not es_fantasma:
            messagebox.showinfo("Info", "Solo aplica a pedidos fantasma.")
            return

        # Dialogo de fecha
        if _HAS_TKCAL:
            top = tk.Toplevel(self.frame)
            top.title("Asignar fecha de entrega")
            ttk.Label(top, text=f"Pedido: {pid}").pack(padx=12, pady=(12,6))
            dtp = DateEntry(top, width=12, date_pattern="yyyy-mm-dd")
            dtp.pack(padx=12, pady=6)
            def ok():
                fecha = dtp.get_date().strftime("%Y-%m-%d")
                _asignar_fecha_entrega_csv(pid, fecha)
                top.destroy()
                self.refrescar()
            ttk.Button(top, text="OK", command=ok).pack(pady=(6,12))
            top.grab_set()
            top.focus_set()
        else:
            fecha = simpledialog.askstring("Fecha de entrega", "YYYY-MM-DD:")
            if not fecha:
                return
            try:
                # validar
                _ = datetime.strptime(fecha, "%Y-%m-%d")
            except Exception:
                messagebox.showerror("Error", "Formato inválido. Usa YYYY-MM-DD.")
                return
            _asignar_fecha_entrega_csv(pid, fecha)
            self.refrescar()
            self._emit_refresh_all()
