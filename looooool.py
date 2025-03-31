import socket
import threading
import time
import firebase_admin
from firebase_admin import credentials, firestore

# Configuración de Firebase
cred = credentials.Certificate("D:/Info/Escritorio/ambienteInteligenteInterfazWeb-main/ambienteInteligenteInterfazWeb-main/back/version1/src/main/resources/firebase-service-account.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

host = '10.0.5.228'  # Dirección local
port = 65432  # Puerto

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((host, port))
server_socket.listen(5)
print(f"Servidor escuchando en {host}:{port}")

# Diccionario para rastrear las últimas señales de los ESP32
active_clients = {}  # {ip: {"last_beat": timestamp, "id_sensor": id_sensor}}
lock = threading.Lock()


def monitor_clients():
    """Monitorea la actividad de los ESP32 y detecta desconexiones."""
    while True:
        time.sleep(8)
        current_time = time.time()
        with lock:
            for ip, data in list(active_clients.items()):
                last_beat = data["last_beat"]
                id_sensor = data["id_sensor"]
                
                # Si no hay beat en más de 15s, cambiar el estado del sensor a 'desactivado'
                if current_time - last_beat > 15:
                    print(f"[ALERTA] El dispositivo {ip} se ha desconectado. Actualizando estado...")

                    # Actualizar el estado en Firestore
                    doc_ref = db.collection("sensorshouse1").document(id_sensor)
                    doc_ref.update({"estado": "desactivado"})
                    
                    # Eliminar el cliente desconectado del diccionario
                    del active_clients[ip]


def handle_client(conn, addr):
    """Manejo de conexión del cliente (ESP32)"""
    print(f"Conexión establecida con {addr}")
    try:
        while True:
            data = conn.recv(1024)
            if not data or data.strip() == b"":
                continue
            message = data.decode().strip()

            # Detectar beat para mantener conexión activa
            if message == "beat":
                with lock:
                    if addr[0] in active_clients:
                        active_clients[addr[0]]["last_beat"] = time.time()
                continue

            print(f"Mensaje recibido de {addr}: {message}")

            # Clasificar y guardar en Firestore según el tipo de mensaje
            if message.startswith("USER:"):
                _, name, email, age = message.split(':')
                db.collection("users").add({
                    "name": name,
                    "email": email,
                    "age": int(age)
                })
            elif message.startswith("TEMP:"):
                _, temp, id_sensor = message.split(':')
                db.collection("temperature").add({
                    "temp": temp,
                    "idSensor": id_sensor
                })
            elif message.startswith("LOCATION:"):
                _, location, id_sensor = message.split(':')
                db.collection("locationofperson").add({
                    "location": location,
                    "idSensor": id_sensor
                })
            elif message.startswith("SENSOR:"):
                _, estado, id_sensor = message.split(':')
                doc_ref = db.collection("sensorshouse1").document(id_sensor)
                
                # Actualizar estado del sensor
                doc_ref.set({
                    "estado": estado,
                    "idSensor": id_sensor
                }, merge=True)
                
                # Guardar el beat para ese sensor usando la IP como clave
                with lock:
                    active_clients[addr[0]] = {
                        "last_beat": time.time(),
                        "id_sensor": id_sensor
                    }
            else:
                # Opcional: Guardar en una colección por defecto (ej: "datos_crudos")
                db.collection("datos_crudos").add({
                    "ip": str(addr[0]),
                    "mensaje": message,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
    except Exception as e:
        print(f"Error con {addr}: {e}")
    finally:
        conn.close()
        with lock:
            if addr[0] in active_clients:
                del active_clients[addr[0]]


# Iniciar hilo de monitoreo de clientes para detectar inactividad
t_monitor = threading.Thread(target=monitor_clients, daemon=True)
t_monitor.start()

try:
    while True:
        conn, addr = server_socket.accept()
        client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        client_thread.start()
except KeyboardInterrupt:
    print("\nServidor detenido manualmente.")
finally:
    server_socket.close()
    print("Servidor cerrado.")
