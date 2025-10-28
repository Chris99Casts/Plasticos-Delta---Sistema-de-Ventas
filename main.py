import tkinter as tk
from ui.app import NotaVentaApp

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x600+100+100")
    app = NotaVentaApp(root)
    root.mainloop()

## Este es el archivo principal para ejecutar la App de Nota de Venta.
