import threading
import socket
import os
import json
import random
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- הגדרות ---
TRACKER_IP = '127.0.0.1'
TRACKER_PORT = 13000
SYNC_FOLDER = 'synced_files'
ACTIVE_PEERS = {}
MY_NAME = f"{socket.gethostname()}-{random.randint(100, 999)}"
MY_DATA_PORT = 0
IS_DOWNLOADING = False  # דגל למניעת לולאה


class SyncHandler(FileSystemEventHandler):
    def __init__(self, folder_to_watch):
        self.folder_to_watch = folder_to_watch

    def on_modified(self, event):
        global IS_DOWNLOADING
        if not event.is_directory and not IS_DOWNLOADING:
            file_name = os.path.basename(event.src_path)
            if not file_name.startswith('.') and not file_name.endswith('.tmp'):
                print(f"[Watchdog] זוהה שינוי ב-{file_name}")
                notify_peers_of_change(file_name)

    def on_created(self, event):
        global IS_DOWNLOADING
        if not event.is_directory and not IS_DOWNLOADING:
            file_name = os.path.basename(event.src_path)
            print(f"[Watchdog] קובץ חדש: {file_name}")
            notify_peers_of_change(file_name)

    def on_deleted(self, event):
        global IS_DOWNLOADING
        if not event.is_directory and not IS_DOWNLOADING:
            file_name = os.path.basename(event.src_path)
            print(f"[Watchdog] קובץ נמחק: {file_name}. מעדכן את כולם...")
            # נשלח הודעת מחיקה לכל החברים
            notify_peers_of_deletion(file_name)

def notify_peers_of_deletion(file_name):
    global ACTIVE_PEERS
    for name, addr_info in ACTIVE_PEERS.items():
        ip, port = addr_info[0], addr_info[1]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            # הודעה חדשה בפרוטוקול שלנו
            s.sendall(f"DELETE_REQ:{MY_NAME}:{file_name}".encode('utf-8'))
            s.close()
        except:
            continue
def notify_peers_of_change(file_name):
    global ACTIVE_PEERS
    # שולח לכל מי שאני מכיר
    for name, addr_info in ACTIVE_PEERS.items():
        ip, port = addr_info[0], addr_info[1]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)  # שלא יתקע אם ה-Peer נעלם
            s.connect((ip, port))
            s.sendall(f"SYNC_REQ:{MY_NAME}:{file_name}".encode('utf-8'))
            s.close()
        except:
            continue


def handle_file_request(conn, addr):
    global ACTIVE_PEERS, SYNC_FOLDER
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
                    conn.sendall(f.read())
            else:
                conn.sendall("FILE_NOT_FOUND".encode('utf-8'))

        elif data.startswith("SYNC_REQ:"):
            parts = data.split(":")
            sender_name = parts[1]
            file_name = parts[2].strip()
            print(f"[סנכרון] קיבלתי הודעה מ-{sender_name} על {file_name}")

            if sender_name in ACTIVE_PEERS:
                ip, port = ACTIVE_PEERS[sender_name]
                threading.Thread(target=request_file_from_peer, args=(ip, port, file_name), daemon=True).start()
            # תרחיש 3: Peer חדש מבקש לדעת אילו קבצים קיימים
        elif data.startswith("LIST_FILES"):
            files = os.listdir(SYNC_FOLDER)
            # מסננים קבצים מוסתרים או זמניים
            files = [f for f in files if not f.startswith('.') and not f.endswith('.tmp')]
            files_data = json.dumps(files)
            conn.sendall(files_data.encode('utf-8'))
        elif data.startswith("DELETE_REQ:"):
            parts = data.split(":")
            sender_name = parts[1]
            file_name = parts[2].strip()
            print(f"[סנכרון] {sender_name} מחק את {file_name}. מוחק גם אצלי...")

            file_path = os.path.join(SYNC_FOLDER, file_name)
            if os.path.exists(file_path):
                global IS_DOWNLOADING
                IS_DOWNLOADING = True  # הגנה כדי שה-Watchdog שלנו לא יצעק בחזרה
                os.remove(file_path)
                time.sleep(0.5)
                IS_DOWNLOADING = False
                print(f"✅ הקובץ {file_name} נמחק בהצלחה.")
    except Exception as e:
        print(f"שגיאה בטיפול בבקשה: {e}")
    finally:
        conn.close()


def request_file_from_peer(target_ip, target_port, file_name):
    global IS_DOWNLOADING, SYNC_FOLDER
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((target_ip, target_port))
        client.sendall(f"GET_FILE:{file_name}".encode('utf-8'))
        response = client.recv(1024).decode('utf-8')

        if response.startswith("FILE_READY:"):
            file_size = int(response.split(":")[1])
            client.sendall("READY".encode('utf-8'))
            file_path = os.path.join(SYNC_FOLDER, file_name)

            IS_DOWNLOADING = True  # הגנה מופעלת
            with open(file_path, 'wb') as f:
                received = 0
                while received < file_size:
                    data = client.recv(4096)
                    if not data: break
                    f.write(data)
                    received += len(data)

            time.sleep(0.5)
            IS_DOWNLOADING = False  # הגנה כבויה
            print(f"✅ הקובץ {file_name} סונכרן בהצלחה!")
    except Exception as e:
        print(f"שגיאה במשיכת קובץ: {e}")
        IS_DOWNLOADING = False
    finally:
        client.close()


def update_peers_loop():
    """ Thread שרץ ברקע ומעדכן את רשימת ה-Peers כל 5 שניות """
    while True:
        register_to_tracker()
        time.sleep(5)


def register_to_tracker():
    global ACTIVE_PEERS
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
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
    """ פונה ל-Peer קיים ומוריד את כל מה שחסר """
    global ACTIVE_PEERS
    if not ACTIVE_PEERS:
        return

    # מנסה לפנות ל-Peer הראשון ברשימה
    target_name = list(ACTIVE_PEERS.keys())[0]
    ip, port = ACTIVE_PEERS[target_name]

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.sendall("LIST_FILES".encode('utf-8'))

        data = s.recv(4096).decode('utf-8')
        remote_files = json.loads(data)
        s.close()

        print(f"[סנכרון ראשוני] נמצאו {len(remote_files)} קבצים אצל {target_name}. בודק מה חסר...")

        for file_name in remote_files:
            local_path = os.path.join(SYNC_FOLDER, file_name)
            if not os.path.exists(local_path):
                print(f"[סנכרון ראשוני] מושך קובץ חסר: {file_name}")
                request_file_from_peer(ip, port, file_name)

    except Exception as e:
        print(f"⚠️ סנכרון ראשוני נכשל: {e}")

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

    print(f"--- מערכת פעילה בתיקייה: {SYNC_FOLDER} ---")

    threading.Thread(target=start_peer_data_server, daemon=True).start()
    time.sleep(1)

    # הפעלת ה-Thread שמעדכן את רשימת החברים
    threading.Thread(target=update_peers_loop, daemon=True).start()

    event_handler = SyncHandler(SYNC_FOLDER)
    observer = Observer()
    observer.schedule(event_handler, SYNC_FOLDER, recursive=False)
    observer.start()
    # 4. רישום לטראקר
    if register_to_tracker():
        print(f"** {MY_NAME} connected and synced **")

        # --- כאן מוסיפים את הסנכרון הראשוני ---
        time.sleep(2)  # מחכים רגע כדי לוודא שרשימת ה-Peers התעדכנה מהטראקר
        initial_sync()
        # ---------------------------------------
    else:
        print("שגיאה ברישום")


if __name__ == "__main__":
    start_all_services()
    while True:
        time.sleep(1)