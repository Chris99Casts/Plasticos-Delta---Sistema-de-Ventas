import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DATA_DIR = os.path.join(BASE_DIR, "data")

PRODUCTOS_PATH = os.path.join(DATA_DIR, "productos.csv")
PEDIDOS_PATH = os.path.join(DATA_DIR, "pedidos.csv")
PEDIDOS_DETALLE_PATH = os.path.join(DATA_DIR, "pedidos_detalle.csv")   # <--- importante
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")
NOTAS_DIR = os.path.join(BASE_DIR, "Notas")
