import os
import json
import threading
import time
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

# --- CONFIGURACIÓN DE RUTAS ---
# Configurado para guardar en el disco D:
BASE_PATH = r"D:\hls"
CONFIG_FILE = os.path.join(BASE_PATH, "config.json")

class HlsManagerPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestor IPTV PRO - V2.0 (Terminales Visibles)")
        self.root.geometry("1150x850")
        
        # Estilo
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self.configurar_estilos()
        
        self.autostart_tiempo = 120
        self.autostart_activo = True
        
        self.config_data = {
            "default_res": "Original",
            "default_bitrate": "Auto",
            "canales": {}
        }

        self.preparar_entorno()
        self.cargar_datos() 
        self.construir_interfaz()
        self.actualizar_tabla()
        self.iniciar_cuenta_atras()

    def configurar_estilos(self):
        bg_color = "#f4f6f9"
        self.root.configure(bg=bg_color)
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("TLabelframe", background=bg_color, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabel", background=bg_color, font=("Segoe UI", 10))
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=5)
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=25)

    def preparar_entorno(self):
        if not os.path.exists(BASE_PATH): 
            try:
                os.makedirs(BASE_PATH)
            except Exception as e:
                print(f"Error creando la ruta {BASE_PATH}. Asegúrate de que el disco D: existe.")
        
        if not os.path.exists(CONFIG_FILE): 
            self.guardar_json()

    def construir_interfaz(self):
        # PANEL SUPERIOR
        frame_top = ttk.Frame(self.root, padding="10")
        frame_top.pack(fill=tk.X)

        g_frame = ttk.LabelFrame(frame_top, text=" Nota sobre configuración ", padding="10")
        g_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(g_frame, text="La transcodificación está desactivada (-c:v copy -c:a copy). Todo se graba en D:\\hls").grid(row=0, column=0, sticky="w")

        # TABLA
        self.tree = ttk.Treeview(self.root, columns=("ID", "Nombre", "Estado"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Nombre", text="Canal")
        self.tree.heading("Estado", text="Estado")
        
        # Ajustar anchos de columna
        self.tree.column("ID", width=150)
        self.tree.column("Nombre", width=400)
        self.tree.column("Estado", width=150)
        
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self.cargar_datos_formulario)

        # BOTONES ACCIÓN
        f_btns = ttk.Frame(self.root, padding="10")
        f_btns.pack(fill=tk.X)
        tk.Button(f_btns, text="? INICIAR", command=self.iniciar_seleccionado, bg="#4caf50", fg="white", width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(f_btns, text="? DETENER", command=self.detener_seleccionado, bg="#f44336", fg="white", width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(f_btns, text="?? INICIAR TODOS", command=self.iniciar_todos_hilo, bg="#2196f3", fg="white").pack(side=tk.RIGHT, padx=5)

        # FORMULARIO
        self.crear_formulario()

    def crear_formulario(self):
        f = ttk.LabelFrame(self.root, text=" Datos del Canal ", padding="15")
        f.pack(fill=tk.X, padx=10, pady=10)
        self.var_id = tk.StringVar()
        self.var_nom = tk.StringVar()
        self.var_url = tk.StringVar()
        
        ttk.Label(f, text="ID (Carpeta):").grid(row=0, column=0)
        ttk.Entry(f, textvariable=self.var_id, width=15).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(f, text="Nombre:").grid(row=0, column=2)
        ttk.Entry(f, textvariable=self.var_nom, width=30).grid(row=0, column=3, sticky="w", padx=5)
        
        ttk.Label(f, text="URL:").grid(row=1, column=0, pady=10)
        ttk.Entry(f, textvariable=self.var_url, width=80).grid(row=1, column=1, columnspan=4, padx=5)
        
        tk.Button(f, text="?? GUARDAR CANAL", command=self.guardar_canal, bg="#ff9800", fg="white").grid(row=2, column=1, pady=5)

    def iniciar_ffmpeg(self, cid):
        canal = self.config_data["canales"].get(cid)
        if not canal: return
        
        ruta_hls = os.path.join(BASE_PATH, cid)
        if not os.path.exists(ruta_hls): 
            os.makedirs(ruta_hls)
            
        # Para evitar problemas con las barras invertidas en Windows dentro del comando FFmpeg
        output = os.path.join(ruta_hls, "index.m3u8").replace("\\", "/")

        # Comando exacto suministrado, con copia directa y todos los parámetros de reconexión
        cmd = (
            f'ffmpeg -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
            f'-i "{canal["url"]}" '
            f'-c:v copy -c:a copy '
            f'-f hls -hls_time 15 -hls_list_size 25 '
            f'-hls_flags delete_segments+append_list+discont_start '
            f'"{output}"'
        )
        
        # Ejecutamos abriendo una terminal VISIBLE usando 'start' y asignando el 'cid' como título
        # para que luego el comando taskkill pueda encontrar la ventana por su título y cerrarla.
        subprocess.Popen(f'start "{cid}" {cmd}', shell=True)
        self.tree.set(cid, "Estado", "? EN CURSO")

    def guardar_canal(self):
        cid = self.var_id.get().strip()
        if not cid: 
            messagebox.showwarning("Aviso", "El ID no puede estar vacío")
            return
            
        self.config_data["canales"][cid] = {
            "nombre": self.var_nom.get(), 
            "url": self.var_url.get()
        }
        self.guardar_json()
        self.actualizar_tabla()
        messagebox.showinfo("OK", "Canal Guardado correctamente en D:\\hls")

    def actualizar_tabla(self):
        self.tree.delete(*self.tree.get_children())
        for cid, d in self.config_data["canales"].items():
            self.tree.insert("", tk.END, iid=cid, values=(cid, d['nombre'], "? Detenido"))

    def iniciar_seleccionado(self):
        sel = self.tree.selection()
        if sel: 
            self.iniciar_ffmpeg(sel[0])
        else:
            messagebox.showinfo("Aviso", "Selecciona un canal de la lista primero.")

    def detener_seleccionado(self):
        sel = self.tree.selection()
        if sel:
            cid = sel[0]
            # Mata el proceso basándose en el título de la ventana que le asignamos en el comando 'start'
            os.system(f'taskkill /fi "windowtitle eq {cid}*" /f >nul 2>&1')
            # También matamos posibles procesos de ffmpeg huérfanos que estén escribiendo en esa ruta
            # (Opcional, pero previene archivos bloqueados)
            self.tree.set(cid, "Estado", "? Detenido")

    def iniciar_todos_hilo(self):
        self.autostart_activo = False
        def tarea():
            for cid in self.config_data["canales"]:
                self.iniciar_ffmpeg(cid)
                time.sleep(2) # Pausa reducida a 2 seg para iniciar terminales rápido
        threading.Thread(target=tarea, daemon=True).start()

    def cargar_datos(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: 
                    self.config_data.update(json.load(f))
            except json.JSONDecodeError:
                pass # Si el archivo está corrupto, usa configuración por defecto

    def guardar_json(self):
        with open(CONFIG_FILE, 'w') as f: 
            json.dump(self.config_data, f, indent=4)

    def iniciar_cuenta_atras(self):
        if self.autostart_activo and self.autostart_tiempo > 0:
            self.autostart_tiempo -= 1
            self.root.after(1000, self.iniciar_cuenta_atras)
        elif self.autostart_activo: 
            self.iniciar_todos_hilo()

    def cargar_datos_formulario(self, event):
        sel = self.tree.selection()
        if not sel: return
        cid = sel[0]
        c = self.config_data["canales"][cid]
        self.var_id.set(cid)
        self.var_nom.set(c['nombre'])
        self.var_url.set(c['url'])

if __name__ == "__main__":
    # Asegúrate de que ffmpeg está en las variables de entorno (PATH) de Windows.
    root = tk.Tk()
    app = HlsManagerPro(root)
    root.mainloop()
