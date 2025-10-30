import csv, os, re
from datetime import datetime
from data.paths import PRODUCTOS_PATH, PEDIDOS_PATH, PEDIDOS_DETALLE_PATH, CLIENTES_PATH


# ---------------- util numérico ----------------
def _to_std_number(num_str: str) -> str:
    if num_str is None:
        return ""
    s = str(num_str).strip()
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return ""
    has_comma = ',' in s
    has_dot = '.' in s
    if has_comma and has_dot:
        last_comma = s.rfind(',')
        last_dot = s.rfind('.')
        if last_comma > last_dot:   # decimal=coma
            s = s.replace('.', '')
            s = s.replace(',', '.')
        else:                        # decimal=punto
            s = s.replace(',', '')
        return s
    if has_comma and not has_dot:
        if s.count(',') > 1:
            s = s.replace(',', '')
            return s
        right = s.split(',')[-1]
        if 1 <= len(right) <= 2:
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
        return s
    if has_dot and not has_comma:
        if s.count('.') > 1:
            s = s.replace('.', '')
            return s
        right = s.split('.')[-1]
        if 1 <= len(right) <= 2:
            return s
        else:
            s = s.replace('.', '')
            return s
    return s

# ---------------- Esquemas ----------------
PEDIDOS_FIELDS = [
    "id_pedido", "fecha", "cliente", "total", "estado",
    "descuento",             # 0/1: precios con descuento al capturar
    "pagado",                # 0/1
    "descuento_pago_pct",    # % aplicado en cobranza
    "total_cobro",           # total con descuento de cobranza
]

DETALLE_FIELDS = [
    "id_linea", "id_pedido", "producto", "cantidad",
    "cantidad_completada", "precio_unitario", "importe"
]

# ---------------- archivos base ----------------
def ensure_files():
    # productos
    if not os.path.exists(PRODUCTOS_PATH):
        with open(PRODUCTOS_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["producto", "precio", "precio_desc"])
            writer.writerow(["Tubo PVC 1/2", "12.50", "10.80"])

    # encabezados
    if not os.path.exists(PEDIDOS_PATH):
        with open(PEDIDOS_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(PEDIDOS_FIELDS)

    # detalle
    if not os.path.exists(PEDIDOS_DETALLE_PATH):
        with open(PEDIDOS_DETALLE_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(DETALLE_FIELDS)
    
    # clientes
    if not os.path.exists(CLIENTES_PATH):
        with open(CLIENTES_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id_cliente","nombre","descuento"])  # descuento: 0/1
            w.writerow(["C0001","Cliente Demo Sin Desc", "0"])
            w.writerow(["C0002","Cliente Demo Con Desc", "1"])

def generar_id_pedido_ym(now: datetime | None = None) -> str:
    now = now or datetime.now()
    yyyymm = now.strftime("%Y%m")
    if not os.path.exists(PEDIDOS_PATH):
        ensure_files()

    max_seq = 0
    with open(PEDIDOS_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            folio = (row.get("id_pedido") or "").strip()
            if not folio.startswith(yyyymm + "-"):
                continue
            try:
                seq = int(folio.split("-")[-1])
                if seq > max_seq:
                    max_seq = seq
            except Exception:
                pass
    return f"{yyyymm}-{(max_seq+1):03d}"

# ---------------- productos ----------------
def cargar_productos():
    candidate_encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    last_err = None
    for enc in candidate_encodings:
        try:
            with open(PRODUCTOS_PATH, "r", newline="", encoding=enc, errors="strict") as f:
                sample = f.read(4096); f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
                except Exception:
                    dialect = csv.excel; dialect.delimiter = ","
                reader = csv.DictReader(f, dialect=dialect)
                rows = list(reader)
        except Exception as e:
            last_err = e; continue

        norm = []
        for r in rows:
            rr = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            producto = rr.get("producto") or rr.get("nombre") or rr.get("descripcion") or ""
            precio_raw = rr.get("precio") or rr.get("precio_unitario") or rr.get("p.unit") or rr.get("p unit") or ""
            precio_desc_raw = rr.get("precio_desc") or rr.get("precio con descuento") or rr.get("precio_descuento") or ""
            precio_std = _to_std_number(precio_raw) if precio_raw else ""
            precio_desc_std = _to_std_number(precio_desc_raw) if precio_desc_raw else ""
            if not precio_desc_std:
                precio_desc_std = precio_std
            norm.append({
                "producto": producto,
                "precio": precio_std,
                "precio_desc": precio_desc_std
            })
        return norm
    raise UnicodeDecodeError(
        f"No se pudo leer {PRODUCTOS_PATH} con {candidate_encodings}. Último error: {last_err}"
    )

# ---------------- helpers de IO ----------------
def _leer_todas_lineas():
    if not os.path.exists(PEDIDOS_DETALLE_PATH):
        ensure_files()
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def _escribir_todas_lineas(rows):
    with open(PEDIDOS_DETALLE_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DETALLE_FIELDS)
        w.writeheader()
        w.writerows(rows)

def _write_pedidos(rows):
    with open(PEDIDOS_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PEDIDOS_FIELDS)
        w.writeheader()
        w.writerows(rows)

# ---------------- CRUD de pedidos ----------------
def registrar_pedido(header: dict, items: list[dict]):
    """
    header: {id_pedido, fecha, cliente, total, estado, descuento(0/1)}
    items:  [{id_linea?, producto, cantidad, precio_unitario, importe}, ...]
    """
    descuento = str(header.get("descuento", "0")).strip()
    header_out = {
        "id_pedido": header["id_pedido"],
        "fecha": header["fecha"],
        "cliente": header["cliente"],
        "total": header["total"],
        "estado": header["estado"],  # Pendiente
        "descuento": "1" if descuento in ("1", "true", "True", "si", "sí") else "0",
        "pagado": "0",
        "descuento_pago_pct": "",
        "total_cobro": "",
    }

    file_exists = os.path.exists(PEDIDOS_PATH) and os.path.getsize(PEDIDOS_PATH) > 0
    with open(PEDIDOS_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PEDIDOS_FIELDS)
        if not file_exists:
            w.writeheader()
        w.writerow(header_out)

    file_exists = os.path.exists(PEDIDOS_DETALLE_PATH) and os.path.getsize(PEDIDOS_DETALLE_PATH) > 0
    with open(PEDIDOS_DETALLE_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DETALLE_FIELDS)
        if not file_exists:
            w.writeheader()
        for i, it in enumerate(items, start=1):
            id_linea = it.get("id_linea") or f"{header['id_pedido']}-{i}"
            cantidad = int(it.get("cantidad", 0))
            precio_u = _to_std_number(it.get("precio_unitario", "0"))
            importe = _to_std_number(it.get("importe", "0"))
            w.writerow({
                "id_linea": id_linea,
                "id_pedido": header["id_pedido"],
                "producto": it.get("producto",""),
                "cantidad": cantidad,
                "cantidad_completada": 0,
                "precio_unitario": precio_u,
                "importe": importe
            })

def leer_pedidos():
    if not os.path.exists(PEDIDOS_PATH):
        ensure_files()
    with open(PEDIDOS_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    norm = []
    for r in rows:
        rr = { (k or "").strip(): (v or "").strip() for k, v in r.items() }
        if "descuento" not in rr: rr["descuento"] = "0"
        if "pagado" not in rr: rr["pagado"] = "0"
        if "descuento_pago_pct" not in rr: rr["descuento_pago_pct"] = ""
        if "total_cobro" not in rr: rr["total_cobro"] = ""
        if "estado" not in rr: rr["estado"] = "Pendiente"
        norm.append(rr)
    return norm

def leer_items_por_pedido(id_pedido: str):
    id_pedido = str(id_pedido)
    if not os.path.exists(PEDIDOS_DETALLE_PATH):
        ensure_files()
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    fixed = []
    for r in rows:
        if r.get("id_pedido") != id_pedido:
            continue
        cantidad = int((r.get("cantidad") or "0").strip() or 0)
        cant_comp = int((r.get("cantidad_completada") or "0").strip() or 0)
        fixed.append({
            "id_linea": r.get("id_linea") or f"{id_pedido}-X",
            "id_pedido": id_pedido,
            "producto": r.get("producto",""),
            "cantidad": cantidad,
            "cantidad_completada": cant_comp,
            "precio_unitario": r.get("precio_unitario",""),
            "importe": r.get("importe","")
        })
    return fixed

def actualizar_cantidad_completada(id_linea: str, nueva_cantidad: int):
    rows = _leer_todas_lineas()
    actualizado = False
    for r in rows:
        if str(r.get("id_linea")) == str(id_linea):
            cantidad = int((r.get("cantidad") or 0))
            nueva = max(0, min(int(nueva_cantidad), cantidad))
            r["cantidad_completada"] = str(nueva)
            actualizado = True
            pid = r["id_pedido"]
            break
    if actualizado:
        _escribir_todas_lineas(rows)
        recalc_estado_pedido(pid)
    return actualizado

def recalc_estado_pedido(id_pedido: str):
    """No recalcula si el pedido está Cancelado (respeta el estado)."""
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    estado_actual = None
    for p in pedidos:
        if p["id_pedido"] == id_pedido:
            estado_actual = p.get("estado","")
            break
    if estado_actual and estado_actual.lower() == "cancelado":
        return

    items = leer_items_por_pedido(id_pedido)
    if not items:
        return
    all_zero = all(int(i["cantidad_completada"]) == 0 for i in items)
    all_full = all(int(i["cantidad_completada"]) >= int(i["cantidad"]) for i in items)
    estado = "Completado" if all_full else ("Pendiente" if all_zero else "Parcial")

    for p in pedidos:
        if p["id_pedido"] == id_pedido:
            p["estado"] = estado
    _write_pedidos(pedidos)

def actualizar_cantidades_completadas_batch(updates: list[tuple[str, int]]):
    rows = _leer_todas_lineas()
    index_by_id = { str(r.get("id_linea")): i for i, r in enumerate(rows) }
    pedidos_afectados = set()

    for id_linea, nueva in updates:
        key = str(id_linea)
        if key not in index_by_id:
            continue
        i = index_by_id[key]
        r = rows[i]
        cantidad = int((r.get("cantidad") or 0))
        nueva_ok = max(0, min(int(nueva), cantidad))
        rows[i]["cantidad_completada"] = str(nueva_ok)
        pedidos_afectados.add(str(r.get("id_pedido")))

    _escribir_todas_lineas(rows)
    res = {}
    for pid in pedidos_afectados:
        recalc_estado_pedido(pid)
        for p in leer_pedidos():
            if p["id_pedido"] == pid:
                res[pid] = p.get("estado","")
                break
    return res

def actualizar_pedido_completo(id_pedido: str, cliente: str, fecha: str, nuevas_lineas: list[dict]):
    """
    Preserva 'descuento' y columnas de cobranza.
    Ignora cualquier línea con cantidad <= 0 (se elimina del detalle).
    """
    id_pedido = str(id_pedido)

    # 1) Filtrado anticipado de líneas (cant > 0)
    filtradas = []
    for it in (nuevas_lineas or []):
        try:
            c = int(it.get("cantidad") or 0)
        except Exception:
            c = 0
        if c <= 0:
            continue
        filtradas.append(it)
    nuevas_lineas = filtradas

    # 2) Cargar detalle
    rows = _leer_todas_lineas()
    actuales = [r for r in rows if str(r.get("id_pedido")) == id_pedido]
    otras = [r for r in rows if str(r.get("id_pedido")) != id_pedido]

    by_id = { str(r.get("id_linea")): r for r in actuales }
    nuevos_rows = []
    sec = 1
    for it in nuevas_lineas:
        prod = str(it.get("producto","")).strip()
        try:
            cant = int(it.get("cantidad") or 0)
        except Exception:
            cant = 0
        punit = _to_std_number(it.get("precio_unitario","0"))
        id_linea = str(it.get("id_linea") or "").strip()
        if id_linea and id_linea in by_id:
            prev = by_id[id_linea]
            prev_comp = int((prev.get("cantidad_completada") or 0))
            cant_comp = max(0, min(prev_comp, cant))
        else:
            id_linea = f"{id_pedido}-{sec}"; sec += 1
            cant_comp = 0
        try:
            importe = float(punit or "0") * float(cant)
        except:
            importe = 0.0

        nuevos_rows.append({
            "id_linea": id_linea,
            "id_pedido": id_pedido,
            "producto": prod,
            "cantidad": str(cant),
            "cantidad_completada": str(cant_comp),
            "precio_unitario": _to_std_number(punit),
            "importe": f"{importe:.2f}"
        })

    _escribir_todas_lineas(otras + nuevos_rows)

    # 3) Recalcular total/estado preservando campos
    pedidos = leer_pedidos()
    total = 0.0
    all_zero, all_full = True, True
    for r in nuevos_rows:
        try:
            total += float(_to_std_number(r.get("importe","0")))
        except:
            pass
        c = int(r.get("cantidad") or 0)
        cc = int(r.get("cantidad_completada") or 0)
        if cc > 0: all_zero = False
        if cc < c: all_full = False

    estado = "Completado" if nuevos_rows and all_full else ("Pendiente" if (not nuevos_rows or all_zero) else "Parcial")

    for p in pedidos:
        if p["id_pedido"] == id_pedido:
            # preserva columnas adicionales
            descuento_flag = p.get("descuento", "0")
            pagado = p.get("pagado", "0")
            d_pct  = p.get("descuento_pago_pct", "")
            tot_c  = p.get("total_cobro", "")
            p.update({
                "cliente": cliente,
                "fecha": fecha,
                "total": f"{total:.2f}",
                "estado": estado,
                "descuento": descuento_flag,
                "pagado": pagado,
                "descuento_pago_pct": d_pct,
                "total_cobro": tot_c,
            })
    _write_pedidos(pedidos)
    return True

# -------- Cancelación --------
def cancelar_pedido(id_pedido: str) -> bool:
    """
    Cancela el pedido (estado='Cancelado'), pone cantidad_completada=0 en TODAS sus líneas,
    y limpia el pago (pagado=0). Mantiene importes y total (histórico).
    """
    id_pedido = str(id_pedido)
    changed = False

    # 1) Encabezado
    pedidos = leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            p["estado"] = "Cancelado"
            p["pagado"] = "0"
            # mantenemos total como histórico; no tocamos total_cobro/desc_pct
            changed = True
            break
    if changed:
        _write_pedidos(pedidos)

    # 2) Detalle: poner completados=0
    det = _leer_todas_lineas()
    touched = False
    for r in det:
        if str(r.get("id_pedido")) == id_pedido:
            r["cantidad_completada"] = "0"
            touched = True
    if touched:
        _escribir_todas_lineas(det)

    return changed

# -------- Cobranza --------
def marcar_pagado(id_pedido: str, descuento_pct: float = 0.0):
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    ok = False; total_cobro_val = 0.0
    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            try:
                total = float(_to_std_number(p.get("total","0")))
            except:
                total = 0.0
            pct = max(0.0, min(100.0, float(descuento_pct or 0.0)))
            total_cobro_val = max(0.0, total * (1.0 - pct/100.0))
            p["pagado"] = "1"
            p["descuento_pago_pct"] = f"{pct:.2f}"
            p["total_cobro"] = f"{total_cobro_val:.2f}"
            ok = True
            break
    if ok:
        _write_pedidos(pedidos)
    return ok, total_cobro_val

def deshacer_pago(id_pedido: str):
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    ok = False
    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            p["pagado"] = "0"
            p["descuento_pago_pct"] = ""
            p["total_cobro"] = ""
            ok = True
            break
    if ok:
        _write_pedidos(pedidos)
    return ok

def cargar_clientes():
    """
    Devuelve lista de dicts: {id_cliente, nombre, descuento('0'/'1')}
    Lee con detección de delimitador y encoding como cargar_productos().
    """
    candidate_encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    last_err = None
    for enc in candidate_encodings:
        try:
            with open(CLIENTES_PATH, "r", newline="", encoding=enc, errors="strict") as f:
                sample = f.read(4096); f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
                except Exception:
                    dialect = csv.excel; dialect.delimiter = ","
                rows = list(csv.DictReader(f, dialect=dialect))
        except Exception as e:
            last_err = e; continue

        out = []
        for r in rows:
            rr = {(k or "").strip().lower(): (v or "").strip() for k,v in r.items()}
            out.append({
                "id_cliente": rr.get("id_cliente",""),
                "nombre": rr.get("nombre",""),
                "descuento": "1" if (rr.get("descuento","").lower() in ("1","true","sí","si","y","yes")) else "0",
            })
        return out
    raise UnicodeDecodeError(f"No se pudo leer {CLIENTES_PATH} con {candidate_encodings}. Último error: {last_err}")

def buscar_clientes(texto: str):
    """
    Búsqueda simple por subcadena en id_cliente o nombre (case-insensitive).
    Devuelve lista de dicts como cargar_clientes().
    """
    q = (texto or "").strip().lower()
    if not q:
        return []
    data = cargar_clientes()
    res = []
    for c in data:
        if q in (c["id_cliente"] or "").lower() or q in (c["nombre"] or "").lower():
            res.append(c)
    return res
