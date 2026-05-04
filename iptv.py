import os
import json
import time
import subprocess
import urllib.request
import logging
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

# --- CONFIGURACIÓN ---
JSON_URL = "https://raw.githubusercontent.com/boxplusteam/nose/refs/heads/main/data.json"
BASE_PATH = r"D:\hls"
PUERTO_HTTP = 80 

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
    extensions_map = SimpleHTTPRequestHandler.extensions_map.copy()
    extensions_map.update({
        '.m3u8': 'application/x-mpegURL',
        '.ts': 'video/MP2T',
    })

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type, Origin')
        
        if self.path.endswith(".m3u8"):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        elif self.path.endswith(".ts"):
            self.send_header('Cache-Control', 'public, max-age=3600')
            
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ["/", "/hls", "/hls/"]:
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
                            # Espera máxima de 15 segundos para no colgar el hilo
                            for _ in range(30):
                                if os.path.exists(archivo_index): break
                                time.sleep(0.5)
        try:
            return super().do_GET()
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logging.error(f"Error sirviendo archivo: {e}")

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
    
    # Limpieza de carpeta previa
    if os.path.exists(ruta_hls):
        try: shutil.rmtree(ruta_hls)
        except: pass
    
    os.makedirs(ruta_hls, exist_ok=True)
    output = os.path.join(ruta_hls, "index.m3u8")

    # COMANDO CORREGIDO Y LIMPIO
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-loglevel", "error",
        "-reconnect", "1", 
        "-reconnect_at_eof", "1", 
        "-reconnect_streamed", "1", 
        "-reconnect_delay_max", "10",
        "-probesize", "15M",           # Aumentado para mayor estabilidad inicial
        "-analyzeduration", "15M", 
        "-i", url,
        "-c:v", "copy", 
        "-c:a", "copy",
        "-f", "hls", 
        "-hls_time", "4", 
        "-hls_list_size", "10", 
        "-hls_flags", "delete_segments+append_list+discont_start",
        "-hls_segment_type", "mpegts",
        output
    ]
    
    try:
        # Esto oculta la ventana de consola si estás en Windows
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0 # Oculto completamente
        return subprocess.Popen(cmd, startupinfo=si)
    except Exception as e:
        logging.error(f"Error lanzando FFmpeg en {cid}: {e}")
        return None

def escanear_url():
    try:
        req = urllib.request.Request(JSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            return json.loads(response.read().decode('utf-8'))
    except: return None

def servidor_hilo():
    server_address = ("", PUERTO_HTTP)
    httpd = ThreadingHTTPServer(server_address, OnDemandHandler)
    httpd.serve_forever()

def main():
    global datos_actuales_ram, procesos_activos
    threading.Thread(target=servidor_hilo, daemon=True).start()
    logging.info(f"=== GESTOR ACTIVO (50MBPS READY) - PUERTO {PUERTO_HTTP} ===")

    while True:
        nuevo = escanear_url()
        
        if nuevo and nuevo != datos_actuales_ram:
            logging.info("♻️ Cambio detectado en JSON. Reseteando...")
            datos_actuales_ram = nuevo

        ahora = time.time()
        for cid in list(procesos_activos.keys()):
            # Tiempo de gracia de 60 segundos antes de apagar el canal
            if ahora - ultima_actividad.get(cid, 0) > 60:
                logging.info(f"⏹ Cerrando {cid} por inactividad.")
                procesos_activos[cid].terminate() # terminate es más suave que kill
                del procesos_activos[cid]
                # Pequeña pausa antes de borrar archivos para evitar errores de acceso
                time.sleep(1)
                try: shutil.rmtree(os.path.join(BASE_PATH, cid))
                except: pass
            elif procesos_activos[cid].poll() is not None:
                logging.warning(f"⚠️ El proceso FFmpeg para {cid} se cerró inesperadamente.")
                del procesos_activos[cid]
        
        time.sleep(5)

if __name__ == "__main__":
    main()
