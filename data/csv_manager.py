import csv, os, re
from datetime import datetime
from data.paths import PRODUCTOS_PATH, PEDIDOS_PATH, PEDIDOS_DETALLE_PATH, CLIENTES_PATH, PEDIDOS_PAGOS_PATH

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
        if last_comma > last_dot:
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
        return s
    if has_comma and not has_dot:
        if s.count(',') > 1:
            return s.replace(',', '')
        right = s.split(',')[-1]
        return s.replace(',', '.') if 1 <= len(right) <= 2 else s.replace(',', '')
    if has_dot and not has_comma:
        if s.count('.') > 1:
            return s.replace('.', '')
        right = s.split('.')[-1]
        return s if 1 <= len(right) <= 2 else s.replace('.', '')
    return s

# ---------------- Esquemas ----------------
PEDIDOS_FIELDS = [
    "id_pedido","fecha","cliente","total","estado",
    "descuento","pagado","descuento_pago_pct","total_cobro",
    "fecha_entrega","exento_minimo_desc","no_factura"
]
DETALLE_FIELDS = ["id_linea","id_pedido","producto","cantidad","cantidad_completada","precio_unitario","importe"]

# ---------------- helpers de IO seguros (ignoran llaves extra) ----------------
def _csv_rewrite(path: str, headers: list[str], rows: list[dict]):
    """
    Reescribe un CSV conservando sólo las columnas del encabezado.
    Ignora llaves extra (extrasaction='ignore').
    ¡Defensivo!: si rows está vacío y el archivo ya existe con datos, NO sobrescribe.
    """
    # Si nos pasan None, trátalo como lista vacía
    rows = list(rows or [])

    dirp = os.path.dirname(path)
    if dirp:
        os.makedirs(dirp, exist_ok=True)

    # Protección: si el archivo ya existe y tiene contenido (> encabezado) y rows está vacío → no tocar
    if os.path.exists(path) and os.path.getsize(path) > 0 and len(rows) == 0:
        return

    # Escribir (si rows vacío y no había archivo, se crea con sólo encabezado, que es correcto)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)


def _csv_append(path: str, headers: list[str], row: dict):
    """
    Agrega una fila al CSV ignorando llaves extra.
    Crea el archivo con encabezado si no existe o está vacío.
    """
    dirp = os.path.dirname(path)
    if dirp:
        os.makedirs(dirp, exist_ok=True)

    write_header = (not os.path.exists(path)) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if write_header:
            wr.writeheader()
        wr.writerow(row or {})



# ---------------- archivos base ----------------
def ensure_files():
    if not os.path.exists(PRODUCTOS_PATH):
        with open(PRODUCTOS_PATH,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["producto","precio","precio_desc"]); w.writerow(["Tubo PVC 1/2","12.50","10.80"])
    if not os.path.exists(PEDIDOS_PATH):
        with open(PEDIDOS_PATH,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerow(PEDIDOS_FIELDS)
    if not os.path.exists(PEDIDOS_DETALLE_PATH):
        with open(PEDIDOS_DETALLE_PATH,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerow(DETALLE_FIELDS)
    if not os.path.exists(CLIENTES_PATH):
        with open(CLIENTES_PATH,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["id_cliente","nombre","descuento"])
            w.writerow(["C0001","Cliente Demo Sin Desc","0"]); w.writerow(["C0002","Cliente Demo Con Desc","1"])
    if not os.path.exists(PEDIDOS_PAGOS_PATH):
        with open(PEDIDOS_PAGOS_PATH,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerow(["id_pago","id_pedido","fecha","monto"])

def generar_id_pedido_ym(now: datetime | None = None) -> str:
    now = now or datetime.now()
    yyyymm = now.strftime("%Y%m")
    if not os.path.exists(PEDIDOS_PATH): ensure_files()
    max_seq = 0
    with open(PEDIDOS_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            folio = (row.get("id_pedido") or "").strip()
            if folio.startswith(yyyymm + "-"):
                try: max_seq = max(max_seq, int(folio.split("-")[-1]))
                except: pass
    return f"{yyyymm}-{(max_seq+1):03d}"

# ---------------- productos ----------------
def cargar_productos():
    encs = ["utf-8-sig","utf-8","cp1252","latin-1"]; last=None
    for enc in encs:
        try:
            with open(PRODUCTOS_PATH,"r",newline="",encoding=enc,errors="strict") as f:
                sample=f.read(4096); f.seek(0)
                try: dialect=csv.Sniffer().sniff(sample, delimiters=",;|\t")
                except: dialect=csv.excel; dialect.delimiter=","
                rows=list(csv.DictReader(f, dialect=dialect))
        except Exception as e:
            last=e; continue
        norm=[]
        for r in rows:
            rr={(k or "").strip().lower():(v or "").strip() for k,v in r.items()}
            producto = rr.get("producto") or rr.get("nombre") or rr.get("descripcion") or ""
            p = _to_std_number(rr.get("precio","")) if rr.get("precio") else ""
            pd = _to_std_number(rr.get("precio_desc","")) if rr.get("precio_desc") else (p or "")
            norm.append({"producto":producto,"precio":p,"precio_desc":pd})
        return norm
    raise UnicodeDecodeError(f"No se pudo leer {PRODUCTOS_PATH}. Último error: {last}")

# ---------------- helpers de IO (lectura) ----------------
def _leer_todas_lineas():
    if not os.path.exists(PEDIDOS_DETALLE_PATH): ensure_files()
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def _escribir_todas_lineas(rows):
    # rows puede venir vacío por algún flujo; la protección está en _csv_rewrite
    _csv_rewrite(PEDIDOS_DETALLE_PATH, DETALLE_FIELDS, rows)

def _write_pedidos(rows):
    # Normaliza y delega. Si rows vacío y el archivo ya tiene datos, no se sobrescribe.
    rows = list(rows or [])
    for p in rows:
        p.setdefault("no_factura","")
        p.setdefault("fecha_entrega","")
        p.setdefault("exento_minimo_desc","0")
    _csv_rewrite(PEDIDOS_PATH, PEDIDOS_FIELDS, rows)

# ---------------- CRUD de pedidos ----------------
def registrar_pedido(header: dict, items: list[dict]):
    desc = str(header.get("descuento","0")).strip()
    header_out = {
        "id_pedido":header["id_pedido"], "fecha":header["fecha"], "cliente":header["cliente"],
        "total":header["total"], "estado":header["estado"],
        "descuento":"1" if desc in ("1","true","True","si","sí") else "0",
        "pagado":"0", "descuento_pago_pct":"", "total_cobro":"",
        "fecha_entrega":"", "exento_minimo_desc":"0", "no_factura":"",                             # <-- nuevo

    }
    _csv_append(PEDIDOS_PATH, PEDIDOS_FIELDS, header_out)

    # Detalle
    for i,it in enumerate(items, start=1):
        id_linea = it.get("id_linea") or f"{header['id_pedido']}-{i}"
        cantidad = int(it.get("cantidad",0))
        punit = _to_std_number(it.get("precio_unitario","0"))
        importe = _to_std_number(it.get("importe","0"))
        row = {
            "id_linea":id_linea,
            "id_pedido":header["id_pedido"],
            "producto":it.get("producto",""),
            "cantidad":cantidad,
            "cantidad_completada":0,
            "precio_unitario":punit,
            "importe":importe
        }
        _csv_append(PEDIDOS_DETALLE_PATH, DETALLE_FIELDS, row)

def leer_pedidos():
    if not os.path.exists(PEDIDOS_PATH): ensure_files()
    with open(PEDIDOS_PATH, newline="", encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    norm=[]
    for r in rows:
        rr={ (k or "").strip():(v or "").strip() for k,v in r.items() }
        rr.setdefault("descuento","0"); rr.setdefault("pagado","0")
        rr.setdefault("descuento_pago_pct",""); rr.setdefault("total_cobro",""); rr.setdefault("estado","Pendiente")
        rr.setdefault("fecha_entrega",""); rr.setdefault("exento_minimo_desc","0"); rr.setdefault("no_factura","")
        norm.append(rr)
    return norm

def leer_items_por_pedido(id_pedido: str):
    id_pedido = str(id_pedido)
    if not os.path.exists(PEDIDOS_DETALLE_PATH): ensure_files()
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # Detectar si hay líneas de este pedido sin id_linea y auto-repararlas
    need_fix = False
    used_nums = set()
    for r in rows:
        if str(r.get("id_pedido")) != id_pedido:
            continue
        lid = (r.get("id_linea") or "").strip()
        if lid.startswith(f"{id_pedido}-"):
            try:
                n = int(lid.split("-")[-1])
                used_nums.add(n)
            except Exception:
                pass
        if not lid:
            need_fix = True

    if need_fix:
        # Generar consecutivos únicos f"{id_pedido}-<n>"
        def next_num():
            n = 1
            while n in used_nums:
                n += 1
            used_nums.add(n)
            return n

        changed = False
        for r in rows:
            if str(r.get("id_pedido")) != id_pedido:
                continue
            lid = (r.get("id_linea") or "").strip()
            if not lid:
                r["id_linea"] = f"{id_pedido}-{next_num()}"
                changed = True
        if changed:
            _escribir_todas_lineas(rows)  # persistimos la reparación

    # Ahora leemos ya con ids válidos
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
    rows=_leer_todas_lineas(); actualizado=False
    pid=None
    for r in rows:
        if str(r.get("id_linea"))==str(id_linea):
            cantidad=int((r.get("cantidad") or 0))
            r["cantidad_completada"]=str(max(0, min(int(nueva_cantidad), cantidad)))
            actualizado=True; pid=r["id_pedido"]; break
    if actualizado:
        _escribir_todas_lineas(rows)
        recalc_estado_pedido(pid)
    return actualizado

def recalc_estado_pedido(id_pedido: str):
    id_pedido=str(id_pedido); pedidos=leer_pedidos(); estado_actual=None
    for p in pedidos:
        if p["id_pedido"]==id_pedido: estado_actual=p.get("estado",""); break
    if estado_actual and estado_actual.lower()=="cancelado": return
    items=leer_items_por_pedido(id_pedido)
    if not items: return
    all_zero=all(int(i["cantidad_completada"])==0 for i in items)
    all_full=all(int(i["cantidad_completada"])>=int(i["cantidad"]) for i in items)
    estado="Completado" if all_full else ("Pendiente" if all_zero else "Parcial")

    for p in pedidos:
        if p["id_pedido"]==id_pedido:
            p["estado"]=estado
            if estado=="Completado" and (p.get("fecha_entrega","")== ""):
                p["fecha_entrega"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _write_pedidos(pedidos)

def actualizar_cantidades_completadas_batch(updates: list[tuple[str,int]]):
    rows=_leer_todas_lineas(); index_by_id={ str(r.get("id_linea")):i for i,r in enumerate(rows) }
    pedidos_afect=set()
    for id_linea,nueva in updates:
        if str(id_linea) not in index_by_id: continue
        i=index_by_id[str(id_linea)]; r=rows[i]
        cantidad=int((r.get("cantidad") or 0)); rows[i]["cantidad_completada"]=str(max(0,min(int(nueva),cantidad)))
        pedidos_afect.add(str(r.get("id_pedido")))
    _escribir_todas_lineas(rows)
    res={}
    for pid in pedidos_afect:
        recalc_estado_pedido(pid)
        for p in leer_pedidos():
            if p["id_pedido"]==pid: res[pid]=p.get("estado",""); break
    return res

def actualizar_pedido_completo(id_pedido: str, cliente: str, fecha: str, nuevas_lineas: list[dict]):
    id_pedido=str(id_pedido)
    filtradas=[]
    for it in (nuevas_lineas or []):
        try: c=int(it.get("cantidad") or 0)
        except: c=0
        if c>0: filtradas.append(it)
    nuevas_lineas=filtradas

    rows=_leer_todas_lineas()
    actuales=[r for r in rows if str(r.get("id_pedido"))==id_pedido]
    otras=[r for r in rows if str(r.get("id_pedido"))!=id_pedido]
    by_id={ str(r.get("id_linea")):r for r in actuales }
    nuevos=[]; sec=1
    for it in nuevas_lineas:
        prod=str(it.get("producto","")).strip()
        try: cant=int(it.get("cantidad") or 0)
        except: cant=0
        punit=_to_std_number(it.get("precio_unitario","0"))
        id_linea=str(it.get("id_linea") or "").strip()
        if id_linea and id_linea in by_id:
            prev=by_id[id_linea]; prev_comp=int((prev.get("cantidad_completada") or 0))
            cant_comp=max(0, min(prev_comp, cant))
        else:
            id_linea=f"{id_pedido}-{sec}"; sec+=1; cant_comp=0
        try: importe=float(punit or "0")*float(cant)
        except: importe=0.0
        nuevos.append({"id_linea":id_linea,"id_pedido":id_pedido,"producto":prod,"cantidad":str(cant),
                       "cantidad_completada":str(cant_comp),"precio_unitario":_to_std_number(punit),
                       "importe":f"{importe:.2f}"})
    _escribir_todas_lineas(otras+nuevos)

    pedidos=leer_pedidos(); total=0.0; all_zero=True; all_full=True
    for r in nuevos:
        try: total+=float(_to_std_number(r.get("importe","0")))
        except: pass
        c=int(r.get("cantidad") or 0); cc=int(r.get("cantidad_completada") or 0)
        if cc>0: all_zero=False
        if cc<c: all_full=False
    estado="Completado" if nuevos and all_full else ("Pendiente" if (not nuevos or all_zero) else "Parcial")
    for p in pedidos:
        if p["id_pedido"]==id_pedido:
            p.update({"cliente":cliente,"fecha":fecha,"total":f"{total:.2f}","estado":estado,
                      "descuento":p.get("descuento","0"),"pagado":p.get("pagado","0"),
                      "descuento_pago_pct":p.get("descuento_pago_pct",""),"total_cobro":p.get("total_cobro",""),
                      "fecha_entrega":p.get("fecha_entrega",""), "exento_minimo_desc":p.get("exento_minimo_desc","0")})
    _write_pedidos(pedidos); return True

# -------- Cancelación --------
def cancelar_pedido(id_pedido: str) -> bool:
    id_pedido=str(id_pedido); changed=False
    pedidos=leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido")==id_pedido:
            p["estado"]="Cancelado"; p["pagado"]="0"; changed=True; break
    if changed: _write_pedidos(pedidos)
    det=_leer_todas_lineas(); touched=False
    for r in det:
        if str(r.get("id_pedido"))==id_pedido:
            r["cantidad_completada"]="0"; touched=True
    if touched: _escribir_todas_lineas(det)
    return changed

# -------- Clientes --------
def cargar_clientes():
    encs=["utf-8-sig","utf-8","cp1252","latin-1"]; last=None
    for enc in encs:
        try:
            with open(CLIENTES_PATH,"r",newline="",encoding=enc,errors="strict") as f:
                sample=f.read(4096); f.seek(0)
                try: dialect=csv.Sniffer().sniff(sample, delimiters=",;|\t")
                except: dialect=csv.excel; dialect.delimiter=","
                rows=list(csv.DictReader(f, dialect=dialect))
        except Exception as e:
            last=e; continue
        out=[]
        for r in rows:
            rr={(k or "").strip().lower():(v or "").strip() for k,v in r.items()}
            out.append({"id_cliente":rr.get("id_cliente",""),"nombre":rr.get("nombre",""),
                        "descuento":"1" if (rr.get("descuento","").lower() in ("1","true","sí","si","y","yes")) else "0"})
        return out
    raise UnicodeDecodeError(f"No se pudo leer {CLIENTES_PATH}. Último error: {last}")

def buscar_clientes(texto: str):
    q=(texto or "").strip().lower()
    if not q: return []
    data=cargar_clientes(); res=[]
    for c in data:
        if q in (c["id_cliente"] or "").lower() or q in (c["nombre"] or "").lower(): res.append(c)
    return res

def cliente_tiene_descuento_preferencial(id_cliente: str | None, nombre: str | None) -> bool:
    id_cliente=(id_cliente or "").strip().lower(); nombre=(nombre or "").strip().lower()
    for r in cargar_clientes():
        rid=(r.get("id_cliente") or "").strip().lower(); nom=(r.get("nombre") or "").strip().lower()
        pref=(r.get("descuento") or "0") in ("1","true","si","sí")
        if (id_cliente and rid==id_cliente) or (nombre and nom==nombre): return bool(pref)
    return False

# -------- Abonos + Descuento / Pronto-pago --------
def leer_abonos(id_pedido: str):
    if not os.path.exists(PEDIDOS_PAGOS_PATH): ensure_files()
    with open(PEDIDOS_PAGOS_PATH, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if (r.get("id_pedido")==str(id_pedido))]

def _write_abonos(all_rows):
    with open(PEDIDOS_PAGOS_PATH,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["id_pago","id_pedido","fecha","monto"])
        w.writeheader(); w.writerows(all_rows)

def total_abonado(id_pedido: str) -> float:
    tot=0.0
    for r in leer_abonos(id_pedido):
        try: tot+=float(_to_std_number(r.get("monto","0")) or "0")
        except: pass
    return max(0.0, tot)

_FECHA_FORMATOS = [
    "%Y-%m-%d %H:%M","%Y-%m-%d %H:%M:%S","%d/%m/%Y %H:%M","%d/%m/%Y %H:%M:%S",
    "%Y/%m/%d %H:%M","%Y/%m/%d %H:%M:%S","%d-%m-%Y %H:%M","%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d","%d/%m/%Y","%Y/%m/%d","%d-%m-%Y",
]
def _parse_fecha_multi(fecha_str: str) -> datetime | None:
    s = (fecha_str or "").strip()
    if not s:
        return None
    for fmt in _FECHA_FORMATOS:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None

def _dias_desde_signed(fecha_str: str):
    dt = _parse_fecha_multi(fecha_str)
    if dt is None:
        return None
    return (datetime.now() - dt).days  # puede ser negativo (entrega futura)

_MINIMO_NOTA = 3500.0
_PRONTO_PAGO_PCT = 10.0

def set_exento_minimo_desc(id_pedido: str, flag: bool) -> bool:
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    changed = False
    for p in pedidos:
        if p.get("id_pedido")==id_pedido:
            p["exento_minimo_desc"] = "1" if flag else "0"
            changed = True
            break
    if changed:
        _write_pedidos(pedidos)
    return changed

def set_fecha_entrega(id_pedido: str, fecha: str | datetime | None) -> bool:
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    changed = False
    if isinstance(fecha, datetime):
        dt_new = fecha
    else:
        s = (fecha or "").strip()
        if not s:
            dt_new = None
        else:
            dt_new = _parse_fecha_multi(s)
            if dt_new is None:
                raise ValueError("Formato de fecha no válido. Ejemplos: '2025-10-31 14:30', '31/10/2025 14:30', '2025-10-31'.")

    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            if dt_new is not None:
                dt_ped = _parse_fecha_multi(p.get("fecha",""))
                if dt_ped is not None and dt_new < dt_ped:
                    raise ValueError("La fecha de entrega no puede ser anterior a la fecha del pedido.")
                out = dt_new.strftime("%Y-%m-%d %H:%M")
            else:
                out = ""
            p["fecha_entrega"] = out
            changed = True
            break

    if changed:
        _write_pedidos(pedidos)
    return changed

def descuento_eligibilidad(id_pedido: str):
    id_pedido = str(id_pedido)
    for p in leer_pedidos():
        if p.get("id_pedido")!=id_pedido: continue
        pref = (p.get("descuento","0")=="1")
        try: total = float(_to_std_number(p.get("total","0")) or "0")
        except: total = 0.0
        dias = _dias_desde_signed(p.get("fecha_entrega",""))
        minimo_ok = (total >= _MINIMO_NOTA - 1e-9)
        exento = (p.get("exento_minimo_desc","0")=="1")
        elig = (dias is not None) and (0 <= dias <= 7) and (not pref) and (minimo_ok or exento)
        return {'eligible': bool(elig), 'dias': dias, 'pref': pref, 'minimo_ok': minimo_ok, 'exento': exento}
    return {'eligible': False, 'dias': None, 'pref': False, 'minimo_ok': False, 'exento': False}

def estado_pago(id_pedido: str):
    pedidos=leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido")==str(id_pedido):
            try: total=float(_to_std_number(p.get("total","0")) or "0")
            except: total=0.0
            try: objetivo=float(_to_std_number(p.get("total_cobro") or "0") or 0)
            except: objetivo=0.0
            if objetivo<=0: objetivo=total
            abon=total_abonado(id_pedido)
            if abon<=0.0: return "Pago Pendiente", abon, objetivo
            if abon+0.01>=objetivo: return "Pago Completo", abon, objetivo
            return "Pago Parcial", abon, objetivo
    return "Pago Pendiente", 0.0, 0.0

def total_cobro_actual(id_pedido: str):
    """
    (objetivo_actual, pct_aplicado_hoy, dias_desde_entrega|"N/A")
    - Si hay descuento fijo (descuento_pago_pct no vacío y total_cobro>0), usarlo SIEMPRE.
    - Si no, calcula dinámico según elegibilidad pronto-pago.
    """
    id_pedido=str(id_pedido); pedidos=leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido")!=id_pedido: continue
        try: total_pedido=float(_to_std_number(p.get("total","0")) or "0")
        except: total_pedido=0.0

        dias_signed = _dias_desde_signed(p.get("fecha_entrega",""))
        dias_display = dias_signed if dias_signed is not None else "N/A"
        abonados = total_abonado(id_pedido)

        try: fijo=float(_to_std_number(p.get("total_cobro") or "0") or 0)
        except: fijo=0.0
        pct_fijo_txt = (p.get("descuento_pago_pct") or "").strip()
        try: pct_fijo=float(_to_std_number(pct_fijo_txt or "0") or 0.0)
        except: pct_fijo=0.0

        # NUEVO: si hay descuento fijo establecido, mostrarlo aunque no haya abonos
        if fijo > 0 and pct_fijo_txt != "":
            return fijo, pct_fijo, dias_display

        el = descuento_eligibilidad(id_pedido)
        pronto = _PRONTO_PAGO_PCT if el['eligible'] else 0.0
        objetivo = total_pedido*(1.0 - pronto/100.0)
        return objetivo, pronto, dias_display
    return 0.0, 0.0, "N/A"

def registrar_abono(id_pedido: str, monto: float):
    id_pedido=str(id_pedido)
    try: monto=float(monto or 0.0)
    except: monto=-1.0
    if monto<=0.0:
        raise ValueError("El monto debe ser mayor a 0.")

    objetivo_actual, _, _ = total_cobro_actual(id_pedido)
    abonado = total_abonado(id_pedido)
    saldo = max(0.0, objetivo_actual - abonado)
    if saldo <= 0.0:
        raise ValueError("Este pedido ya no tiene saldo por cubrir.")
    if monto > saldo + 1e-9:
        raise ValueError(f"El abono excede el saldo actual (${saldo:.2f}).")

    with open(PEDIDOS_PAGOS_PATH,"a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["id_pago","id_pedido","fecha","monto"])
        if f.tell()==0: w.writeheader()
        pid=f"{id_pedido}-P{int(datetime.now().timestamp())}"
        w.writerow({"id_pago":pid,"id_pedido":id_pedido,"fecha":datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "monto":f"{monto:.2f}"})

    pedidos=leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido")!=id_pedido: continue
        try: total_pedido=float(_to_std_number(p.get("total","0")) or "0")
        except: total_pedido=0.0
        abonado_nuevo = abonado + monto
        try: total_cobro=float(_to_std_number(p.get("total_cobro") or "0") or 0)
        except: total_cobro=0.0
        objetivo = total_cobro or total_pedido

        ya_tenia_desc = bool((p.get("descuento_pago_pct") or "").strip())
        if not ya_tenia_desc:
            el = descuento_eligibilidad(id_pedido)
            pronto = _PRONTO_PAGO_PCT if el['eligible'] else 0.0
            objetivo_posible = total_pedido*(1.0-pronto/100.0)
            if abonado_nuevo + 1e-6 >= objetivo_posible:
                p["descuento_pago_pct"]=f"{pronto:.2f}"; p["total_cobro"]=f"{objetivo_posible:.2f}"
                objetivo=objetivo_posible
        p["pagado"]="1" if (abonado_nuevo + 0.01 >= objetivo) else "0"
        break
    _write_pedidos(pedidos)
    return True

def eliminar_abono(id_pago: str) -> tuple[bool, str]:
    if not os.path.exists(PEDIDOS_PAGOS_PATH): ensure_files()
    with open(PEDIDOS_PAGOS_PATH, newline="", encoding="utf-8-sig") as f:
        all_rows=list(csv.DictReader(f))
    row_map={ r.get("id_pago",""):r for r in all_rows }
    target=row_map.get(id_pago)
    if not target: return False, ""
    id_pedido=target.get("id_pedido","")
    kept=[r for r in all_rows if r.get("id_pago")!=id_pago]; _write_abonos(kept)

    pedidos=leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido")!=id_pedido: continue
        try: total=float(_to_std_number(p.get("total","0")) or "0")
        except: total=0.0
        try: objetivo=float(_to_std_number(p.get("total_cobro") or "0") or 0)
        except: objetivo=0.0
        if objetivo<=0: objetivo=total
        abon=total_abonado(id_pedido)
        p["pagado"]="1" if (abon+0.01>=objetivo) else "0"
        break
    _write_pedidos(pedidos)
    return True, id_pedido

# -------- Descuento forzado (nuevo) --------
def aplicar_descuento_forzado(id_pedido: str, pct: float = 10.0) -> bool:
    """
    Aplica un descuento fijo (forzado) SOLO si:
      - el pedido NO está pagado
      - el cliente NO es preferencial (descuento='1' => preferencial)
    Ajusta total_cobro y marca pagado si los abonos ya cubren el objetivo.
    """
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    objetivo = None
    target = None

    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            target = p
            break
    if not target:
        return False

    # NO permitir forzar si ya está pagado
    if (target.get("pagado", "0") == "1"):
        return False

    # NO permitir forzar si es preferencial
    if (target.get("descuento", "0") == "1"):
        return False

    # Calcular objetivo con descuento
    try:
        total = float(_to_std_number(target.get("total", "0")) or 0.0)
    except Exception:
        total = 0.0

    pct_ok = max(0.0, min(100.0, float(pct or 0.0)))
    objetivo = max(0.0, total * (1.0 - pct_ok/100.0))

    target["descuento_pago_pct"] = f"{pct_ok:.2f}"
    target["total_cobro"] = f"{objetivo:.2f}"

    # Recalcular pagado en función de abonos
    abon = total_abonado(id_pedido)
    target["pagado"] = "1" if (abon + 0.01 >= objetivo) else "0"

    _write_pedidos(pedidos)
    return True

# -------- Quitar descuento forzado --------
def quitar_descuento_forzado(id_pedido: str) -> bool:
    """
    Quita el descuento forzado (limpia descuento_pago_pct y total_cobro).
    Recalcula 'pagado' con base en total sin descuento y abonos.
    """
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    target = None
    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            target = p
            break
    if not target:
        return False

    # limpiar campos fijos
    target["descuento_pago_pct"] = ""
    target["total_cobro"] = ""

    # recalcular pagado vs total normal
    try:
        total = float(_to_std_number(target.get("total", "0")) or 0.0)
    except Exception:
        total = 0.0
    abon = total_abonado(id_pedido)
    target["pagado"] = "1" if (abon + 0.01 >= total) else "0"

    _write_pedidos(pedidos)
    return True

# -------- Soporte a pedidos fantasma --------
def _id_origen_de_fantasma(id_pedido: str) -> str | None:
    """
    Obtiene el id de origen desde el id de un fantasma.
    Formatos soportados:
      - Con columna id_origen en CSV (preferente)
      - Prefijo 'PH-<id_origen>-<timestamp>' sin columna
    """
    id_pedido = str(id_pedido or "")
    if id_pedido.startswith("PH-"):
        parts = id_pedido.split("-")
        if len(parts) >= 3:
            return "-".join(parts[1:-1])
        elif len(parts) == 2:
            return parts[1]
    return None

def _es_pedido_fantasma(p: dict) -> bool:
    if not p: return False
    es_flag = str(p.get("es_fantasma","") or "").strip().lower() in ("1","true","yes","y")
    es_estado = (p.get("estado","") or "").strip().lower() == "fantasma"
    es_prefijo = str(p.get("id_pedido","") or "").startswith("PH-")
    return es_flag or es_estado or es_prefijo

def actualizar_cantidades_completadas_batch_sync(id_pedido: str, updates: list[tuple[str,int]]) -> dict:
    """
    Aplica el batch al FANTASMA y sube al ORIGEN el avance neto (delta) por producto.
    El delta se calcula con los valores *que realmente quedaron* en archivo después del batch.
    Devuelve { id_pedido: estado } incluyendo el origen si aplica.
    """
    id_pedido = str(id_pedido)

    # --- util de normalización de producto ---
    def _norm_prod(s: str) -> str:
        s = (s or "").strip().lower()
        return re.sub(r"\s+", " ", s)

    # --- foto 'antes' de completados del FANTASMA ---
    before_rows = _leer_todas_lineas()
    before_by_id = { str(r.get("id_linea")): r for r in before_rows }
    before_comp = {}
    for id_linea, _ in updates:
        r = before_by_id.get(str(id_linea))
        if r and str(r.get("id_pedido")) == id_pedido:
            try: before_comp[str(id_linea)] = int(r.get("cantidad_completada") or 0)
            except: before_comp[str(id_linea)] = 0

    # --- aplica batch normal (modifica archivo) ---
    estados = actualizar_cantidades_completadas_batch(updates)

    # --- valida que sea fantasma ---
    pedidos = leer_pedidos()
    ped = next((p for p in pedidos if p.get("id_pedido")==id_pedido), {})
    if not _es_pedido_fantasma(ped):
        return estados

    # --- id de ORIGEN ---
    id_origen = (ped.get("id_origen") or "").strip() or _id_origen_de_fantasma(id_pedido)
    if not id_origen:
        return estados

    # --- foto 'después' leída del archivo (lo que *sí quedó*) ---
    after_rows = _leer_todas_lineas()
    after_by_id = { str(r.get("id_linea")): r for r in after_rows }

    # Delta por producto normalizado (usando valor 'después')
    deltas_por_prod: dict[str,int] = {}
    for id_linea, _asked_value in updates:
        r_after = after_by_id.get(str(id_linea))
        if not r_after or str(r_after.get("id_pedido")) != id_pedido:
            continue
        try:
            comp_after = int(r_after.get("cantidad_completada") or 0)
        except:
            comp_after = 0
        comp_before = int(before_comp.get(str(id_linea), 0))
        delta = max(0, comp_after - comp_before)
        if delta <= 0:
            continue
        prod_norm = _norm_prod(r_after.get("producto",""))
        deltas_por_prod[prod_norm] = deltas_por_prod.get(prod_norm, 0) + delta

    if not deltas_por_prod:
        return estados  # no hubo avance neto real

    # --- índice de líneas del ORIGEN por producto ---
    origen_lines = [r for r in after_rows if str(r.get("id_pedido")) == id_origen]
    idx_origen: dict[str, list[dict]] = {}
    for r in origen_lines:
        idx_origen.setdefault(_norm_prod(r.get("producto","")), []).append(r)

    # --- distribuir delta llenando primeras las líneas con mayor pendiente ---
    changed = False
    for prod_norm, delta_total in deltas_por_prod.items():
        lines = idx_origen.get(prod_norm, [])
        if not lines or delta_total <= 0:
            continue

        def pendiente(r):
            try:
                c  = int(r.get("cantidad") or 0)
                cc = int(r.get("cantidad_completada") or 0)
            except:
                c, cc = 0, 0
            return max(0, c - cc)

        lines.sort(key=pendiente, reverse=True)

        rest = int(delta_total)
        for r in lines:
            if rest <= 0:
                break
            c  = int(r.get("cantidad") or 0) if (r.get("cantidad") or "").isdigit() else int(float(r.get("cantidad") or 0))
            cc = int(r.get("cantidad_completada") or 0) if (r.get("cantidad_completada") or "0").isdigit() else int(float(r.get("cantidad_completada") or 0))
            cap = max(0, c - cc)
            if cap <= 0:
                continue
            add = min(cap, rest)
            if add > 0:
                r["cantidad_completada"] = str(cc + add)
                rest -= add
                changed = True
        # si queda 'rest', no hay más capacidad; no se sobrepasa 'cantidad'

    # --- persistir y recalcular estados ---
    if changed:
        _escribir_todas_lineas(after_rows)
        try:
            recalc_estado_pedido(id_origen)
        except:
            pass
        try:
            # refrescar estados reportados
            for p in leer_pedidos():
                if p.get("id_pedido") in (id_pedido, id_origen):
                    estados[p.get("id_pedido")] = p.get("estado","")
        except:
            estados[id_origen] = estados.get(id_origen, "Actualizado")

    return estados

def set_no_factura(id_pedido: str, no_factura: str) -> bool:
    id_pedido = str(id_pedido)
    pedidos = leer_pedidos()
    changed = False
    for p in pedidos:
        if p.get("id_pedido") == id_pedido:
            p["no_factura"] = (no_factura or "").strip()
            changed = True
            break
    if changed:
        _write_pedidos(pedidos)
    return changed
