import socket
import threading
import json
import os  # ייבוא לצורך פונקציות עתידיות, כרגע לא חובה

# --- הגדרות ---
TRACKER_IP = '0.0.0.0'  # הקשבה לכל כתובות ה-IP המקומיות
TRACKER_PORT = 13000  # הפורט המוגדר ל-Tracker

# המילון שישמור את רשימת ה-Peers: {peer_name: (ip, port)}
active_peers = {}


def handle_peer_connection(client_socket, addr):
    """ מטפל בחיבור נכנס מ-Peer שרוצה להירשם או לקבל רשימה """
    global active_peers
    try:
        # 1. קבלת בקשת הרישום
        request = client_socket.recv(1024).decode('utf-8')
        data = json.loads(request)

        action = data.get('action')
        peer_name = data.get('name')
        peer_ip = data.get('ip')
        peer_port = data.get('port')

        if action == 'REGISTER':
            # 2. רישום ה-Peer בטבלה
            active_peers[peer_name] = (peer_ip, peer_port)
            print(f"-> נרשם Peer חדש: {peer_name} ב- {peer_ip}:{peer_port}. סך Peers: {len(active_peers)}")

            # 3. שליחת רשימת ה-Peers המעודכנת חזרה אליו
            response = {'status': 'OK', 'peers': active_peers}
            client_socket.sendall(json.dumps(response).encode('utf-8'))

        # (אפשרות: הוספת Deregister בעתיד לטיפול בהתנתקות)

    except Exception as e:
        print(f"שגיאה בטיפול בחיבור: {e}")
    finally:
        # סוגרים את החיבור לאחר סיום הטיפול
        client_socket.close()


def start_tracker():
    """ מפעיל את שרת ה-Tracker """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # מאפשר שימוש חוזר בפורט, חשוב לבדיקות
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((TRACKER_IP, TRACKER_PORT))
        server.listen(5)
        print("*************************************")
        print(f"*** Tracker Server פועל בפורט {TRACKER_PORT} ***")
        print("*************************************")

        while True:
            # השרת ממתין ומקבל חיבורים חדשים
            client_socket, addr = server.accept()
            # מטפל בחיבור ב-Thread נפרד כדי לא לחסום את השרת
            peer_handler = threading.Thread(target=handle_peer_connection, args=(client_socket, addr))
            peer_handler.start()

    except Exception as e:
        print(f"שגיאה קריטית ב-Tracker: {e}")


if __name__ == "__main__":
    start_tracker()