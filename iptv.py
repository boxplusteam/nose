import os
import json
import time
import subprocess
import urllib.request
import logging
import shutil

# --- CONFIGURACIÓN ESTRICTA ---
JSON_URL = "https://raw.githubusercontent.com/boxplusteam/nose/refs/heads/main/data.json"
BASE_PATH = r"D:\hls"

# Preparación del entorno de trabajo
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

# Estado en memoria (Zero-Disk-JSON)
procesos_activos = {}
datos_actuales_ram = None 

def matar_todo_y_limpiar():
    """Fuerza el cierre de FFmpeg y limpia el directorio de trabajo."""
    global procesos_activos
    logging.info("!!! CAMBIO DETECTADO: Forzando reinicio total !!!")
    
    # 1. Matar procesos registrados
    for cid, proc in procesos_activos.items():
        try:
            proc.kill() 
        except:
            pass
    procesos_activos.clear()
    
    # 2. Comando de choque para asegurar que no queden huérfanos
    os.system("taskkill /IM ffmpeg.exe /F >nul 2>&1")
    time.sleep(2) # Pausa para liberación de archivos por parte de Windows

    # 3. Limpiar carpetas de segmentos
    for elemento in os.listdir(BASE_PATH):
        ruta = os.path.join(BASE_PATH, elemento)
        if os.path.isdir(ruta):
            try:
                shutil.rmtree(ruta)
            except Exception as e:
                logging.error(f"Error limpiando carpeta {elemento}: {e}")

def escanear_url():
    """Descarga el contenido del JSON directamente a la RAM."""
    try:
        req = urllib.request.Request(JSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logging.error(f"Error escaneando la URL: {e}")
        return None

def lanzar_ffmpeg(cid, info):
    """Inicia FFmpeg con los parámetros técnicos requeridos."""
    url = info.get("url")
    if not url: return None

    ruta_hls = os.path.join(BASE_PATH, cid)
    os.makedirs(ruta_hls, exist_ok=True)
    output = os.path.join(ruta_hls, "index.m3u8")

    # Parámetros aplicados exactamente según tu solicitud
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", url,
        "-c:v", "copy", "-c:a", "copy",
        "-f", "hls", "-hls_time", "6", "-hls_list_size", "30",
        "-hls_flags", "delete_segments+append_list+discont_start",
        output
    ]

    try:
        # Ejecución en consola independiente y minimizada
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7 

        return subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            startupinfo=si
        )
    except Exception as e:
        logging.error(f"Error al iniciar canal {cid}: {e}")
        return None

def main():
    global datos_actuales_ram, procesos_activos
    
    # Verificación de integridad inicial
    if not shutil.which("ffmpeg"):
        logging.critical("FFmpeg no encontrado en el sistema.")
        return

    logging.info("=== GESTOR EN MEMORIA ACTIVO (60s) ===")

    while True:
        nuevo_contenido = escanear_url()
        
        if nuevo_contenido:
            # Compara el objeto JSON en RAM para detectar cambios
            if nuevo_contenido != datos_actuales_ram:
                matar_todo_y_limpiar()
                datos_actuales_ram = nuevo_contenido
                
                canales = nuevo_contenido.get("canales", {})
                for cid, info in canales.items():
                    proc = lanzar_ffmpeg(cid, info)
                    if proc:
                        procesos_activos[cid] = proc
                        logging.info(f"Canal iniciado: {cid}")
            else:
                # Si no hay cambios, solo verifica que los canales no se hayan caído
                canales = datos_actuales_ram.get("canales", {})
                for cid, proc in list(procesos_activos.items()):
                    if proc.poll() is not None:
                        logging.warning(f"Re-lanzando canal caído: {cid}")
                        procesos_activos[cid] = lanzar_ffmpeg(cid, canales.get(cid))
        
        time.sleep(60)

if __name__ == "__main__":
    main()
