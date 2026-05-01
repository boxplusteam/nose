import os
import json
import time
import subprocess
import urllib.request
import logging
import shutil
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import ThreadingTCPServer

# --- CONFIGURACIÓN ---
JSON_URL = "https://raw.githubusercontent.com/boxplusteam/nose/refs/heads/main/data.json"
BASE_PATH = r"D:\hls"
PUERTO_HTTP = 8080 

if not os.path.exists(BASE_PATH):
    os.makedirs(BASE_PATH, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_PATH, "gestor.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

procesos_activos = {}
datos_actuales_ram = None 
ultima_actividad = {}

class OnDemandHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/hls" or path == "/hls/":
            self.send_error(403, "Acceso denegado")
            return

        if path.startswith("/hls/"):
            partes = [p for p in path.split("/") if p]
            if len(partes) >= 2:
                cid = partes[1]
                ultima_actividad[cid] = time.time()
                
                if path.endswith("index.m3u8") and cid not in procesos_activos:
                    if datos_actuales_ram and cid in datos_actuales_ram.get("canales", {}):
                        logging.info(f"🚀 Petición On-Demand: {cid}. Iniciando FFmpeg...")
                        proc = lanzar_ffmpeg(cid, datos_actuales_ram["canales"][cid])
                        if proc:
                            procesos_activos[cid] = proc
                            archivo_index = os.path.join(BASE_PATH, cid, "index.m3u8")
                            for _ in range(30):
                                if os.path.exists(archivo_index): break
                                time.sleep(0.5)
        try:
            return super().do_GET()
        except Exception:
            pass

    def translate_path(self, path):
        path = path.split("?")[0]
        if path.startswith("/hls/"):
            rel_path = path[5:] 
            return os.path.join(BASE_PATH, rel_path.replace("/", os.sep))
        return ""

    def log_message(self, format, *args):
        pass

def lanzar_ffmpeg(cid, info):
    url = info.get("url")
    if not url: return None
    ruta_hls = os.path.join(BASE_PATH, cid)
    if os.path.exists(ruta_hls): shutil.rmtree(ruta_hls)
    os.makedirs(ruta_hls, exist_ok=True)
    output = os.path.join(ruta_hls, "index.m3u8")

    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", url,
        "-c:v", "copy", "-c:a", "copy",
        "-f", "hls", "-hls_time", "4", "-hls_list_size", "6",
        "-hls_flags", "delete_segments+append_list+discont_start",
        output
    ]
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7 
        return subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si)
    except Exception as e:
        logging.error(f"Error en {cid}: {e}")
        return None

def escanear_url():
    try:
        req = urllib.request.Request(JSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            return json.loads(response.read().decode('utf-8'))
    except: return None

def servidor_hilo():
    ThreadingTCPServer.allow_reuse_address = True
    with ThreadingTCPServer(("", PUERTO_HTTP), OnDemandHandler) as httpd:
        httpd.serve_forever()

def main():
    global datos_actuales_ram, procesos_activos
    threading.Thread(target=servidor_hilo, daemon=True).start()
    logging.info(f"=== GESTOR ACTIVO - REVISIÓN CADA 5s ===")

    while True:
        nuevo = escanear_url()
        
        # SI HAY CAMBIOS EN EL JSON (más canales, menos canales o cambios de URL)
        if nuevo and nuevo != datos_actuales_ram:
            logging.info("♻️ Cambio detectado en JSON. Reseteando sistema...")
            
            # PARAR TODO
            for cid in list(procesos_activos.keys()):
                try:
                    procesos_activos[cid].kill()
                except:
                    pass
            
            procesos_activos.clear()
            ultima_actividad.clear()
            datos_actuales_ram = nuevo
            logging.info("Nuevo JSON cargado. Esperando peticiones...")

        # Control de inactividad normal (5s)
        ahora = time.time()
        for cid in list(procesos_activos.keys()):
            if ahora - ultima_actividad.get(cid, 0) > 60:
                logging.info(f"⏹ Inactividad en {cid}. Cerrando.")
                procesos_activos[cid].kill()
                del procesos_activos[cid]
                try: shutil.rmtree(os.path.join(BASE_PATH, cid))
                except: pass
            elif procesos_activos[cid].poll() is not None:
                del procesos_activos[cid]
        
        # REVISAR CADA 5 SEGUNDOS
        time.sleep(5)

if __name__ == "__main__":
    main()