import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
import threading
import time
import sys
import os
from PIL import Image, ImageTk
import subprocess

# Import your logic file
import peer_app

# Set modern theme
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
        self.state('zoomed')

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind("<Escape>", lambda e: self.on_closing())

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=1)

        self.setup_ui()
        sys.stdout = RedirectText(self)
        self.update_loop()

    def setup_ui(self):
        # --- SIDEBAR (Left) ---
        self.sidebar = ctk.CTkFrame(self, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        ctk.CTkLabel(self.sidebar, text="P2P CONTROL", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        self.prog_frame = ctk.CTkFrame(self.sidebar, fg_color="#2c3e50")
        self.prog_frame.pack(fill="x", padx=10, pady=10)
        self.prog_label = ctk.CTkLabel(self.prog_frame, text="Idle", font=("Arial", 11))
        self.prog_label.pack(pady=5)
        self.prog_bar = ctk.CTkProgressBar(self.prog_frame)
        self.prog_bar.set(0)
        self.prog_bar.pack(padx=10, pady=10)

        ctk.CTkLabel(self.sidebar, text="Network Peers", font=("Arial", 14, "bold")).pack(pady=(10, 5))
        self.peers_box = ctk.CTkTextbox(self.sidebar, height=150, state="disabled")
        self.peers_box.pack(fill="x", padx=10, pady=5)

        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.stats_frame.pack(side="bottom", fill="x", padx=10, pady=20)

        self.saved_label = ctk.CTkLabel(self.stats_frame, text="Total Saved: 0 MB",
                                        font=("Arial", 12, "italic"), text_color="#2ecc71")
        self.saved_label.pack()

        # --- MAIN AREA (Right) with TABS ---
        self.tab_view = ctk.CTkTabview(self, segmented_button_selected_color="#3498db")
        self.tab_view.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.tab_files = self.tab_view.add("Files Management")
        self.tab_chat = self.tab_view.add("P2P Chat")

        self.setup_files_tab()
        self.setup_chat_tab()

    def setup_files_tab(self):
        self.tab_files.grid_columnconfigure(0, weight=1)
        self.tab_files.grid_columnconfigure(1, weight=1)
        self.tab_files.grid_rowconfigure(0, weight=1)

        self.files_frame = ctk.CTkFrame(self.tab_files)
        self.files_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(self.files_frame, text="LOCAL FILES", font=("Arial", 16, "bold")).pack(pady=10)

        self.files_listbox = tk.Listbox(self.files_frame, bg="#242424", fg="white",
                                        font=("Consolas", 12), borderwidth=0, highlightthickness=0,
                                        selectbackground="#3498db")
        self.files_listbox.pack(fill="both", expand=True, padx=10, pady=10)
        self.files_listbox.bind('<<ListboxSelect>>', self.on_file_selected)

        self.right_col = ctk.CTkFrame(self.tab_files, fg_color="transparent")
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.right_col.grid_rowconfigure(0, weight=2)
        self.right_col.grid_rowconfigure(1, weight=1)

        # PREVIEW
        self.preview_frame = ctk.CTkFrame(self.right_col)
        self.preview_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        ctk.CTkLabel(self.preview_frame, text="FILE PREVIEW", font=("Arial", 14, "bold")).pack(pady=5)
        self.image_label = ctk.CTkLabel(self.preview_frame, text="")
        self.preview_text = ctk.CTkTextbox(self.preview_frame, state="disabled", font=("Consolas", 11))
        self.preview_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.btn_rename = ctk.CTkButton(self.preview_frame, text="RENAME FILE", fg_color="#2980b9",
                                        command=self.rename_current_file)
        self.btn_rename.pack(pady=5, padx=10)
        self.btn_delete = ctk.CTkButton(self.preview_frame, text="DELETE FILE FROM NETWORK", fg_color="#c0392b",
                                        command=self.delete_current_file)
        self.btn_delete.pack(pady=5, padx=10)

        # LOGS
        self.log_frame = ctk.CTkFrame(self.right_col)
        self.log_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.log_area = ctk.CTkTextbox(self.log_frame, font=("Consolas", 11), text_color="#2ecc71")
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_area.tag_config("compression", foreground="#00ffff")

    def setup_chat_tab(self):
        self.tab_chat.grid_columnconfigure(0, weight=1)
        self.tab_chat.grid_rowconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.tab_chat, state="disabled", font=("Arial", 12))
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.chat_display.tag_config("me", foreground="#3498db", justify="right")
        self.chat_display.tag_config("others", foreground="#e67e22")

        self.input_frame = ctk.CTkFrame(self.tab_chat, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.chat_input = ctk.CTkEntry(self.input_frame, placeholder_text="Type a message to peers...")
        self.chat_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.chat_input.bind("<Return>", lambda e: self.send_chat())

        self.btn_send = ctk.CTkButton(self.input_frame, text="Send", width=100, command=self.send_chat)
        self.btn_send.pack(side="right")

    def send_chat(self):
        msg = self.chat_input.get().strip()
        if msg:
            peer_app.send_chat_message(msg)
            self.display_chat_msg("You", msg, is_me=True)
            self.chat_input.delete(0, 'end')

    def display_chat_msg(self, sender, msg, is_me=False):
        self.chat_display.configure(state="normal")
        tag = "me" if is_me else "others"
        prefix = f"[{sender}]: " if not is_me else ""
        self.chat_display.insert("end", f"{prefix}{msg}\n", tag)
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def on_file_selected(self, event):
        selection = self.files_listbox.curselection()
        if not selection: return
        filename = self.files_listbox.get(selection[0]).replace(" 📄 ", "").strip()
        filepath = os.path.join(peer_app.SYNC_FOLDER, filename)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.image_label.configure(image=None, text="")
        self.image_label.pack_forget()
        self.preview_text.pack(fill="both", expand=True, padx=5, pady=5)
        if not os.path.exists(filepath): return
        try:
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif']:
                self.preview_text.pack_forget()
                self.image_label.pack(fill="both", expand=True, padx=5, pady=5)
                img = Image.open(filepath)
                img.thumbnail((400, 400))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.image_label.configure(image=ctk_img)
                self.image_label.image = ctk_img
            elif ext == '.p2p':
                self.preview_text.insert("end", "Compressed P2P Container.")
            elif ext in ['.txt', '.py', '.json', '.log']:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    self.preview_text.insert("end", f.read(5000))
        except Exception as e:
            self.preview_text.insert("end", f"Error: {e}")
        self.preview_text.configure(state="disabled")

    def rename_current_file(self):
        selection = self.files_listbox.curselection()
        if not selection: return
        old_name = self.files_listbox.get(selection[0]).replace(" 📄 ", "").strip()
        new_name = ctk.CTkInputDialog(text="New name:", title="Rename").get_input()
        if new_name and new_name != old_name:
            if "." not in new_name: new_name += os.path.splitext(old_name)[1]
            try:
                peer_app.IS_DOWNLOADING = True
                os.rename(os.path.join(peer_app.SYNC_FOLDER, old_name), os.path.join(peer_app.SYNC_FOLDER, new_name))
                peer_app.IS_DOWNLOADING = False
                peer_app.notify_peers_of_rename(old_name, new_name)
            except:
                peer_app.IS_DOWNLOADING = False

    def delete_current_file(self):
        selection = self.files_listbox.curselection()
        if not selection: return
        filename = self.files_listbox.get(selection[0]).replace(" 📄 ", "").strip()
        if messagebox.askyesno("Confirm", f"Delete {filename}?"):
            try:
                peer_app.IS_DOWNLOADING = True
                os.remove(os.path.join(peer_app.SYNC_FOLDER, filename))
                peer_app.IS_DOWNLOADING = False
                peer_app.notify_peers_of_deletion(filename)
                self.reset_preview()
            except:
                peer_app.IS_DOWNLOADING = False

    def reset_preview(self):
        self.image_label.configure(image=None);
        self.image_label.pack_forget()
        self.preview_text.configure(state="normal");
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled");
        self.preview_text.pack(fill="both", expand=True)

    def log(self, msg):
        is_compression_msg = any(k in msg for k in ["Compressing", "Decompressing", "P2P", "⚡", "🔧"])
        self.log_area.configure(state="normal")
        tag = "compression" if is_compression_msg else None
        self.log_area.insert("end", f"> {msg}\n", tag)
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def update_progress(self, filename, ratio):
        self.prog_bar.set(ratio)
        self.prog_label.configure(text=f"Syncing: {filename.replace('.p2p', '')} ({int(ratio * 100)}%)")
        if ratio >= 1: self.after(2000, lambda: [self.prog_label.configure(text="Idle"), self.prog_bar.set(0)])

    def update_loop(self):
        while not peer_app.gui_queue.empty():
            item = peer_app.gui_queue.get()
            if isinstance(item, tuple):
                if item[0] == "REMOTE_DELETE":
                    self.reset_preview()
                elif item[0] == "PROGRESS":
                    self.update_progress(item[1], item[2])
                elif item[0] == "CHAT":
                    self.display_chat_msg(item[1], item[2])
            else:
                self.log(item)

        self.peers_box.configure(state="normal")
        self.peers_box.delete("1.0", "end")
        for p in peer_app.ACTIVE_PEERS.keys():
            self.peers_box.insert("end", f" ● {p}\n")
        self.peers_box.configure(state="disabled")

        if os.path.exists(peer_app.SYNC_FOLDER):
            files = [f for f in os.listdir(peer_app.SYNC_FOLDER) if not f.startswith('.') and not f.endswith('.p2p')]
            current = [self.files_listbox.get(i).replace(" 📄 ", "").strip() for i in range(self.files_listbox.size())]
            if set(files) != set(current):
                self.files_listbox.delete(0, tk.END)
                for f in files: self.files_listbox.insert(tk.END, f" 📄 {f}")

        if hasattr(peer_app, 'TOTAL_SAVED_BYTES'):
            saved_mb = peer_app.TOTAL_SAVED_BYTES / (1024 * 1024)
            self.saved_label.configure(text=f"Bandwidth Saved: {saved_mb:.2f} MB")

        self.after(1000, self.update_loop)

    def on_closing(self):
        self.destroy()


if __name__ == "__main__":
    threading.Thread(target=peer_app.start_all_services, daemon=True).start()
    app = PeerGUI()
    app.mainloop()
