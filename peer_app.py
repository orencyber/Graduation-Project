import threading
import socket
import os
import json
import random
import time
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import queue

# --- הגדרות ---
TRACKER_IP = '127.0.0.1'
TRACKER_PORT = 13000
SYNC_FOLDER = 'synced_files'
ACTIVE_PEERS = {}
MY_NAME = f"{socket.gethostname()}-{random.randint(100, 999)}"
MY_DATA_PORT = 0
IS_DOWNLOADING = False

# מילון לשמירת ה-Hashes של הקבצים המקומיים כדי למנוע סנכרון כפול
file_hashes = {}

gui_queue = queue.Queue()


def get_file_hash(filepath):
    """ מחשב SHA-256 של קובץ """
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except:
        return None


def log_to_gui(message):
    """ שולח הודעה לתור של ה-GUI ומדפיס לטרמינל """
    gui_queue.put(message)
    print(message)


class SyncHandler(FileSystemEventHandler):
    def __init__(self, folder_to_watch):
        self.folder_to_watch = folder_to_watch
        # רשימת התעלמות מקבצים זמניים של מערכת ההפעלה
        self.ignore_list = ["New Text Document.txt", "חדש.txt"]

    def process_event(self, event):
        global IS_DOWNLOADING, file_hashes
        if event.is_directory or IS_DOWNLOADING:
            return

        file_name = os.path.basename(event.src_path)
        filepath = event.src_path

        # 1. סינון קבצים זמניים/מוסתרים/ברשימת ההתעלמות
        if (file_name.startswith('.') or
                file_name.endswith('.tmp') or
                file_name in self.ignore_list):
            return

        # 2. בדיקה שהקובץ קיים ולא ריק (ווינדוס יוצרת קבצים ריקים לפני שינוי שם)
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return

        # 3. מנגנון Hash - האם התוכן באמת השתנה?
        new_hash = get_file_hash(filepath)
        if new_hash and file_hashes.get(file_name) == new_hash:
            return  # התוכן זהה, אין צורך לסנכרן

        file_hashes[file_name] = new_hash
        log_to_gui(f"[Watchdog] Update detected: {file_name}")
        notify_peers_of_change(file_name)

    def on_modified(self, event):
        self.process_event(event)

    def on_created(self, event):
        self.process_event(event)

    def on_deleted(self, event):
        global IS_DOWNLOADING, file_hashes
        if not event.is_directory and not IS_DOWNLOADING:
            file_name = os.path.basename(event.src_path)
            if file_name in file_hashes:
                del file_hashes[file_name]
            log_to_gui(f"[Watchdog] File deleted: {file_name}")
            notify_peers_of_deletion(file_name)


def notify_peers_of_deletion(file_name):
    for name, addr_info in ACTIVE_PEERS.items():
        ip, port = addr_info[0], addr_info[1]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            s.sendall(f"DELETE_REQ:{MY_NAME}:{file_name}".encode('utf-8'))
            s.close()
        except:
            continue


def notify_peers_of_change(file_name):
    for name, addr_info in ACTIVE_PEERS.items():
        ip, port = addr_info[0], addr_info[1]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            s.sendall(f"SYNC_REQ:{MY_NAME}:{file_name}".encode('utf-8'))
            s.close()
        except:
            continue


def handle_file_request(conn, addr):
    global SYNC_FOLDER,IS_DOWNLOADING
    try:
        data = conn.recv(1024).decode('utf-8')
        if not data: return

        if data.startswith("GET_FILE:"):
            file_name = data.split(":")[1].strip()
            file_path = os.path.join(SYNC_FOLDER, file_name)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                conn.sendall(f"FILE_READY:{file_size}".encode('utf-8'))
                conn.recv(1024)
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk: break
                        conn.sendall(chunk)
            else:
                conn.sendall("FILE_NOT_FOUND".encode('utf-8'))

        elif data.startswith("SYNC_REQ:"):
            parts = data.split(":")
            sender_name = parts[1]
            file_name = parts[2].strip()
            log_to_gui(f"[Sync] Update from {sender_name} for {file_name}")
            if sender_name in ACTIVE_PEERS:
                ip, port = ACTIVE_PEERS[sender_name]
                threading.Thread(target=request_file_from_peer, args=(ip, port, file_name), daemon=True).start()

        elif data.startswith("LIST_FILES"):
            files = [f for f in os.listdir(SYNC_FOLDER) if not f.startswith('.') and not f.endswith('.tmp')]
            conn.sendall(json.dumps(files).encode('utf-8'))

        elif data.startswith("DELETE_REQ:"):
            file_name = data.split(":")[2].strip()
            file_path = os.path.join(SYNC_FOLDER, file_name)
            if os.path.exists(file_path):
                global IS_DOWNLOADING
                IS_DOWNLOADING = True
                os.remove(file_path)
                time.sleep(0.2)
                IS_DOWNLOADING = False
                gui_queue.put(("REMOTE_DELETE", file_name))
                log_to_gui(f"✅ {file_name} deleted by peer.")
        elif data.startswith("RENAME_REQ:"):
            parts = data.split(":")
            old_name = parts[2]
            new_name = parts[3].strip()

            old_path = os.path.join(SYNC_FOLDER, old_name)
            new_path = os.path.join(SYNC_FOLDER, new_name)

            if os.path.exists(old_path):
                IS_DOWNLOADING = True
                try:
                    os.rename(old_path, new_path)
                    # עדכון מילון ה-Hashes כדי לשמור על עקביות
                    if old_name in file_hashes:
                        file_hashes[new_name] = file_hashes.pop(old_name)
                    log_to_gui(f"📝 Renamed {old_name} to {new_name} by peer.")
                except Exception as e:
                    print(f"Rename error: {e}")
                IS_DOWNLOADING = False
    except Exception as e:
        log_to_gui(f"Error handling request: {e}")
    finally:
        conn.close()


def request_file_from_peer(target_ip, target_port, file_name):
    global IS_DOWNLOADING, SYNC_FOLDER, file_hashes
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((target_ip, target_port))
        client.sendall(f"GET_FILE:{file_name}".encode('utf-8'))
        response = client.recv(1024).decode('utf-8')

        if response.startswith("FILE_READY:"):
            file_size = int(response.split(":")[1])
            client.sendall("READY".encode('utf-8'))
            file_path = os.path.join(SYNC_FOLDER, file_name)

            IS_DOWNLOADING = True
            with open(file_path, 'wb') as f:
                received = 0
                while received < file_size:
                    data = client.recv(4096)
                    if not data: break
                    f.write(data)
                    received += len(data)
                    progress_ratio = received / file_size
                    gui_queue.put(("PROGRESS", file_name, progress_ratio))

            time.sleep(0.5)
            # עדכון ה-Hash המקומי לאחר הורדה כדי שלא נשלח אותו חלוזרה בטעות
            file_hashes[file_name] = get_file_hash(file_path)

            IS_DOWNLOADING = False
            log_to_gui(f"✅ {file_name} synced successfully!")
    except Exception as e:
        log_to_gui(f"Error requesting file: {e}")
        IS_DOWNLOADING = False
    finally:
        client.close()

def notify_peers_of_rename(old_name, new_name):
    for name, addr_info in ACTIVE_PEERS.items():
        ip, port = addr_info[0], addr_info[1]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            # פורמט: RENAME_REQ:SENDER:OLD_NAME:NEW_NAME
            s.sendall(f"RENAME_REQ:{MY_NAME}:{old_name}:{new_name}".encode('utf-8'))
            s.close()
        except:
            continue

def update_peers_loop():
    while True:
        register_to_tracker()
        time.sleep(5)


def register_to_tracker():
    global ACTIVE_PEERS
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(3)
        s.connect((TRACKER_IP, TRACKER_PORT))
        msg = {'action': 'REGISTER', 'name': MY_NAME, 'ip': '127.0.0.1', 'port': MY_DATA_PORT}
        s.sendall(json.dumps(msg).encode('utf-8'))
        resp = json.loads(s.recv(4096).decode('utf-8'))
        ACTIVE_PEERS = resp['peers']
        if MY_NAME in ACTIVE_PEERS: del ACTIVE_PEERS[MY_NAME]
        return True
    except:
        return False


def initial_sync():
    if not ACTIVE_PEERS: return
    target_name = list(ACTIVE_PEERS.keys())[0]
    ip, port = ACTIVE_PEERS[target_name]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.sendall("LIST_FILES".encode('utf-8'))
        data = s.recv(4096).decode('utf-8')
        remote_files = json.loads(data)
        s.close()
        log_to_gui(f"Initial sync: Found {len(remote_files)} files.")
        for file_name in remote_files:
            if not os.path.exists(os.path.join(SYNC_FOLDER, file_name)):
                request_file_from_peer(ip, port, file_name)
    except Exception as e:
        log_to_gui(f"⚠️ Initial sync failed: {e}")


def start_peer_data_server():
    global MY_DATA_PORT
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', 0))
    MY_DATA_PORT = server.getsockname()[1]
    server.listen(5)
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_file_request, args=(conn, addr), daemon=True).start()


def start_all_services():
    global SYNC_FOLDER
    SYNC_FOLDER = f"synced_files_{MY_NAME}"
    if not os.path.exists(SYNC_FOLDER): os.makedirs(SYNC_FOLDER)
    log_to_gui(f"System active in: {SYNC_FOLDER}")
    threading.Thread(target=start_peer_data_server, daemon=True).start()
    time.sleep(1)
    threading.Thread(target=update_peers_loop, daemon=True).start()
    event_handler = SyncHandler(SYNC_FOLDER)
    observer = Observer()
    observer.schedule(event_handler, SYNC_FOLDER, recursive=False)
    observer.start()
    if register_to_tracker():
        log_to_gui(f"** {MY_NAME} connected and registered **")
        time.sleep(2)
        initial_sync()
    else:
        log_to_gui("Error: Tracker not found.")


if __name__ == "__main__":
    start_all_services()
    while True:
        time.sleep(1)
