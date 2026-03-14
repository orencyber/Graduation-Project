import threading
import socket
import os
import json
import random
import time
import hashlib
import shutil  # נדרש להעברת קבצים
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import queue
import compression_engine as ce

# --- הגדרות ---
TRACKER_IP = '127.0.0.1'
TRACKER_PORT = 13000
SYNC_FOLDER = 'synced_files'
# --- נתיב תיקיית הורדות (שנה את הנתיב למשתמש שלך) ---
# --- נתיב תיקיית הורדות ספציפי ---
DOWNLOADS_FOLDER = r"C:\Users\oren\Downloads"
ACTIVE_PEERS = {}
MY_NAME = f"{socket.gethostname()}-{random.randint(100, 999)}"
MY_DATA_PORT = 0
IS_DOWNLOADING = False
TOTAL_SAVED_BYTES = 0
file_hashes = {}
gui_queue = queue.Queue()


# --- פונקציות עזר ---

def get_file_hash(filepath):
    hasher = hashlib.sha256()
    try:
        if not os.path.exists(filepath): return None
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except:
        return None


def log_to_gui(message):
    gui_queue.put(message)
    print(message)


# --- לוגיקת צ'אט ---

def send_chat_message(message_text):
    """ שולח הודעת טקסט לכל הפירים המחוברים """
    for name, addr_info in ACTIVE_PEERS.items():
        ip, port = addr_info[0], addr_info[1]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            s.sendall(f"CHAT_MSG:{MY_NAME}:{message_text}".encode('utf-8'))
            s.close()
        except:
            continue
    log_to_gui(f"[You]: {message_text}")


# --- ניהול אירועי קבצים ---

class SyncHandler(FileSystemEventHandler):
    def __init__(self, folder_to_watch):
        self.folder_to_watch = folder_to_watch
        self.ignore_list = ["New Text Document.txt", "חדש.txt"]

    def process_event(self, event):
        global IS_DOWNLOADING
        if event.is_directory or IS_DOWNLOADING: return
        file_name = os.path.basename(event.src_path)
        filepath = event.src_path
        if (file_name.startswith('.') or file_name.endswith('.tmp') or file_name in self.ignore_list): return
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0: return

        new_hash = get_file_hash(filepath)
        if new_hash and file_hashes.get(file_name) == new_hash: return

        file_hashes[file_name] = new_hash
        log_to_gui(f"[Watchdog] Update detected: {file_name}")
        notify_peers_of_change(file_name)

    def on_modified(self, event):
        self.process_event(event)

    def on_created(self, event):
        self.process_event(event)

    def on_deleted(self, event):
        global IS_DOWNLOADING
        if not event.is_directory and not IS_DOWNLOADING:
            file_name = os.path.basename(event.src_path)
            if file_name in file_hashes: del file_hashes[file_name]
            log_to_gui(f"[Watchdog] File deleted: {file_name}")
            notify_peers_of_deletion(file_name)


class DownloadFolderHandler(FileSystemEventHandler):
    def process(self, event):
        if event.is_directory: return
        src_path = event.src_path
        filename = os.path.basename(src_path)

        # הדפסת דיבאג לטרמינל - תראה אם זה בכלל מזהה משהו
        print(f"DEBUG: Watchdog noticed {filename} in Downloads")

        # סינון קבצים זמניים
        if filename.endswith(('.tmp', '.crdownload', '.part')) or filename.startswith('.'):
            return

        # המתנה קצרה לוודא שהקובץ נכתב במלואו
        time.sleep(1.5)
        dest_path = os.path.join(SYNC_FOLDER, filename)

        try:
            # אם הקובץ קיים בהורדות ועדיין לא קיים בסנכרון - תעתיק
            if os.path.exists(src_path) and not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)
                log_to_gui(f"🚀 Auto-Import: {filename} captured!")
        except Exception as e:
            print(f"DEBUG: Copy error: {e}")

    def on_created(self, event):
        self.process(event)

    def on_moved(self, event):
        self.process(event)  # חשוב! דפדפנים משנים שם בסוף ההורדה

# --- תקשורת רשת ---

def handle_file_request(conn, addr):
    global SYNC_FOLDER, IS_DOWNLOADING, TOTAL_SAVED_BYTES
    try:
        data = conn.recv(1024).decode('utf-8')
        if not data: return

        # --- טיפול בהודעות צ'אט נכנסות ---
        if data.startswith("CHAT_MSG:"):
            parts = data.split(":", 2)
            sender = parts[1]
            content = parts[2]
            gui_queue.put(("CHAT", sender, content))  # שליחה ל-GUI כטאפל
            return

        if data.startswith("GET_FILE:"):
            file_name = data.split(":")[1].strip()
            file_path = os.path.join(SYNC_FOLDER, file_name)
            sending_path = file_path
            is_compressed = False
            image_extensions = ('.jpg', '.jpeg', '.png', '.bmp')

            if os.path.exists(file_path) and \
                    file_name.lower().endswith(image_extensions) and \
                    os.path.getsize(file_path) > 50 * 1024 * 1024:

                log_to_gui(f"⚡ Large image ({os.path.getsize(file_path) // (1024 * 1024)}MB). Compressing...")
                try:
                    bits, mapping, size = ce.compress_image(file_path)
                    bits_as_bytes = ce.string_to_bytes(bits)
                    temp_compressed_path = file_path + ".p2p"
                    ce.save_compressed_p2p(temp_compressed_path, bits_as_bytes, mapping, size)

                    TOTAL_SAVED_BYTES += (os.path.getsize(file_path) - os.path.getsize(temp_compressed_path))
                    sending_path = temp_compressed_path
                    is_compressed = True
                except Exception as e:
                    log_to_gui(f"❌ Compression failed: {e}")

            if os.path.exists(sending_path):
                f_size = os.path.getsize(sending_path)
                c_status = "COMPRESSED" if is_compressed else "RAW"
                conn.sendall(f"FILE_READY:{f_size}:{c_status}".encode('utf-8'))
                conn.recv(1024)  # Wait for READY
                with open(sending_path, 'rb') as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk: break
                        conn.sendall(chunk)
                if is_compressed: os.remove(sending_path)
            else:
                conn.sendall("FILE_NOT_FOUND".encode('utf-8'))

        elif data.startswith("SYNC_REQ:"):
            parts = data.split(":")
            sender_name, file_name = parts[1], parts[2].strip()
            log_to_gui(f"[Sync] Update from {sender_name} for {file_name}")
            if sender_name in ACTIVE_PEERS:
                ip, port = ACTIVE_PEERS[sender_name]
                threading.Thread(target=request_file_from_peer, args=(ip, port, file_name), daemon=True).start()

        elif data.startswith("DELETE_REQ:"):
            file_name = data.split(":")[2].strip()
            file_path = os.path.join(SYNC_FOLDER, file_name)
            if os.path.exists(file_path):
                IS_DOWNLOADING = True
                os.remove(file_path)
                time.sleep(0.2)
                IS_DOWNLOADING = False
                gui_queue.put(("REMOTE_DELETE", file_name))
                log_to_gui(f"✅ {file_name} deleted by peer.")

    except Exception as e:
        log_to_gui(f"Error: {e}")
    finally:
        conn.close()


# (שאר הפונקציות notify_peers, request_file, וכו' נשארות דומות)

def request_file_from_peer(target_ip, target_port, file_name):
    global IS_DOWNLOADING, SYNC_FOLDER, file_hashes
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((target_ip, target_port))
        client.sendall(f"GET_FILE:{file_name}".encode('utf-8'))
        response = client.recv(1024).decode('utf-8')
        if response.startswith("FILE_READY:"):
            parts = response.split(":")
            file_size = int(parts[1])
            is_compressed = (parts[2] == "COMPRESSED") if len(parts) > 2 else False
            client.sendall("READY".encode('utf-8'))

            dl_path = os.path.join(SYNC_FOLDER, file_name + (".p2p" if is_compressed else ""))
            final_path = os.path.join(SYNC_FOLDER, file_name)
            IS_DOWNLOADING = True
            with open(dl_path, 'wb') as f:
                received = 0
                while received < file_size:
                    data = client.recv(4096)
                    if not data: break
                    f.write(data)
                    received += len(data)
                    gui_queue.put(("PROGRESS", file_name, received / file_size))

            if is_compressed:
                bits_b, mapping, sz = ce.load_compressed_p2p(dl_path)
                img = ce.decompress_to_image(ce.bytes_to_string(bits_b), mapping, sz)
                img.save(final_path)
                os.remove(dl_path)

            file_hashes[file_name] = get_file_hash(final_path)
            IS_DOWNLOADING = False
            log_to_gui(f"✅ {file_name} synced!")
    except:
        IS_DOWNLOADING = False
    finally:
        client.close()


def notify_peers_of_deletion(file_name):
    for name, addr in ACTIVE_PEERS.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2);
            s.connect((addr[0], addr[1]))
            s.sendall(f"DELETE_REQ:{MY_NAME}:{file_name}".encode('utf-8'));
            s.close()
        except:
            continue


def notify_peers_of_change(file_name):
    for name, addr in ACTIVE_PEERS.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2);
            s.connect((addr[0], addr[1]))
            s.sendall(f"SYNC_REQ:{MY_NAME}:{file_name}".encode('utf-8'));
            s.close()
        except:
            continue


def notify_peers_of_rename(old_name, new_name):
    for name, addr in ACTIVE_PEERS.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2);
            s.connect((addr[0], addr[1]))
            s.sendall(f"RENAME_REQ:{MY_NAME}:{old_name}:{new_name}".encode('utf-8'));
            s.close()
        except:
            continue


def register_to_tracker():
    global ACTIVE_PEERS
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3);
        s.connect((TRACKER_IP, TRACKER_PORT))
        msg = {'action': 'REGISTER', 'name': MY_NAME, 'ip': '127.0.0.1', 'port': MY_DATA_PORT}
        s.sendall(json.dumps(msg).encode('utf-8'))
        resp = json.loads(s.recv(4096).decode('utf-8'))
        ACTIVE_PEERS = resp['peers']
        if MY_NAME in ACTIVE_PEERS: del ACTIVE_PEERS[MY_NAME]
        return True
    except:
        return False


def update_peers_loop():
    while True: register_to_tracker(); time.sleep(5)


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

    # --- הפעלת Watchdogs ---
    observer = Observer()
    # 1. צופה לתיקיית הסנכרון
    observer.schedule(SyncHandler(SYNC_FOLDER), SYNC_FOLDER, recursive=False)
    # 2. צופה לתיקיית ההורדות
    if os.path.exists(DOWNLOADS_FOLDER):
        observer.schedule(DownloadFolderHandler(), DOWNLOADS_FOLDER, recursive=False)
        log_to_gui(f"👀 Monitoring Downloads: {DOWNLOADS_FOLDER}")

    observer.start()

    if register_to_tracker():
        log_to_gui(f"** {MY_NAME} connected **")
    else:
        log_to_gui("Error: Tracker not found.")


if __name__ == "__main__":
    start_all_services()
    while True: time.sleep(1)
