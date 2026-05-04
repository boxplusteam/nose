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
PUERTO_HTTP = 80  # Cambia a 8000 si prefieres ese puerto

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
    # Definimos los tipos de archivo correctamente para que los reproductores no den error
    extensions_map = SimpleHTTPRequestHandler.extensions_map.copy()
    extensions_map.update({
        '.m3u8': 'application/x-mpegURL',
        '.ts': 'video/MP2T',
    })

    def end_headers(self):
        # CORS para que funcione en cualquier web player
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type, Origin')
        
        # Lógica de Caché para optimizar el tráfico de red (Estilo Nginx)
        if self.path.endswith(".m3u8"):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        elif self.path.endswith(".ts"):
            self.send_header('Cache-Control', 'public, max-age=3600') # Cachear segmentos de video
            
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
                
                # Si piden el index y no está iniciado el proceso
                if path.endswith("index.m3u8") and cid not in procesos_activos:
                    if datos_actuales_ram and cid in datos_actuales_ram.get("canales", {}):
                        logging.info(f"🚀 Petición On-Demand: {cid}. Iniciando FFmpeg...")
                        proc = lanzar_ffmpeg(cid, datos_actuales_ram["canales"][cid])
                        if proc:
                            procesos_activos[cid] = proc
                            archivo_index = os.path.join(BASE_PATH, cid, "index.m3u8")
                            # Esperar a que FFmpeg genere el primer archivo
                            for _ in range(30):
                                if os.path.exists(archivo_index): break
                                time.sleep(0.5)
        try:
            return super().do_GET()
        except (ConnectionResetError, BrokenPipeError):
            # Ignorar errores comunes cuando un cliente cierra el reproductor rápido
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
        # Desactivar logs de cada petición .ts para no saturar la consola
        pass

def lanzar_ffmpeg(cid, info):
    url = info.get("url")
    if not url: return None
    ruta_hls = os.path.join(BASE_PATH, cid)
    if os.path.exists(ruta_hls): shutil.rmtree(ruta_hls)
    os.makedirs(ruta_hls, exist_ok=True)
    output = os.path.join(ruta_hls, "index.m3u8")

    # Comando optimizado para streaming estable
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", url,
        "-c:v", "copy", "-c:a", "copy",
        "-f", "hls", "-hls_time", "9", "-hls_list_size", "20",
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
    # El uso de ThreadingHTTPServer permite múltiples conexiones simultáneas
    server_address = ("", PUERTO_HTTP)
    httpd = ThreadingHTTPServer(server_address, OnDemandHandler)
    httpd.serve_forever()

def main():
    global datos_actuales_ram, procesos_activos
    threading.Thread(target=servidor_hilo, daemon=True).start()
    logging.info(f"=== GESTOR ACTIVO (SIMULANDO NGINX) - PUERTO {PUERTO_HTTP} ===")

    while True:
        nuevo = escanear_url()
        
        if nuevo and nuevo != datos_actuales_ram:
            logging.info("♻️ Cambio detectado en JSON. Reseteando sistema...")
            for cid in list(procesos_activos.keys()):
                try: procesos_activos[cid].kill()
                except: pass
            
            procesos_activos.clear()
            ultima_actividad.clear()
            datos_actuales_ram = nuevo

        ahora = time.time()
        for cid in list(procesos_activos.keys()):
            # Aumentado a 60 segundos el tiempo de gracia
            if ahora - ultima_actividad.get(cid, 0) > 60:
                logging.info(f"⏹ Inactividad en {cid}. Cerrando.")
                procesos_activos[cid].kill()
                del procesos_activos[cid]
                try: shutil.rmtree(os.path.join(BASE_PATH, cid))
                except: pass
            elif procesos_activos[cid].poll() is not None:
                del procesos_activos[cid]
        
        time.sleep(5)

if __name__ == "__main__":
    main()
