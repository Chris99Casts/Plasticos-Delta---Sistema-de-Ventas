import tkinter as tk
from tkinter import ttk
from ui.tab_nueva_nota import TabNuevaNota
from ui.tab_pedidos import TabPedidos
from data.csv_manager import ensure_files
from ui.tab_cobranza import TabCobranza
from ui.tab_control_entregas import TabControlEntregas 
from ui.tab_captura_rapida import TabCapturaRapida
import tkinter.font as tkfont 
import json, os, subprocess, platform, shutil


class NotaVentaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Generador de Notas de Venta")
        self.root.configure(bg="#1e1e1e")

        # Pantalla completa / maximizado (manteniendo la barra de título)
        self.is_fullscreen = False
        self._prev_geometry = None  # para recordar tamaño anterior
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

        # Arrancar maximizada, pero con barra de título y botones
        try:
            self.root.state('zoomed')
        except tk.TclError:
            # En sistemas donde 'zoomed' no existe, simplemente ignora
            pass


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
        # ---- Persistencia de zoom ----
        self._settings_file = os.path.join(os.path.expanduser("~"), ".plastics_delta_settings.json")

        def _load_zoom():
            try:
                with open(self._settings_file, "r", encoding="utf-8") as f:
                    return float(json.load(f).get("ui_scale", 1.0))
            except Exception:
                return 1.0

        def _save_zoom():
            try:
                data = {"ui_scale": self.ui_scale}
                with open(self._settings_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass

        self._load_zoom = _load_zoom
        self._save_zoom = _save_zoom        

        # ===== Escalado UI (Zoom con teclado) =====
        self.ui_scale = self._load_zoom()
        self._base_fonts = {}
        self._style = style  # guarda referencia al Style

        # toma snapshots de tamaños base de fuentes de Tk
        for fname in ("TkDefaultFont","TkTextFont","TkFixedFont","TkMenuFont",
                    "TkHeadingFont","TkIconFont","TkTooltipFont"):
            try:
                f = tkfont.nametofont(fname)
                self._base_fonts[fname] = f.cget("size")
            except tk.TclError:
                pass

        def _apply_scale():
            # 1) fuentes
            for fname, base in self._base_fonts.items():
                try:
                    f = tkfont.nametofont(fname)
                    f.configure(size=max(8, int(round(base * self.ui_scale))))
                except tk.TclError:
                    pass

            # 2) métricas de Treeview, Tabs, etc.
            row_h = max(20, int(round(24 * self.ui_scale)))
            tab_pad_y = max(4, int(round(6 * self.ui_scale)))
            tab_pad_x = max(8, int(round(12 * self.ui_scale)))

            # estilos “Dark”
            self._style.configure("Dark.Treeview", rowheight=row_h)
            self._style.configure("Dark.TNotebook.Tab", padding=(tab_pad_x, tab_pad_y))

            # estilos “Pend” (los define TabPendientes)
            try:
                self._style.configure("Pend.Treeview", rowheight=row_h)
                self._style.configure("Pend.TNotebook.Tab", padding=(tab_pad_x, tab_pad_y))
            except tk.TclError:
                pass

            # 3) scaling de Tk (afecta algunos widgets nativos)
            try:
                self.root.tk.call("tk", "scaling", self.ui_scale)
            except tk.TclError:
                pass

            # 4) refrescar layout
            self.root.update_idletasks()

        self._apply_scale = _apply_scale  # guarda como método
        self._apply_scale()


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
        
        self.tab_rapida = TabCapturaRapida(
            notebook,
            frame_style="Dark.TFrame",
            label_style="Dark.TLabel",
            button_style="Dark.TButton",
            entry_style="Dark.TEntry",
            tree_style="Dark.Treeview",
            on_refresh_all=self.refresh_all,
        )
        notebook.add(self.tab_rapida.frame, text="Quick Capture")

        self.tab_pedidos = TabPedidos(notebook,
                                      frame_style="Dark.TFrame",
                                      on_refresh_all=self.refresh_all,
                                      tree_style="Dark.Treeview")
        notebook.add(self.tab_nota.frame, text="Nueva Nota")
        notebook.add(self.tab_pedidos.frame, text="Pedidos")

        self.tab_ctrl_ent = TabControlEntregas(
            notebook,
            frame_style="Dark.TFrame",
            tree_style="Dark.Treeview",
            button_style="Dark.TButton",
            label_style="Dark.TLabel",
            on_refresh_all=self.refresh_all
        )
        notebook.add(self.tab_ctrl_ent.frame, text="Control de entregas")
        
        self.tab_cobranza = TabCobranza(
            notebook,
            frame_style="Dark.TFrame",
            tree_style="Dark.Treeview",
            button_style="Dark.TButton",
            on_refresh_all=self.refresh_all,
            label_style="Dark.TLabel"
        )
        notebook.add(self.tab_cobranza.frame, text="Cobranza")

        



        # Zoom: Ctrl + / Ctrl - / Ctrl 0
        def _zoom(delta):
            self.ui_scale = max(0.7, min(1.8, round((self.ui_scale + delta), 2)))
            self._apply_scale()
            self._save_zoom()

        def _reset_zoom(_=None):
            self.ui_scale = 1.0
            self._apply_scale()
            self._save_zoom()

        # Windows: Ctrl-plus también llega como Control-equal; Ctrl-minus / Ctrl-underscore
        self.root.bind_all("<Control-plus>",   lambda e: _zoom(+0.10))
        self.root.bind_all("<Control-equal>",  lambda e: _zoom(+0.10))
        self.root.bind_all("<Control-minus>",  lambda e: _zoom(-0.10))
        self.root.bind_all("<Control-underscore>", lambda e: _zoom(-0.10))
        self.root.bind_all("<Control-0>", _reset_zoom)
        
        # Soporte para teclado táctil en Surface / Windows
        self._setup_touch_keyboard_support()


        self._setup_touch_keyboard_support()




    def toggle_fullscreen(self, event=None):
        """
        F11: alterna entre ventana normal y maximizada,
        pero siempre con barra de título y botones.
        """
        if not self.is_fullscreen:
            # Activar "fullscreen" = maximizar
            self.is_fullscreen = True
            try:
                # Guarda tamaño/posición actual para restaurar después
                self._prev_geometry = self.root.geometry()
            except Exception:
                self._prev_geometry = None

            # Asegúrate de NO estar en modo -fullscreen
            try:
                self.root.attributes('-fullscreen', False)
            except Exception:
                pass

            # Maximizar ventana (con barra de título)
            try:
                self.root.state('zoomed')
            except Exception:
                pass
        else:
            # Si ya está en "fullscreen", salimos
            self.exit_fullscreen()

    def exit_fullscreen(self, event=None):
        """ESC: vuelve a la ventana normal."""
        self.is_fullscreen = False
        try:
            self.root.attributes('-fullscreen', False)
        except Exception:
            pass

        try:
            self.root.state('normal')
        except Exception:
            pass

        # Restaura la geometría anterior si la tenemos
        try:
            if getattr(self, "_prev_geometry", None):
                self.root.geometry(self._prev_geometry)
        except Exception:
            pass


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
        
        try:
            self._apply_scale()
        except Exception:
            pass
        try:
            self._apply_scale()
        except Exception:
            pass
        try: 
            self.tab_ctrl.refrescar()      # <<--- IMPORTANTE: incluir Control de Entregas
        except:
            pass
        
        try:
            if hasattr(self.tab_rapida, "refrescar"):
                self.tab_rapida.refrescar()
        except Exception:
            pass
    
    def _setup_touch_keyboard_support(self):
        """
        En Surface / Windows lanza el teclado táctil cuando
        una caja de texto o combobox recibe el foco.
        """
        if platform.system() != "Windows":
            return  # sólo aplica en Windows

        # Función interna para lanzar el teclado
        def _launch_tabtip(event=None):
            # Rutas típicas del teclado táctil / OSK
            candidates = [
                r"C:\Program Files\Common Files\microsoft shared\ink\TabTip.exe",
                r"C:\Program Files (x86)\Common Files\microsoft shared\ink\TabTip.exe",
                r"C:\Windows\System32\osk.exe",
            ]
            for p in candidates:
                if os.path.exists(p):
                    try:
                        subprocess.Popen(p)
                        break
                    except Exception:
                        continue

        # Guardamos referencia para que no la limpie el GC
        self._launch_tabtip = _launch_tabtip

        # Vinculamos para todos los Entry / Combobox / Text
        for cls in ("Entry", "TEntry", "TCombobox", "Text"):
            try:
                self.root.bind_class(cls, "<FocusIn>", self._launch_tabtip, add="+")
            except tk.TclError:
                pass

    def _launch_touch_keyboard(self, event=None):
        """
        Intenta abrir el teclado táctil moderno (TabTip) en Windows Surface.
        No usa el teclado clásico 'osk.exe'.
        """
        if platform.system() != "Windows":
            return

        # Posibles rutas de TabTip.exe
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\\Program Files"),
                         "Common Files", "microsoft shared", "ink", "TabTip.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)"),
                         "Common Files", "microsoft shared", "ink", "TabTip.exe"),
        ]

        exe = None
        for p in candidates:
            if os.path.exists(p):
                exe = p
                break

        if exe is None:
            # Intento extra: buscar en PATH
            exe = shutil.which("TabTip.exe") or shutil.which("tabtip.exe")

        if exe:
            try:
                # os.startfile suele lanzar mejor apps modernas (ShellExecute)
                os.startfile(exe)
            except OSError:
                try:
                    subprocess.Popen(
                        [exe],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception:
                    # Si falla, evitamos que truene la app
                    pass

    def _setup_touch_keyboard_support(self):
        """
        Crea un botón 'Teclado' y enlaza los campos de texto para que intenten
        abrir el teclado táctil moderno de Windows (TabTip) en Surface.
        """
        if platform.system() != "Windows":
            return

        # 1) Botón flotante en la esquina superior derecha
        try:
            kb_btn = tk.Button(
                self.root,
                text="Teclado",
                command=self._launch_touch_keyboard,
                bg="#333333",
                fg="white",
                relief="flat",
                padx=8,
                pady=2
            )
            kb_btn.place(relx=1.0, x=-10, y=10, anchor="ne")
            self._kb_btn = kb_btn
        except Exception:
            pass

        # 2) Al tocar entradas/combos, intenta abrir TabTip
        for cls in ("Entry", "TEntry", "TCombobox", "Text"):
            try:
                self.root.bind_class(
                    cls, "<Button-1>",
                    self._launch_touch_keyboard,
                    add="+"
                )
                self.root.bind_class(
                    cls, "<FocusIn>",
                    self._launch_touch_keyboard,
                    add="+"
                )
            except tk.TclError:
                pass





    


