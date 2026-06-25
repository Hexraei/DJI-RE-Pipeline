#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DJI Firmware Automated Extraction & Decryption Pipeline
A robust Tkinter GUI application designed to automate the ingestion, extraction,
decryption, folder organization, and CSV logging of firmware containers downloaded from DDD.
"""

import os
import sys
import shutil
import tarfile
import subprocess
import csv
import re
import datetime
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Master Dynamic Paths definition
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(PROJECT_DIR, "..", ".."))
TOOLS_DIR = os.path.join(PROJECT_DIR, "tools")
VENV_PYTHON = os.path.join(WORKSPACE_ROOT, "Tools", "venv", "bin", "python")

if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable

# Master Storage destinations inside Project Dir
FIRMWARE_STORE = os.path.join(PROJECT_DIR, "Firmwares")
RAW_STORE = os.path.join(FIRMWARE_STORE, "Raw")
EXTRACTED_STORE = os.path.join(FIRMWARE_STORE, "Extracted")
DECRYPTED_STORE = os.path.join(FIRMWARE_STORE, "Decrypted")

# Master Logs Storage destinations inside Project Dir
LOGS_DIR = os.path.join(PROJECT_DIR, "Logs")
SINGLE_LOGS_DIR = os.path.join(LOGS_DIR, "Single File Processing")
BULK_LOGS_DIR = os.path.join(LOGS_DIR, "Bulk Folder Processing")

TEMP_WORK_DIR = os.path.join(PROJECT_DIR, "temp_extract")

# Ensure required directories exist
for d in [RAW_STORE, EXTRACTED_STORE, DECRYPTED_STORE, TOOLS_DIR, LOGS_DIR, SINGLE_LOGS_DIR, BULK_LOGS_DIR, PROJECT_DIR]:
    os.makedirs(d, exist_ok=True)


def _to_relative_path(abs_path):
    """Converts absolute path to clean /Firmwares/... relative path string."""
    try:
        rel = os.path.relpath(abs_path, PROJECT_DIR)
        if rel.startswith("Firmwares"):
            return "/" + rel
        return abs_path
    except Exception:
        return abs_path


class FirmwarePipelineApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DJI Firmware Extraction & Decryption Pipeline")
        self.geometry("1150x800")
        self.minsize(900, 600)
        
        # Configure styling
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('.', font=('Helvetica', 10))
        self.style.configure('TButton', font=('Helvetica', 10, 'bold'), padding=6)
        self.style.configure('Clear.TButton', font=('Helvetica', 9, 'bold'), padding=(8, 2))
        self.style.configure('Home.TButton', font=('Helvetica', 12, 'bold'), padding=12)
        self.style.configure('Header.TLabel', font=('Helvetica', 15, 'bold'), foreground='#2C3E50')
        self.style.configure('Subheader.TLabel', font=('Helvetica', 11, 'italic'), foreground='#7F8C8D')
        self.style.configure('Banner.TLabel', font=('Helvetica', 10, 'bold'), foreground='#34495E')
        self.style.configure('Treeview', rowheight=26)
        self.style.configure('Treeview.Heading', font=('Helvetica', 11, 'bold'), background='#BDC3C7')

        # Control Variables
        self.single_file_path = tk.StringVar()
        self.bulk_folder_path = tk.StringVar()
        self.cancel_flag = False
        self.active_subprocess = None
        self.is_processing = False

        # Bulk Session Data Store
        self.bulk_sessions = {}
        self.bulk_archive_list = []
        self.bulk_current_index = 0

        # Single Session Data Store
        self.single_session_data = {'model': '', 'dest': '', 'types': {}, 'rows': []}

        # Tooltip reference
        self.tooltip_window = None

        # Master Container
        self.container = ttk.Frame(self)
        self.container.pack(fill=tk.BOTH, expand=True)

        # Build Screen Frames
        self.home_frame = ttk.Frame(self.container, padding=30)
        self.single_frame = ttk.Frame(self.container, padding=15)
        self.bulk_frame = ttk.Frame(self.container, padding=15)

        self._build_home_screen()
        self._build_single_screen()
        self._build_bulk_screen()

        # Start on Home Screen
        self.show_screen('home')

    def show_screen(self, screen_name):
        self.home_frame.pack_forget()
        self.single_frame.pack_forget()
        self.bulk_frame.pack_forget()

        if screen_name == 'home':
            self.home_frame.pack(fill=tk.BOTH, expand=True)
        elif screen_name == 'single':
            self.single_frame.pack(fill=tk.BOTH, expand=True)
        elif screen_name == 'bulk':
            self.bulk_frame.pack(fill=tk.BOTH, expand=True)

    def _go_back(self):
        if self.is_processing:
            msg = "Are you sure you want to go back?\nAn active decryption process is currently running.\nGoing back will terminate all active background jobs and clear GUI logs."
        else:
            msg = "Are you sure you want to go back to the Home screen?\nAll current GUI logs and dashboard tables will be cleared."

        if messagebox.askyesno("Confirm Exit to Home", msg):
            self.cancel_flag = True
            if self.active_subprocess:
                try:
                    self.active_subprocess.terminate()
                except Exception:
                    pass
            
            # Clean temp directory
            if os.path.exists(TEMP_WORK_DIR):
                shutil.rmtree(TEMP_WORK_DIR, ignore_errors=True)

            # Clear Single View
            self.single_session_data = {'model': '', 'dest': '', 'types': {}, 'rows': []}
            self._update_single_banner()
            for item in self.single_tree.get_children():
                self.single_tree.delete(item)
            self.single_log_box.delete(1.0, tk.END)
            self.single_status_var.set("Status: Idle")

            # Clear Bulk View
            self.bulk_sessions = {}
            self.bulk_archive_list = []
            self.bulk_current_index = 0
            self.bulk_combo['values'] = []
            self.bulk_combo.set('')
            self._update_bulk_banner(None)
            for item in self.bulk_tree.get_children():
                self.bulk_tree.delete(item)
            self.bulk_log_box.delete(1.0, tk.END)
            self.bulk_status_var.set("Status: Idle")

            self._lock_single_gui(False)
            self._lock_bulk_gui(False)
            self.show_screen('home')

    def _build_home_screen(self):
        box = ttk.Frame(self.home_frame)
        box.pack(expand=True)

        title = ttk.Label(box, text="DJI Firmware Automated Extraction & Decryption Engine", style='Header.TLabel', anchor=tk.CENTER)
        title.pack(pady=(0, 5))

        subtitle = ttk.Label(box, text="Select a mode to begin.", style='Subheader.TLabel', anchor=tk.CENTER)
        subtitle.pack(pady=(0, 40))

        btn_frame = ttk.Frame(box)
        btn_frame.pack(fill=tk.X)

        single_btn = ttk.Button(btn_frame, text="Single File Processing", style='Home.TButton', command=lambda: self.show_screen('single'))
        single_btn.pack(side=tk.LEFT, expand=True, padx=10, fill=tk.X)

        bulk_btn = ttk.Button(btn_frame, text="Bulk Folder Processing", style='Home.TButton', command=lambda: self.show_screen('bulk'))
        bulk_btn.pack(side=tk.RIGHT, expand=True, padx=10, fill=tk.X)

    def _build_single_screen(self):
        # Top Header & Go Back & Status Display
        header_frame = ttk.Frame(self.single_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))

        back_btn = ttk.Button(header_frame, text="< Go Back", command=self._go_back)
        back_btn.pack(side=tk.LEFT)

        title_label = ttk.Label(header_frame, text="Single File Processing Mode", style='Header.TLabel')
        title_label.pack(side=tk.LEFT, padx=(15, 0))

        self.single_status_var = tk.StringVar(value="Status: Idle")
        status_label = ttk.Label(header_frame, textvariable=self.single_status_var, font=('Helvetica', 11, 'bold', 'italic'), foreground='#7F8C8D')
        status_label.pack(side=tk.RIGHT, padx=(0, 10))

        # Input Frame (Label above Entry, Execute aligned beneath)
        input_frame = ttk.Frame(self.single_frame)
        input_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(input_frame, text="Select Firmware Container (tar/bin):").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Entry(input_frame, textvariable=self.single_file_path, width=70).grid(row=1, column=0, sticky=tk.EW, pady=(0, 10), padx=(0, 10))
        ttk.Button(input_frame, text="Browse File", command=self._browse_single).grid(row=1, column=1, sticky=tk.W, pady=(0, 10))
        
        self.single_exec_btn = ttk.Button(input_frame, text="Execute Pipeline", command=self._run_single_pipeline)
        self.single_exec_btn.grid(row=2, column=0, sticky=tk.W, pady=(5, 10))

        input_frame.columnconfigure(0, weight=1)

        # Master Content Split Frame (Left: Info + Dashboard, Right: Logs)
        main_content = ttk.Frame(self.single_frame)
        main_content.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        left_panel = ttk.Frame(main_content)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right_panel = ttk.Frame(main_content)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # LEFT PANEL TOP: Firmware Information Header (Matches Logs Header perfectly)
        info_header_frame = ttk.Frame(left_panel)
        info_header_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(info_header_frame, text="Firmware Information", style='Header.TLabel').pack(side=tk.LEFT)

        # Firmware Information Box (Frame with solid border to eliminate LabelFrame title margin and match Logs box starting height perfectly)
        self.single_banner_frame = ttk.Frame(left_panel, padding=8, relief=tk.SOLID, borderwidth=1)
        self.single_banner_frame.pack(fill=tk.X, pady=(0, 15))

        self.s_archive_lbl = ttk.Label(self.single_banner_frame, text="Source Archive: N/A", style='Banner.TLabel')
        self.s_archive_lbl.grid(row=0, column=0, sticky=tk.W, pady=1)

        self.s_model_lbl = ttk.Label(self.single_banner_frame, text="Model Name: N/A", style='Banner.TLabel')
        self.s_model_lbl.grid(row=1, column=0, sticky=tk.W, pady=1)

        self.s_dest_lbl = ttk.Label(self.single_banner_frame, text="Storage Destination: N/A", style='Banner.TLabel')
        self.s_dest_lbl.grid(row=2, column=0, sticky=tk.W, pady=1)

        self.s_type_lbl = ttk.Label(self.single_banner_frame, text="File Type(s): N/A", style='Banner.TLabel', foreground='#2980B9')
        self.s_type_lbl.grid(row=3, column=0, sticky=tk.W, pady=1)

        self.s_type_lbl.bind("<Enter>", lambda e: self._show_tooltip(e, self.single_session_data['types']))
        self.s_type_lbl.bind("<Leave>", self._hide_tooltip)

        # LEFT PANEL BOTTOM: Dashboard (Borderless Frame)
        tree_frame = ttk.Frame(left_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree_btn_frame = ttk.Frame(tree_frame)
        tree_btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(tree_btn_frame, text="Dashboard", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(tree_btn_frame, text="Clear", style='Clear.TButton', command=lambda: self._clear_tree(self.single_tree, self._log_single)).pack(side=tk.RIGHT)

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.single_tree = ttk.Treeview(tree_frame, columns=("module", "status"), show="headings", yscrollcommand=tree_scroll_y.set)
        tree_scroll_y.config(command=self.single_tree.yview)

        self._configure_tree_columns(self.single_tree)
        self.single_tree.pack(fill=tk.BOTH, expand=True)

        # RIGHT PANEL TOP: Logs (Borderless Frame, matches starting height of Firmware Info Header perfectly)
        log_frame = ttk.Frame(right_panel)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, expand=False, pady=(0, 5))
        ttk.Label(log_btn_frame, text="Logs", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(log_btn_frame, text="Clear", style='Clear.TButton', command=lambda: self._clear_log(self.single_log_box)).pack(side=tk.RIGHT)

        log_text_container = ttk.Frame(log_frame)
        log_text_container.pack(fill=tk.BOTH, expand=True)

        self.single_log_box = tk.Text(log_text_container, wrap=tk.WORD, font=('Consolas', 9), background='#FAFAFA')
        log_scroll = ttk.Scrollbar(log_text_container, orient=tk.VERTICAL, command=self.single_log_box.yview)
        self.single_log_box.config(yscrollcommand=log_scroll.set)
        
        self.single_log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_bulk_screen(self):
        # Top Header & Go Back & Status Display
        header_frame = ttk.Frame(self.bulk_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))

        back_btn = ttk.Button(header_frame, text="< Go Back", command=self._go_back)
        back_btn.pack(side=tk.LEFT)

        title_label = ttk.Label(header_frame, text="Bulk Folder Processing Mode", style='Header.TLabel')
        title_label.pack(side=tk.LEFT, padx=(15, 0))

        self.bulk_status_var = tk.StringVar(value="Status: Idle")
        status_label = ttk.Label(header_frame, textvariable=self.bulk_status_var, font=('Helvetica', 11, 'bold', 'italic'), foreground='#7F8C8D')
        status_label.pack(side=tk.RIGHT, padx=(0, 10))

        # Input Frame (Label above Entry, Execute aligned beneath)
        input_frame = ttk.Frame(self.bulk_frame)
        input_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(input_frame, text="Select Folder containing Firmware Archives:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Entry(input_frame, textvariable=self.bulk_folder_path, width=70).grid(row=1, column=0, sticky=tk.EW, pady=(0, 10), padx=(0, 10))
        ttk.Button(input_frame, text="Browse Folder", command=self._browse_bulk).grid(row=1, column=1, sticky=tk.W, pady=(0, 10))
        
        self.bulk_exec_btn = ttk.Button(input_frame, text="Execute Bulk Pipeline", command=self._run_bulk_pipeline)
        self.bulk_exec_btn.grid(row=2, column=0, sticky=tk.W, pady=(5, 10))

        input_frame.columnconfigure(0, weight=1)

        # Master Content Split Frame (Left: Inline Pagination Header + Info + Dashboard, Right: Logs)
        main_content = ttk.Frame(self.bulk_frame)
        main_content.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        left_panel = ttk.Frame(main_content)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right_panel = ttk.Frame(main_content)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # LEFT PANEL TOP: Inline Firmware Information & Pagination Header (Matches Logs Header perfectly)
        bulk_info_header = ttk.Frame(left_panel)
        bulk_info_header.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(bulk_info_header, text="Firmware Information", style='Header.TLabel').pack(side=tk.LEFT)

        self.bulk_next_btn = ttk.Button(bulk_info_header, text="▶", width=3, style='Clear.TButton', command=self._bulk_next)
        self.bulk_next_btn.pack(side=tk.RIGHT, padx=(0, 0))
        self.bulk_next_btn.bind("<Enter>", lambda e: self._show_text_tooltip(e, "Next Firmware"))
        self.bulk_next_btn.bind("<Leave>", self._hide_tooltip)

        self.bulk_combo = ttk.Combobox(bulk_info_header, state="readonly", width=35)
        self.bulk_combo.pack(side=tk.RIGHT, padx=8)
        self.bulk_combo.bind("<<ComboboxSelected>>", self._bulk_combo_select)

        self.bulk_prev_btn = ttk.Button(bulk_info_header, text="◀", width=3, style='Clear.TButton', command=self._bulk_prev)
        self.bulk_prev_btn.pack(side=tk.RIGHT, padx=(0, 0))
        self.bulk_prev_btn.bind("<Enter>", lambda e: self._show_text_tooltip(e, "Previous Firmware"))
        self.bulk_prev_btn.bind("<Leave>", self._hide_tooltip)

        # Firmware Information Box (Frame with solid border to eliminate LabelFrame title margin and match Logs box starting height perfectly)
        self.bulk_banner_frame = ttk.Frame(left_panel, padding=8, relief=tk.SOLID, borderwidth=1)
        self.bulk_banner_frame.pack(fill=tk.X, pady=(0, 15))

        self.b_archive_lbl = ttk.Label(self.bulk_banner_frame, text="Source Archive: N/A", style='Banner.TLabel')
        self.b_archive_lbl.grid(row=0, column=0, sticky=tk.W, pady=1)

        self.b_model_lbl = ttk.Label(self.bulk_banner_frame, text="Model Name: N/A", style='Banner.TLabel')
        self.b_model_lbl.grid(row=1, column=0, sticky=tk.W, pady=1)

        self.b_dest_lbl = ttk.Label(self.bulk_banner_frame, text="Storage Destination: N/A", style='Banner.TLabel')
        self.b_dest_lbl.grid(row=2, column=0, sticky=tk.W, pady=1)

        self.b_type_lbl = ttk.Label(self.bulk_banner_frame, text="File Type(s): N/A", style='Banner.TLabel', foreground='#2980B9')
        self.b_type_lbl.grid(row=3, column=0, sticky=tk.W, pady=1)

        self.b_type_lbl.bind("<Enter>", lambda e: self._show_tooltip(e, self._get_current_bulk_types()))
        self.b_type_lbl.bind("<Leave>", self._hide_tooltip)

        # LEFT PANEL BOTTOM: Dashboard (Borderless Frame)
        tree_frame = ttk.Frame(left_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree_btn_frame = ttk.Frame(tree_frame)
        tree_btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(tree_btn_frame, text="Dashboard", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(tree_btn_frame, text="Clear", style='Clear.TButton', command=lambda: self._clear_tree(self.bulk_tree, self._log_bulk)).pack(side=tk.RIGHT)

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.bulk_tree = ttk.Treeview(tree_frame, columns=("module", "status"), show="headings", yscrollcommand=tree_scroll_y.set)
        tree_scroll_y.config(command=self.bulk_tree.yview)

        self._configure_tree_columns(self.bulk_tree)
        self.bulk_tree.pack(fill=tk.BOTH, expand=True)

        # RIGHT PANEL TOP: Logs (Borderless Frame, matches starting height of Inline Info Header perfectly)
        log_frame = ttk.Frame(right_panel)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, expand=False, pady=(0, 5))
        ttk.Label(log_btn_frame, text="Logs", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(log_btn_frame, text="Clear", style='Clear.TButton', command=lambda: self._clear_log(self.bulk_log_box)).pack(side=tk.RIGHT)

        log_text_container = ttk.Frame(log_frame)
        log_text_container.pack(fill=tk.BOTH, expand=True)

        self.bulk_log_box = tk.Text(log_text_container, wrap=tk.WORD, font=('Consolas', 9), background='#FAFAFA')
        log_scroll = ttk.Scrollbar(log_text_container, orient=tk.VERTICAL, command=self.bulk_log_box.yview)
        self.bulk_log_box.config(yscrollcommand=log_scroll.set)
        
        self.bulk_log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _configure_tree_columns(self, tree):
        tree.heading("module", text="Module ID")
        tree.heading("status", text="Decryption Status")

        tree.column("module", width=180, anchor=tk.CENTER)
        tree.column("status", width=220, anchor=tk.CENTER)

    def _log_single(self, msg):
        self.single_log_box.insert(tk.END, f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.single_log_box.see(tk.END)

    def _log_bulk(self, msg):
        self.bulk_log_box.insert(tk.END, f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.bulk_log_box.see(tk.END)

    def _clear_tree(self, tree, log_func):
        for item in tree.get_children():
            tree.delete(item)
        log_func("Dashboard table cleared.")

    def _clear_log(self, log_box):
        log_box.delete(1.0, tk.END)

    def _browse_single(self):
        try:
            res = subprocess.run(['zenity', '--file-selection', '--title=Select DJI Firmware Container'], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                self.single_file_path.set(res.stdout.strip())
                return
        except Exception:
            pass
        f = filedialog.askopenfilename(title="Select DJI Firmware Container", filetypes=[("Firmware Archives", "*.bin *.tar *.zip"), ("All Files", "*.*")])
        if f:
            self.single_file_path.set(f)

    def _browse_bulk(self):
        try:
            res = subprocess.run(['zenity', '--file-selection', '--directory', '--title=Select Folder containing Firmware Archives'], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                self.bulk_folder_path.set(res.stdout.strip())
                return
        except Exception:
            pass
        d = filedialog.askdirectory(title="Select Folder containing Firmware Archives")
        if d:
            self.bulk_folder_path.set(d)

    def _lock_single_gui(self, lock=True):
        self.is_processing = lock
        state = tk.DISABLED if lock else tk.NORMAL
        self.single_exec_btn.config(state=state)
        status_text = "Status: Processing" if lock else "Status: Idle"
        self.single_status_var.set(status_text)

    def _lock_bulk_gui(self, lock=True):
        self.is_processing = lock
        state = tk.DISABLED if lock else tk.NORMAL
        self.bulk_exec_btn.config(state=state)
        status_text = "Status: Processing" if lock else "Status: Idle"
        self.bulk_status_var.set(status_text)

    def _parse_firmware_filename(self, filename):
        base = os.path.basename(filename)
        model = "UnknownModel"
        version = "V00.00.0000"

        ver_match = re.search(r'(V\d+\.\d+\.\d+)', base)
        if ver_match:
            version = ver_match.group(1)

        model_match = re.search(r'V\d+\.\d+\.\d+_([A-Za-z0-9]+)_dji', base)
        if model_match:
            model = model_match.group(1)
        else:
            parts = base.split('_')
            if len(parts) >= 2:
                model = parts[1]

        return model, version

    def _show_tooltip(self, event, types_dict):
        if not types_dict:
            return

        lines = []
        for f_type, mod_list in types_dict.items():
            lines.append(f"{f_type}: {', '.join(mod_list)}")
        tooltip_text = "\n".join(lines)

        x = event.widget.winfo_rootx() + 25
        y = event.widget.winfo_rooty() + 25

        self.tooltip_window = tk.Toplevel(event.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip_window, text=tooltip_text, justify=tk.LEFT,
                         background="#2C3E50", foreground="#ECF0F1", relief=tk.SOLID, borderwidth=1,
                         font=("Helvetica", 9, "bold"), padx=8, pady=6)
        label.pack(fill=tk.BOTH, expand=True)

    def _show_text_tooltip(self, event, text):
        x = event.widget.winfo_rootx() + 25
        y = event.widget.winfo_rooty() + 25

        self.tooltip_window = tk.Toplevel(event.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip_window, text=text, justify=tk.LEFT,
                         background="#2C3E50", foreground="#ECF0F1", relief=tk.SOLID, borderwidth=1,
                         font=("Helvetica", 9, "bold"), padx=8, pady=6)
        label.pack(fill=tk.BOTH, expand=True)

    def _hide_tooltip(self, event):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def _get_current_bulk_types(self):
        if not self.bulk_archive_list or self.bulk_current_index >= len(self.bulk_archive_list):
            return {}
        arc = self.bulk_archive_list[self.bulk_current_index]
        return self.bulk_sessions.get(arc, {}).get('types', {})

    def _bulk_prev(self):
        if self.bulk_archive_list and self.bulk_current_index > 0:
            self.bulk_current_index -= 1
            arc = self.bulk_archive_list[self.bulk_current_index]
            self.bulk_combo.set(arc)
            self._render_bulk_view(arc)

    def _bulk_next(self):
        if self.bulk_archive_list and self.bulk_current_index < len(self.bulk_archive_list) - 1:
            self.bulk_current_index += 1
            arc = self.bulk_archive_list[self.bulk_current_index]
            self.bulk_combo.set(arc)
            self._render_bulk_view(arc)

    def _bulk_combo_select(self, event):
        sel = self.bulk_combo.get()
        if sel in self.bulk_archive_list:
            self.bulk_current_index = self.bulk_archive_list.index(sel)
            self._render_bulk_view(sel)

    def _render_bulk_view(self, archive_name):
        self._update_bulk_banner(archive_name)
        for item in self.bulk_tree.get_children():
            self.bulk_tree.delete(item)
        
        if archive_name in self.bulk_sessions:
            for row in self.bulk_sessions[archive_name]['rows']:
                self.bulk_tree.insert("", tk.END, values=row)

    def _update_single_banner(self):
        model = self.single_session_data.get('model', 'N/A')
        dest = self.single_session_data.get('dest', 'N/A')
        types = self.single_session_data.get('types', {})

        self.s_archive_lbl.config(text=f"Source Archive: {self.single_session_data.get('archive', 'N/A')}")
        self.s_model_lbl.config(text=f"Model Name: {model}")
        self.s_dest_lbl.config(text=f"Storage Destination: {dest}")
        
        type_str = ", ".join(types.keys()) if types else "N/A"
        self.s_type_lbl.config(text=f"File Type(s): {type_str}")

    def _update_bulk_banner(self, archive_name):
        if not archive_name or archive_name not in self.bulk_sessions:
            self.b_archive_lbl.config(text="Source Archive: N/A")
            self.b_model_lbl.config(text="Model Name: N/A")
            self.b_dest_lbl.config(text="Storage Destination: N/A")
            self.b_type_lbl.config(text="File Type(s): N/A")
            return

        sess = self.bulk_sessions[archive_name]
        self.b_archive_lbl.config(text=f"Source Archive: {archive_name}")
        self.b_model_lbl.config(text=f"Model Name: {sess.get('model', 'N/A')}")
        self.b_dest_lbl.config(text=f"Storage Destination: {sess.get('dest', 'N/A')}")

        types = sess.get('types', {})
        type_str = ", ".join(types.keys()) if types else "N/A"
        self.b_type_lbl.config(text=f"File Type(s): {type_str}")

    def _run_single_pipeline(self):
        src_path = self.single_file_path.get()
        if not src_path or not os.path.exists(src_path):
            messagebox.showerror("Error", "Please select a valid firmware container file.")
            return

        # Check if previous GUI logs exist
        if self.single_session_data.get('archive') or self.single_tree.get_children() or self.single_log_box.get(1.0, tk.END).strip():
            if not messagebox.askyesno("Warning: Clearing GUI Logs", "Starting a new execution will automatically clear the previous GUI logs, dashboard table, and firmware information.\n\n(Note: All previous results are already safely stored in the CSV log files).\n\nDo you wish to proceed?"):
                return
            # Clear GUI
            self.single_session_data = {'model': '', 'dest': '', 'types': {}, 'rows': []}
            self._update_single_banner()
            for item in self.single_tree.get_children():
                self.single_tree.delete(item)
            self.single_log_box.delete(1.0, tk.END)
        
        self.cancel_flag = False
        self._lock_single_gui(True)
        self._log_single(f"Initiating single pipeline for: {os.path.basename(src_path)}")
        threading.Thread(target=self._worker_process_files, args=([src_path], False, None), daemon=True).start()

    def _run_bulk_pipeline(self):
        folder_path = self.bulk_folder_path.get()
        if not folder_path or not os.path.exists(folder_path):
            messagebox.showerror("Error", "Please select a valid bulk firmware folder.")
            return

        files = []
        for root, _, f_names in os.walk(folder_path):
            for f in f_names:
                if f.endswith(('.bin', '.tar', '.zip')):
                    files.append(os.path.join(root, f))

        if not files:
            messagebox.showwarning("Warning", "No firmware archives (.bin, .tar, .zip) found in selected folder.")
            return

        # Check if previous GUI logs exist
        if self.bulk_sessions or self.bulk_tree.get_children() or self.bulk_log_box.get(1.0, tk.END).strip():
            if not messagebox.askyesno("Warning: Clearing GUI Logs", "Starting a new execution will automatically clear the previous GUI logs, dashboard table, and firmware information.\n\n(Note: All previous results are already safely stored in the CSV log files).\n\nDo you wish to proceed?"):
                return
            # Clear GUI
            self.bulk_sessions = {}
            self.bulk_archive_list = []
            self.bulk_current_index = 0
            self.bulk_combo['values'] = []
            self.bulk_combo.set('')
            self._update_bulk_banner(None)
            for item in self.bulk_tree.get_children():
                self.bulk_tree.delete(item)
            self.bulk_log_box.delete(1.0, tk.END)

        self.cancel_flag = False
        self._lock_bulk_gui(True)
        self._log_bulk(f"Initiating bulk pipeline for {len(files)} archives in: {folder_path}")
        
        run_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
        threading.Thread(target=self._worker_process_files, args=(files, True, run_timestamp), daemon=True).start()

    def _worker_process_files(self, file_paths, is_bulk, run_timestamp):
        log_func = self._log_bulk if is_bulk else self._log_single
        bulk_model_data = {} if is_bulk else None
        
        try:
            for file_path in file_paths:
                if self.cancel_flag:
                    log_func("Pipeline execution cancelled by user.")
                    return
                self._process_single_archive(file_path, is_bulk, log_func, bulk_model_data)
            
            if self.cancel_flag:
                return

            # If Bulk mode, write the grouped model sheets to the Date Time.csv file
            if is_bulk and bulk_model_data:
                bulk_csv_path = os.path.join(BULK_LOGS_DIR, f"{run_timestamp}.csv")
                with open(bulk_csv_path, 'w', newline='', encoding='utf-8') as f_csv:
                    writer = csv.writer(f_csv)
                    
                    # Iterate through each model to create distinct sheet sections
                    for model_name, container_blocks in bulk_model_data.items():
                        writer.writerow([f"================================================================================"])
                        writer.writerow([f"SHEET / SECTION: MODEL - {model_name}"])
                        writer.writerow([f"================================================================================"])
                        writer.writerow(["Source Archive", "Module ID", "Model", "Version", "File Type", "Decryption Status", "Storage Destination", "Timestamp"])
                        
                        for container_hdr, c_rows in container_blocks:
                            writer.writerow([])
                            writer.writerow([container_hdr])
                            writer.writerows(c_rows)
                        
                        writer.writerow([])
                        writer.writerow([])

            log_func("Pipeline execution completed successfully.")
            
            if not is_bulk:
                # Get the last processed model name to show in success message
                last_model = self.single_session_data.get('model', 'unknown_model')
                single_csv_path = os.path.join(SINGLE_LOGS_DIR, f"{last_model}.csv")
                msg = f"Firmware pipeline completed successfully.\nResults logged to:\n{single_csv_path}"
            else:
                bulk_csv_path = os.path.join(BULK_LOGS_DIR, f"{run_timestamp}.csv")
                msg = f"Bulk firmware pipeline completed successfully.\nProcessed {len(file_paths)} archives.\nResults logged to:\n{bulk_csv_path}"
            
            self.after(0, lambda: messagebox.showinfo("Success", msg))
        except Exception as e:
            if not self.cancel_flag:
                err_msg = str(e)
                log_func(f"CRITICAL ERROR: {err_msg}")
                self.after(0, lambda: messagebox.showerror("Pipeline Error", f"An error occurred during pipeline execution:\n{err_msg}"))
        finally:
            if not self.cancel_flag:
                if is_bulk:
                    self.after(0, lambda: self._lock_bulk_gui(False))
                else:
                    self.after(0, lambda: self._lock_single_gui(False))

    def _process_single_archive(self, file_path, is_bulk, log_func, bulk_model_data):
        archive_name = os.path.basename(file_path)
        model, version = self._parse_firmware_filename(archive_name)
        log_func(f"--- Starting Ingestion: {archive_name} (Model: {model} | Version: {version}) ---")

        if os.path.exists(TEMP_WORK_DIR):
            shutil.rmtree(TEMP_WORK_DIR, ignore_errors=True)
        os.makedirs(TEMP_WORK_DIR, exist_ok=True)

        if self.cancel_flag:
            return

        # Step 1: Handle tar vs bin discrepancy
        if tarfile.is_tarfile(file_path):
            log_func(f"Discrepancy Check: '{archive_name}' identified as valid POSIX .tar archive.")
            try:
                with tarfile.open(file_path, 'r') as tar:
                    tar.extractall(path=TEMP_WORK_DIR)
                log_func(f"Unpacked tar archive to temporary work directory.")
            except Exception as e:
                log_func(f"Error unpacking tar: {str(e)}")
        else:
            log_func(f"Discrepancy Check: '{archive_name}' is NOT a tar archive. Treating as legacy xV4 binary container.")
            xv4_tool = os.path.join(TOOLS_DIR, "dji_xv4_fwcon.py")
            if os.path.exists(xv4_tool):
                cmd = [VENV_PYTHON, xv4_tool, "-p", file_path, "-x", "-m", os.path.join(TEMP_WORK_DIR, "m")]
                log_func(f"Executing dji_xv4_fwcon.py for xV4 extraction...")
                try:
                    self.active_subprocess = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    out, err = self.active_subprocess.communicate()
                    if self.active_subprocess.returncode != 0:
                        log_func(f"xV4 extraction warning: {err}")
                    else:
                        log_func(f"xV4 extraction completed successfully.")
                except Exception as e:
                    log_func(f"xV4 execution exception: {str(e)}")
                finally:
                    self.active_subprocess = None
            else:
                log_func(f"Error: dji_xv4_fwcon.py tool not found at {xv4_tool}")

        if self.cancel_flag:
            return

        # Step 2: Scan unpacked modules recursively (excluding .ini files and master containers)
        modules = []
        for root_dir, _, f_names in os.walk(TEMP_WORK_DIR):
            for f in f_names:
                if not f.endswith(('.ini', '_dji_system.bin', '_dji_system.tar')) and not f.endswith('_decrypted.bin'):
                    modules.append(os.path.join(root_dir, f))
        
        if not modules:
            log_func(f"Warning: No standard firmware modules (.bin / .sig) found after extraction.")
            if os.path.exists(TEMP_WORK_DIR):
                shutil.rmtree(TEMP_WORK_DIR, ignore_errors=True)
            return

        log_func(f"Scanning {len(modules)} extracted modules for encryption magic headers...")

        csv_rows = []
        archive_base = os.path.splitext(archive_name)[0]
        target_extract_dir = os.path.join(EXTRACTED_STORE, archive_base)
        target_modules_dir = os.path.join(target_extract_dir, "Modules")
        target_ini_dir = os.path.join(target_extract_dir, "Ini Files")
        target_dec_dir = os.path.join(DECRYPTED_STORE, archive_base)

        os.makedirs(target_modules_dir, exist_ok=True)
        os.makedirs(target_ini_dir, exist_ok=True)
        os.makedirs(target_dec_dir, exist_ok=True)

        session_types = {}
        session_rows = []

        for mod_path in sorted(modules):
            if self.cancel_flag:
                return

            if not os.path.isfile(mod_path):
                continue

            mod_name = os.path.basename(mod_path)
            mod_id = mod_name.split('.')[0]
            ext = mod_name.split('.')[-1]

            dec_status = "Unknown"
            dest_path = ""
            file_type = f".{ext}"

            # Inspect magic bytes for IM*H encryption wrapper
            with open(mod_path, 'rb') as fm:
                magic = fm.read(4)

            if magic == b'IM*H':
                log_func(f"Module '{mod_name}' identified as IM*H encrypted container (.sig). Attempting decryption...")
                file_type = "IM*H (.sig)"
                
                imah_tool = os.path.join(TOOLS_DIR, "dji_imah_fwsig.py")
                out_dec_bin = os.path.join(TEMP_WORK_DIR, f"{mod_id}_decrypted.bin")
                
                cmd = [VENV_PYTHON, imah_tool, "-i", mod_path, "-m", os.path.join(TEMP_WORK_DIR, f"{mod_id}_decrypted"), "-u"]
                try:
                    self.active_subprocess = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    out, err = self.active_subprocess.communicate()
                    ret = self.active_subprocess.returncode
                except Exception as e:
                    err = str(e)
                    ret = 1
                finally:
                    self.active_subprocess = None

                if self.cancel_flag:
                    return

                if "Cannot find enc_key" in err or ret != 0:
                    log_func(f"Decryption Failure: Missing key for '{mod_name}'. Flagging as Encrypted.")
                    dec_status = "Encrypted (Key Missing)"
                    dest_path = os.path.join(target_modules_dir, mod_name)
                    shutil.move(mod_path, dest_path)
                else:
                    log_func(f"Decryption Success: Successfully decrypted '{mod_name}'.")
                    dec_status = "Decrypted Successfully"
                    orig_dest = os.path.join(target_modules_dir, mod_name)
                    shutil.move(mod_path, orig_dest)
                    dest_path = os.path.join(target_dec_dir, f"{mod_id}_decrypted.bin")
                    if os.path.exists(out_dec_bin):
                        shutil.move(out_dec_bin, dest_path)
                    else:
                        dest_path = orig_dest
            else:
                log_func(f"Module '{mod_name}' is cleartext or legacy xV4 (.bin). No IM*H wrapper detected.")
                file_type = "Cleartext (.bin)"
                dec_status = "Cleartext / Legacy Decrypted"
                orig_dest = os.path.join(target_modules_dir, mod_name)
                shutil.copy(mod_path, orig_dest)
                dest_path = os.path.join(target_dec_dir, mod_name)
                shutil.move(mod_path, dest_path)

            rel_dest = _to_relative_path(dest_path)

            if file_type not in session_types:
                session_types[file_type] = []
            session_types[file_type].append(mod_name)

            row_data = (mod_id, dec_status)
            session_rows.append(row_data)

            if not is_bulk:
                self.after(0, lambda r=row_data: self.single_tree.insert("", tk.END, values=r))

            csv_rows.append([archive_name, mod_id, model, version, file_type, dec_status, rel_dest, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

        if self.cancel_flag:
            return

        # Move all .ini files to Ini Files folder
        for root_dir, _, f_names in os.walk(TEMP_WORK_DIR):
            for f in f_names:
                if f.endswith('.ini'):
                    ini_src = os.path.join(root_dir, f)
                    ini_dest = os.path.join(target_ini_dir, f)
                    try:
                        shutil.move(ini_src, ini_dest)
                    except Exception:
                        pass

        # Move original raw container to Raw storage
        raw_dest = os.path.join(RAW_STORE, archive_name)
        if os.path.abspath(file_path) != os.path.abspath(raw_dest):
            try:
                shutil.copy(file_path, raw_dest)
            except Exception:
                pass

        # Clean up temp_extract directory
        if os.path.exists(TEMP_WORK_DIR):
            shutil.rmtree(TEMP_WORK_DIR, ignore_errors=True)

        # Update Session Stores & GUI Banners
        rel_extract_dest = _to_relative_path(target_extract_dir)
        if not is_bulk:
            self.single_session_data = {'archive': archive_name, 'model': model, 'dest': rel_extract_dest, 'types': session_types, 'rows': session_rows}
            self.after(0, self._update_single_banner)
            
            # Single mode: Append to model_name.csv
            single_csv_path = os.path.join(SINGLE_LOGS_DIR, f"{model}.csv")
            write_header = not os.path.exists(single_csv_path) or os.path.getsize(single_csv_path) == 0
            with open(single_csv_path, 'a', newline='', encoding='utf-8') as f_csv:
                writer = csv.writer(f_csv)
                if write_header:
                    writer.writerow(["Source Archive", "Module ID", "Model", "Version", "File Type", "Decryption Status", "Storage Destination", "Timestamp"])
                
                writer.writerow([])
                writer.writerow([f"=== Container: {archive_name} | Model: {model} | Version: {version} | Executed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="])
                writer.writerow(["Source Archive", "Module ID", "Model", "Version", "File Type", "Decryption Status", "Storage Destination", "Timestamp"])
                writer.writerows(csv_rows)
        else:
            self.bulk_sessions[archive_name] = {'model': model, 'dest': rel_extract_dest, 'types': session_types, 'rows': session_rows}
            if archive_name not in self.bulk_archive_list:
                self.bulk_archive_list.append(archive_name)
            
            def _update_bulk_ui():
                self.bulk_combo['values'] = self.bulk_archive_list
                self.bulk_current_index = len(self.bulk_archive_list) - 1
                self.bulk_combo.set(archive_name)
                self._render_bulk_view(archive_name)
            
            self.after(0, _update_bulk_ui)

            # Bulk mode: Append to bulk_model_data in memory for final Date Time.csv writing
            if model not in bulk_model_data:
                bulk_model_data[model] = []
            container_hdr = f"=== Container: {archive_name} | Model: {model} | Version: {version} | Executed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="
            bulk_model_data[model].append((container_hdr, csv_rows))

        log_func(f"Successfully processed {len(session_rows)} modules for '{archive_name}'. CSV log updated.")


if __name__ == "__main__":
    app = FirmwarePipelineApp()
    app.mainloop()
