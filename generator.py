import tkinter as tk
from tkinter import ttk, messagebox
import json
import re

class GeneradorNewEra:
    def __init__(self, root):
        self.root = root
        self.root.title("Generador NEW ERA II - JSON & M3U8")
        self.root.geometry("850x700")

        # --- Variable para el túnel ---
        self.url_cloudflare = tk.StringVar(value="https://allergy-letter-chance-inquiry.trycloudflare.com")

        # --- Interfaz ---
        frame_top = ttk.LabelFrame(root, text=" 1. Configuración de Túnel Cloudflare ", padding=10)
        frame_top.pack(fill="x", padx=20, pady=10)
        
        ttk.Label(frame_top, text="URL Cloudflare:").pack(side="left")
        ttk.Entry(frame_top, textvariable=self.url_cloudflare, width=60).pack(side="left", padx=10)

        frame_mid = ttk.LabelFrame(root, text=" 2. Pega aquí el contenido de tu M3U (AceStream) ", padding=10)
        frame_mid.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.txt_input = tk.Text(frame_mid, font=("Consolas", 10), undo=True)
        self.txt_input.pack(fill="both", expand=True)

        frame_bot = ttk.Frame(root, padding=10)
        frame_bot.pack(fill="x", padx=20)

        ttk.Button(frame_bot, text="LIMPIAR TEXTO", command=self.limpiar).pack(side="left", padx=5)
        ttk.Button(frame_bot, text="GENERAR ARCHIVOS YA", command=self.procesar).pack(side="right", padx=5)

    def limpiar(self):
        self.txt_input.delete("1.0", tk.END)

    def procesar(self):
        contenido = self.txt_input.get("1.0", tk.END).strip()
        base_cloud = self.url_cloudflare.get().rstrip('/')

        if not contenido:
            messagebox.showerror("Error", "Pega el contenido M3U primero.")
            return

        # Regex profesional para extraer logo, nombre e ID de Acestrem
        # Soporta formatos con o sin tvg-id/tvg-name
        patron = re.compile(r'#EXTINF:.*tvg-logo="(.*?)".*?,(.*?)\n(?:acestream://)([\w\d]+)', re.MULTILINE)
        bloques = patron.findall(contenido)

        if not bloques:
            messagebox.showwarning("Atención", "No se detectaron bloques válidos. Asegúrate de que incluyan tvg-logo y la línea acestream://")
            return

        canales_json = {}
        lineas_m3u = ["#EXTM3U\n"]

        for i, (logo, nombre, ace_id) in enumerate(bloques, start=1):
            id_canal = f"canal_{i}"
            nombre_limpio = nombre.strip()
            
            # --- GENERACIÓN JSON (Local AceStream) ---
            canales_json[id_canal] = {
                "nombre": nombre_limpio,
                "url": f"http://127.0.0.1:6878/ace/getstream?id={ace_id}"
            }

            # --- GENERACIÓN M3U8 (Túnel Cloudflare) ---
            # Usamos el id_canal (canal_1, canal_2...) para la ruta del HLS
            url_hls = f"{base_cloud}/hls/{id_canal}/index.m3u8"
            
            linea_inf = f'#EXTINF:-1 tvg-id="" tvg-name="{id_canal}" tvg-logo="{logo}" group-title="Deporte" , {nombre_limpio}\n'
            lineas_m3u.append(linea_inf)
            lineas_m3u.append(f"{url_hls}\n")

        # --- GUARDAR ARCHIVOS ---
        try:
            # Guardar JSON
            with open("canales.json", "w", encoding="utf-8") as fj:
                json.dump(canales_json, fj, indent=2, ensure_ascii=False)
            
            # Guardar M3U8
            with open("lista_hls.m3u8", "w", encoding="utf-8") as fm:
                fm.writelines(lineas_m3u)

            messagebox.showinfo("Proceso Completado", f"Se han generado {len(bloques)} canales con éxito.\n\nArchivos creados:\n- canales.json\n- lista_hls.m3u8")
        except Exception as e:
            messagebox.showerror("Error Crítico", f"No se pudieron guardar los archivos: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GeneradorNewEra(root)
    root.mainloop()
