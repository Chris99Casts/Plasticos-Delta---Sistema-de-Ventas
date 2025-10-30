import tkinter as tk
from tkinter import ttk
from ui.tab_nueva_nota import TabNuevaNota
from ui.tab_pedidos import TabPedidos
from data.csv_manager import ensure_files
from ui.tab_cobranza import TabCobranza
from ui.tab_pendientes import TabPendientes


class NotaVentaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Generador de Notas de Venta")
        self.root.configure(bg="#1e1e1e")

        # Pantalla completa
        self.is_fullscreen = False
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        self.root.attributes('-fullscreen', True)

        # Crea CSVs base
        ensure_files()

        # ===== Estilos (forzamos oscuro, incluido Notebook y Tabs) =====
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except:
            pass

        # Frames / contenedores
        style.configure("Dark.TFrame", background="#1e1e1e")

        # Notebook + Tabs
        style.configure("Dark.TNotebook", background="#1e1e1e", borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background="#2b2b2b",
                        foreground="white",
                        padding=(12, 6))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", "#3a3a3a")],
                  foreground=[("selected", "white")])

        # Controles
        style.configure("Dark.Treeview",
                        background="#252526",
                        fieldbackground="#252526",
                        foreground="white",
                        bordercolor="#2b2b2b")
        style.configure("Dark.Treeview.Heading",
                        background="#2b2b2b",
                        foreground="white")
        style.map("Dark.Treeview.Heading", background=[("active", "#3a3a3a")])

        style.configure("Dark.TLabel", background="#1e1e1e", foreground="white")
        style.configure("Dark.TButton", background="#3c3c3c", foreground="white")
        style.map("Dark.TButton", background=[("active", "#505050")])
        style.configure("Dark.TEntry", fieldbackground="#2d2d2d", foreground="white")
        style.configure("Dark.TCheckbutton", background="#1e1e1e", foreground="white")

        # ===== Notebook con pestañas =====
        notebook = ttk.Notebook(self.root, style="Dark.TNotebook")
        notebook.pack(fill="both", expand=True)

        self.tab_nota = TabNuevaNota(notebook,
                                     frame_style="Dark.TFrame",
                                     label_style="Dark.TLabel",
                                     button_style="Dark.TButton",
                                     entry_style="Dark.TEntry",
                                     check_style="Dark.TCheckbutton",
                                     on_refresh_all=self.refresh_all,
                                     tree_style="Dark.Treeview")
        self.tab_pedidos = TabPedidos(notebook,
                                      frame_style="Dark.TFrame",
                                      on_refresh_all=self.refresh_all,
                                      tree_style="Dark.Treeview")
        notebook.add(self.tab_nota.frame, text="Nueva Nota")
        notebook.add(self.tab_pedidos.frame, text="Pedidos")
        
        self.tab_cobranza = TabCobranza(
            notebook,
            frame_style="Dark.TFrame",
            tree_style="Dark.Treeview",
            button_style="Dark.TButton",
            on_refresh_all=self.refresh_all,
            label_style="Dark.TLabel"
        )
        notebook.add(self.tab_cobranza.frame, text="Cobranza")

        # Pendientes
        self.tab_pend = TabPendientes(notebook)
        notebook.add(self.tab_pend.frame, text="Pendientes")



    # Pantalla completa
    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        try:
            self.root.attributes('-fullscreen', self.is_fullscreen)
        except:
            self.root.state('zoomed')

    def exit_fullscreen(self, event=None):
        try:
            self.root.attributes('-fullscreen', False)
        except:
            pass
        try:
            self.root.state('normal')
        except:
            pass
        self.is_fullscreen = False

    def refresh_all(self):
        """Refresca todas las tabs que expongan .refrescar()."""
        try:
            if hasattr(self.tab_nota, "refrescar"):    # si la tienes
                self.tab_nota.refrescar()
        except Exception:
            pass
        try:
            if hasattr(self.tab_pedidos, "refrescar"):
                self.tab_pedidos.refrescar()
        except Exception:
            pass
        try:
            if hasattr(self.tab_cobranza, "refrescar"):
                self.tab_cobranza.refrescar()
        except Exception:
            pass
        try:
            if hasattr(self.tab_pend, "refrescar"):
                self.tab_pend.refrescar()
        except Exception:
            pass
