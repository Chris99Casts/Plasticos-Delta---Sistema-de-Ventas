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
]
DETALLE_FIELDS = ["id_linea","id_pedido","producto","cantidad","cantidad_completada","precio_unitario","importe"]

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

# ---------------- helpers de IO ----------------
def _leer_todas_lineas():
    if not os.path.exists(PEDIDOS_DETALLE_PATH): ensure_files()
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
def _escribir_todas_lineas(rows):
    with open(PEDIDOS_DETALLE_PATH,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=DETALLE_FIELDS); w.writeheader(); w.writerows(rows)
def _write_pedidos(rows):
    with open(PEDIDOS_PATH,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=PEDIDOS_FIELDS); w.writeheader(); w.writerows(rows)

# ---------------- CRUD de pedidos ----------------
def registrar_pedido(header: dict, items: list[dict]):
    desc = str(header.get("descuento","0")).strip()
    header_out = {
        "id_pedido":header["id_pedido"], "fecha":header["fecha"], "cliente":header["cliente"],
        "total":header["total"], "estado":header["estado"],
        "descuento":"1" if desc in ("1","true","True","si","sí") else "0",
        "pagado":"0", "descuento_pago_pct":"", "total_cobro":"",
    }
    file_exists = os.path.exists(PEDIDOS_PATH) and os.path.getsize(PEDIDOS_PATH)>0
    with open(PEDIDOS_PATH,"a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=PEDIDOS_FIELDS); 
        if not file_exists: w.writeheader()
        w.writerow(header_out)

    file_exists = os.path.exists(PEDIDOS_DETALLE_PATH) and os.path.getsize(PEDIDOS_DETALLE_PATH)>0
    with open(PEDIDOS_DETALLE_PATH,"a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=DETALLE_FIELDS)
        if not file_exists: w.writeheader()
        for i,it in enumerate(items, start=1):
            id_linea = it.get("id_linea") or f"{header['id_pedido']}-{i}"
            cantidad = int(it.get("cantidad",0))
            punit = _to_std_number(it.get("precio_unitario","0"))
            importe = _to_std_number(it.get("importe","0"))
            w.writerow({"id_linea":id_linea,"id_pedido":header["id_pedido"],"producto":it.get("producto",""),
                        "cantidad":cantidad,"cantidad_completada":0,"precio_unitario":punit,"importe":importe})

def leer_pedidos():
    if not os.path.exists(PEDIDOS_PATH): ensure_files()
    with open(PEDIDOS_PATH, newline="", encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    norm=[]
    for r in rows:
        rr={ (k or "").strip():(v or "").strip() for k,v in r.items() }
        rr.setdefault("descuento","0"); rr.setdefault("pagado","0")
        rr.setdefault("descuento_pago_pct",""); rr.setdefault("total_cobro",""); rr.setdefault("estado","Pendiente")
        norm.append(rr)
    return norm

def leer_items_por_pedido(id_pedido: str):
    id_pedido=str(id_pedido)
    if not os.path.exists(PEDIDOS_DETALLE_PATH): ensure_files()
    with open(PEDIDOS_DETALLE_PATH, newline="", encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    fixed=[]
    for r in rows:
        if r.get("id_pedido")!=id_pedido: continue
        cantidad=int((r.get("cantidad") or "0").strip() or 0)
        cant_comp=int((r.get("cantidad_completada") or "0").strip() or 0)
        fixed.append({"id_linea":r.get("id_linea") or f"{id_pedido}-X","id_pedido":id_pedido,"producto":r.get("producto",""),
                      "cantidad":cantidad,"cantidad_completada":cant_comp,"precio_unitario":r.get("precio_unitario",""),
                      "importe":r.get("importe","")})
    return fixed

def actualizar_cantidad_completada(id_linea: str, nueva_cantidad: int):
    rows=_leer_todas_lineas(); actualizado=False
    for r in rows:
        if str(r.get("id_linea"))==str(id_linea):
            cantidad=int((r.get("cantidad") or 0))
            r["cantidad_completada"]=str(max(0, min(int(nueva_cantidad), cantidad)))
            actualizado=True; pid=r["id_pedido"]; break
    if actualizado: _escribir_todas_lineas(rows); recalc_estado_pedido(pid)
    return actualizado

def recalc_estado_pedido(id_pedido: str):
    id_pedido=str(id_pedido); pedidos=leer_pedidos(); estado_actual=None
    for p in pedidos:
        if p["id_pedido"]==id_pedido: estado_actual=p.get("estado",""); break
    if estado_actual and estado_actual.lower()=="cancelado": return
    items=leer_items_por_pedido(id_pedido); 
    if not items: return
    all_zero=all(int(i["cantidad_completada"])==0 for i in items)
    all_full=all(int(i["cantidad_completada"])>=int(i["cantidad"]) for i in items)
    estado="Completado" if all_full else ("Pendiente" if all_zero else "Parcial")
    for p in pedidos:
        if p["id_pedido"]==id_pedido: p["estado"]=estado
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
                      "descuento_pago_pct":p.get("descuento_pago_pct",""),"total_cobro":p.get("total_cobro","")})
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

# -------- Cobranza (compatibilidad manual) --------
def marcar_pagado(id_pedido: str, descuento_pct: float = 0.0):
    id_pedido=str(id_pedido); pedidos=leer_pedidos(); ok=False; total_cobro_val=0.0
    for p in pedidos:
        if p.get("id_pedido")==id_pedido:
            try: total=float(_to_std_number(p.get("total","0")))
            except: total=0.0
            pct=max(0.0, min(100.0, float(descuento_pct or 0.0)))
            total_cobro_val=max(0.0, total*(1.0-pct/100.0))
            p["pagado"]="1"; p["descuento_pago_pct"]=f"{pct:.2f}"; p["total_cobro"]=f"{total_cobro_val:.2f}"; ok=True; break
    if ok: _write_pedidos(pedidos)
    return ok, total_cobro_val

def deshacer_pago(id_pedido: str):
    id_pedido=str(id_pedido); pedidos=leer_pedidos(); ok=False
    for p in pedidos:
        if p.get("id_pedido")==id_pedido:
            p["pagado"]="0"; p["descuento_pago_pct"]=""; p["total_cobro"]=""; ok=True; break
    if ok: _write_pedidos(pedidos)
    return ok

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

# -------- Abonos + Pronto-pago --------
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

# ----- Parser robusto de fechas -----
_FECHA_FORMATOS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
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

def _dias_desde(fecha_str: str) -> int:
    dt = _parse_fecha_multi(fecha_str)
    if dt is None:
        return 9999
    delta = (datetime.now() - dt).days
    return delta if delta >= 0 else 9999

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

def total_cobro_actual(id_pedido: str) -> tuple[float, float, int]:
    """
    Devuelve (objetivo_actual, pct_pronto_pago_aplicado_hoy, dias_transcurridos).
    Regla:
      - Si hay 'total_cobro' y el pedido está pagado o tiene abonos => respetar fijo.
      - En otro caso => calcular dinámico: 10% si 0<=días<=7 y NO preferencial; si no, 0%.
    """
    id_pedido=str(id_pedido); pedidos=leer_pedidos()
    for p in pedidos:
        if p.get("id_pedido")!=id_pedido: continue
        try: total_pedido=float(_to_std_number(p.get("total","0")) or "0")
        except: total_pedido=0.0

        # Datos actuales
        dias=_dias_desde(p.get("fecha",""))
        abonados = total_abonado(id_pedido)

        # ¿Existe un total_cobro 'fijo'?
        try: fijo=float(_to_std_number(p.get("total_cobro") or "0") or 0)
        except: fijo=0.0
        try: pct_fijo=float(_to_std_number(p.get("descuento_pago_pct") or "0") or 0.0)
        except: pct_fijo=0.0

        # Respetar fijo SOLO si ya hubo acción real (pagado o hay abonos)
        if fijo > 0 and (p.get("pagado","0") == "1" or abonados > 0):
            return fijo, pct_fijo, dias

        # Cálculo "hoy" (dinámico)
        es_pref=(p.get("descuento","0")=="1")
        pronto=0.0
        if (not es_pref) and (0 <= dias <= 7):
            pronto=10.0
        objetivo = total_pedido*(1.0-pronto/100.0)
        return objetivo, pronto, dias
    return 0.0, 0.0, 9999

def registrar_abono(id_pedido: str, monto: float):
    """
    Valida:
      - monto > 0
      - monto <= saldo actual (objetivo actual - abonado)
    Si liquida: fija pronto-pago (10% <=7d, no preferencial), total_cobro y 'pagado'.
    """
    id_pedido=str(id_pedido)
    try: monto=float(monto or 0.0)
    except: monto=-1.0
    if monto<=0.0:
        raise ValueError("El monto debe ser mayor a 0.")

    # Saldo actual protegido
    objetivo_actual, _, _ = total_cobro_actual(id_pedido)
    abonado = total_abonado(id_pedido)
    saldo = max(0.0, objetivo_actual - abonado)
    if saldo <= 0.0:
        raise ValueError("Este pedido ya no tiene saldo por cubrir.")
    if monto > saldo + 1e-9:
        raise ValueError(f"El abono excede el saldo actual (${saldo:.2f}).")

    # 1) Guardar renglón de pago
    with open(PEDIDOS_PAGOS_PATH,"a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["id_pago","id_pedido","fecha","monto"])
        if f.tell()==0: w.writeheader()
        pid=f"{id_pedido}-P{int(datetime.now().timestamp())}"
        w.writerow({"id_pago":pid,"id_pedido":id_pedido,"fecha":datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "monto":f"{monto:.2f}"})

    # 2) Recalcular encabezado y pronto-pago al liquidar por primera vez
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
            es_pref=(p.get("descuento","0")=="1"); dias=_dias_desde(p.get("fecha","")); pronto=0.0
            if (not es_pref) and (0 <= dias <= 7): pronto=10.0
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
