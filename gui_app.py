import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import sys
import os
import subprocess

# Import your logic
import peer_app

# Set theme and color
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class RedirectText:
    def __init__(self, gui_instance):
        self.gui = gui_instance

    def write(self, string):
        if string.strip():
            self.gui.log(string.strip())

    def flush(self):
        pass


class PeerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"P2P Node - {peer_app.MY_NAME}")

        # 1. DISABLE the "tough" fullscreen
        self.overrideredirect(False)

        # 2. Set to Maximized state (fills screen but keeps taskbar/buttons)
        self.state('zoomed')

        # 3. Standard protocol for closing the window (X button)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Optional: You can still bind ESC to close for convenience
        self.bind("<Escape>", lambda e: self.on_closing())

        # Grid configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(1, weight=1)

        self.setup_ui()
        sys.stdout = RedirectText(self)
        self.update_loop()

    def setup_ui(self):
        # --- Header ---
        self.header = ctk.CTkFrame(self, height=100, corner_radius=0)
        self.header.grid(row=0, column=0, columnspan=2, sticky="nsew")

        self.title_label = ctk.CTkLabel(self.header, text=f"P2P SYNC NODE: {peer_app.MY_NAME}",
                                        font=ctk.CTkFont(size=28, weight="bold"))
        self.title_label.pack(side="left", padx=40)

        # Action Buttons in Header
        self.btn_exit = ctk.CTkButton(self.header, text="EXIT APP", fg_color="#e74c3c",
                                      hover_color="#c0392b", command=self.on_closing, width=120)
        self.btn_exit.pack(side="right", padx=20)

        self.btn_folder = ctk.CTkButton(self.header, text="OPEN FOLDER", fg_color="#3498db",
                                        hover_color="#2980b9", command=self.open_sync_folder, width=120)
        self.btn_folder.pack(side="right", padx=10)

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self, width=350, corner_radius=0)
        self.sidebar.grid(row=1, column=0, sticky="nsew", padx=15, pady=15)

        ctk.CTkLabel(self.sidebar, text="NETWORK PEERS", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        self.peers_textbox = ctk.CTkTextbox(self.sidebar, height=250, font=("Arial", 14), state="disabled")
        self.peers_textbox.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(self.sidebar, text="LOCAL FILES", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        self.files_textbox = ctk.CTkTextbox(self.sidebar, height=400, font=("Arial", 14), state="disabled")
        self.files_textbox.pack(fill="both", expand=True, padx=15, pady=10)

        # --- Main Log ---
        self.main_content = ctk.CTkFrame(self, corner_radius=15)
        self.main_content.grid(row=1, column=1, sticky="nsew", padx=15, pady=15)

        ctk.CTkLabel(self.main_content, text="REAL-TIME ACTIVITY LOG", font=ctk.CTkFont(size=20, weight="bold")).pack(
            pady=(20, 10))
        self.log_area = ctk.CTkTextbox(self.main_content, font=("Consolas", 14), text_color="#2ecc71")
        self.log_area.pack(fill="both", expand=True, padx=20, pady=20)

    def log(self, msg):
        timestamp = time.strftime('%H:%M:%S')
        # Use root.after to ensure thread-safe UI update
        self.after(0, lambda: self._append_log(timestamp, msg))

    def _append_log(self, timestamp, msg):
        self.log_area.insert("end", f"[{timestamp}] > {msg}\n")
        self.log_area.see("end")

    def update_loop(self):
        # Update Peers list
        self.peers_textbox.configure(state="normal")
        self.peers_textbox.delete("1.0", "end")
        for p in peer_app.ACTIVE_PEERS.keys():
            self.peers_textbox.insert("end", f" ● {p}\n")
        self.peers_textbox.configure(state="disabled")

        # Update Files list
        self.files_textbox.configure(state="normal")
        self.files_textbox.delete("1.0", "end")
        if os.path.exists(peer_app.SYNC_FOLDER):
            for f in os.listdir(peer_app.SYNC_FOLDER):
                if not f.startswith('.'):
                    self.files_textbox.insert("end", f" 📄 {f}\n")
        self.files_textbox.configure(state="disabled")

        # Refresh every 2 seconds
        self.after(2000, self.update_loop)

    def open_sync_folder(self):
        """ Opens the local sync folder in Windows Explorer """
        path = os.path.abspath(peer_app.SYNC_FOLDER)
        if os.path.exists(path):
            subprocess.Popen(f'explorer "{path}"')

    def on_closing(self):
        if messagebox.askokcancel("Exit Network", "Are you sure you want to disconnect?"):
            self.destroy()


if __name__ == "__main__":
    # Start P2P services in background
    logic_thread = threading.Thread(target=peer_app.start_all_services, daemon=True)
    logic_thread.start()

    app = PeerGUI()
    app.mainloop()