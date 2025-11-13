import os
import sys

if getattr(sys, "frozen", False):
    # Cuando corre como .exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Cuando corre como script normal
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DATA_DIR = os.path.join(BASE_DIR, "data")

PRODUCTOS_PATH = os.path.join(DATA_DIR, "productos.csv")
PEDIDOS_PATH = os.path.join(DATA_DIR, "pedidos.csv")
PEDIDOS_DETALLE_PATH = os.path.join(DATA_DIR, "pedidos_detalle.csv")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")
NOTAS_DIR = os.path.join(BASE_DIR, "Notas")
CLIENTES_PATH = os.path.join(DATA_DIR, "clientes.csv")
PEDIDOS_PAGOS_PATH = os.path.join(DATA_DIR, "pedidos_pagos.csv")
