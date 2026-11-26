from datetime import datetime
from html import escape
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
import hashlib
import secrets
import subprocess
import csv
import os
import shutil

import mysql.connector

from koneksi import buat_koneksi


class AplikasiJadwalKelas:
    WARNA = {
        "sidebar": "#173f46",
        "sidebar_hover": "#24545b",
        "accent": "#3e8b82",
        "accent_light": "#e6f3f0",
        "background": "#f4f7f6",
        "surface": "#ffffff",
        "text": "#213338",
        "muted": "#78898b",
        "border": "#e4ecea",
        "orange": "#ce8b45",
        "blue": "#537f9c",
    }
    HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]

    def __init__(self, root):
        self.root = root
        self.root.title("Jadwal Pelajaran | XI RPL")
        self.root.geometry("1120x700")
        self.root.minsize(900, 600)
        self.root.configure(bg=self.WARNA["background"])
        self.current_user = None
        self.current_role = "operator"

        self.hari_aktif = None
        self.kelas_aktif = None
        self.semua_data = []
        self.hari_buttons = {}
        self._atur_style()
        if not self._login_awal():
            self.root.destroy()
            return
        self._buat_layout()
        self.muat_data()

    def _hash_password(self, password, salt):
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def _login_awal(self):
        login = tk.Toplevel(self.root)
        login.title("Login")
        login.geometry("380x280")
        login.resizable(False, False)
        login.configure(bg=self.WARNA["background"])
        login.transient(self.root)
        login.grab_set()
        login.protocol("WM_DELETE_WINDOW", lambda: None)

        tk.Label(
            login, text="Masuk ke aplikasi",
            bg=self.WARNA["background"], fg=self.WARNA["text"],
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w", padx=28, pady=(25, 18))

        form = tk.Frame(login, bg=self.WARNA["background"])
        form.pack(fill=tk.X, padx=28)
        tk.Label(form, text="Username", bg=self.WARNA["background"],
                 fg=self.WARNA["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        username = ttk.Entry(form)
        username.pack(fill=tk.X, pady=(4, 10))
        tk.Label(form, text="Password", bg=self.WARNA["background"],
                 fg=self.WARNA["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        password = ttk.Entry(form, show="*", )
        password.pack(fill=tk.X, pady=(4, 12))

        berhasil = {"nilai": False}

        def proses_login(_event=None):
            nama = username.get().strip()
            kata_sandi = password.get()
            if not nama or not kata_sandi:
                messagebox.showwarning("Data belum lengkap",
                                       "Masukkan username dan password.",
                                       parent=login)
                return
            conn = self._buka_koneksi()
            if conn is None:
                return
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """SELECT id_pengguna, password_hash, salt, nama_lengkap, role
                       FROM pengguna WHERE username = %s""",
                    (nama,),
                )
                user = cursor.fetchone()
                if user:
                    if user[1].startswith("hash_password_"):
                        if kata_sandi != "admin":
                            valid = False
                        else:
                            salt_baru = secrets.token_hex(16)
                            hash_baru = self._hash_password(kata_sandi, salt_baru)
                            cursor.execute(
                                """UPDATE pengguna
                                   SET password_hash = %s, salt = %s
                                   WHERE id_pengguna = %s""",
                                (hash_baru, salt_baru, user[0]),
                            )
                            conn.commit()
                            valid = True
                        role = user[4]
                        nama_lengkap = user[3]
                    else:
                        valid = secrets.compare_digest(
                            self._hash_password(kata_sandi, user[2]), user[1]
                        )
                        role = user[4]
                        nama_lengkap = user[3]
                else:
                    valid = False
                    role = ""
                    nama_lengkap = ""
            except mysql.connector.Error as error:
                conn.rollback()
                messagebox.showerror("Login gagal", str(error), parent=login)
                return
            finally:
                cursor.close()
                conn.close()

            if not valid:
                messagebox.showerror("Login gagal",
                                     "Username atau password salah.",
                                     parent=login)
                password.delete(0, tk.END)
                password.focus_set()
                return
            self.current_user = nama_lengkap
            self.current_role = role
            berhasil["nilai"] = True
            login.destroy()

        buttons = tk.Frame(login, bg=self.WARNA["background"])
        buttons.pack(fill=tk.X, padx=28, pady=(2, 20))
        self._buat_tombol(buttons, "Masuk", proses_login, utama=True).pack(
            side=tk.RIGHT
        )
        password.bind("<Return>", proses_login)
        username.focus_set()
        self.root.wait_window(login)
        return berhasil["nilai"]

    def _is_admin(self):
        if self.current_role == "admin":
            return True
        messagebox.showwarning(
            "Akses ditolak",
            "Fitur ini hanya tersedia untuk administrator.",
            parent=self.root,
        )
        return False

    def _atur_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Jadwal.Treeview",
            rowheight=42,
            font=("Segoe UI", 10),
            background=self.WARNA["surface"],
            fieldbackground=self.WARNA["surface"],
            foreground=self.WARNA["text"],
            borderwidth=0,
        )
        style.configure(
            "Jadwal.Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            background="#f5f8f7",
            foreground=self.WARNA["muted"],
            relief="flat",
            padding=(12, 12),
        )
        style.map(
            "Jadwal.Treeview",
            background=[("selected", self.WARNA["accent_light"])],
            foreground=[("selected", self.WARNA["text"])],
        )
        style.configure(
            "Jadwal.Vertical.TScrollbar",
            background="#e6eeec",
            troughcolor=self.WARNA["surface"],
            bordercolor=self.WARNA["surface"],
            arrowcolor=self.WARNA["muted"],
        )

    def _buat_layout(self):
        self.sidebar = tk.Frame(self.root, bg=self.WARNA["sidebar"], width=228)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=self.WARNA["sidebar"])
        brand.pack(fill=tk.X, padx=24, pady=(28, 38))
        tk.Label(
            brand,
            text="JADWAL.",
            bg=self.WARNA["sidebar"],
            fg="#ffffff",
            font=("Segoe UI", 21, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="RUANG BELAJAR",
            bg=self.WARNA["sidebar"],
            fg="#a9c5c2",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(3, 0))

        tk.Label(
            self.sidebar,
            text="MENU UTAMA",
            bg=self.WARNA["sidebar"],
            fg="#8eafac",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=24, pady=(0, 10))

        self._buat_nav_item(
            "▦", "Ringkasan", aktif=True, command=self.reset_filter
        )
        self._buat_nav_item(
            "▤", "Jadwal Pelajaran", aktif=False, command=self._fokus_jadwal
        )
        self._buat_nav_item(
            "▧", "Data Master", aktif=False, command=self.buka_menu_master
        )
        self._buat_nav_item(
            "⚙", "Pengaturan", aktif=False, command=self.buka_pengaturan
        )

        sidebar_footer = tk.Frame(self.sidebar, bg=self.WARNA["sidebar"])
        sidebar_footer.pack(side=tk.BOTTOM, fill=tk.X, padx=22, pady=22)
        tk.Frame(sidebar_footer, bg="#42666a", height=1).pack(fill=tk.X, pady=(0, 14))
        tk.Label(
            sidebar_footer,
            text="SEMANGAT BELAJAR!",
            bg=self.WARNA["sidebar"],
            fg="#d7e8e5",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            sidebar_footer,
            text="Semua jadwal kelasmu\nada di satu tempat.",
            bg=self.WARNA["sidebar"],
            fg="#a9c5c2",
            font=("Segoe UI", 9),
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 0))

        self.content = tk.Frame(self.root, bg=self.WARNA["background"])
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        topbar = tk.Frame(self.content, bg=self.WARNA["surface"], height=66)
        topbar.pack(fill=tk.X)
        topbar.pack_propagate(False)
        tk.Label(
            topbar,
            text="Dashboard",
            bg=self.WARNA["surface"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=30)
        tk.Label(
            topbar,
            text="SEMUA KELAS",
            bg=self.WARNA["accent_light"],
            fg=self.WARNA["accent"],
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
        ).pack(side=tk.RIGHT, padx=30)

        self.page = tk.Frame(self.content, bg=self.WARNA["background"])
        self.page.pack(fill=tk.BOTH, expand=True, padx=30, pady=(25, 28))

        heading = tk.Frame(self.page, bg=self.WARNA["background"])
        heading.pack(fill=tk.X, pady=(0, 20))
        tk.Label(
            heading,
            text="Halo, selamat datang",
            bg=self.WARNA["background"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 21, "bold"),
        ).pack(anchor="w")
        tk.Label(
            heading,
            text="Pantau jadwal pelajaran kelasmu dengan lebih mudah.",
            bg=self.WARNA["background"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        stats = tk.Frame(self.page, bg=self.WARNA["background"])
        stats.pack(fill=tk.X, pady=(0, 20))
        self.total_value = self._buat_kartu_ringkasan(
            stats, "Total jadwal", "0", "seluruh jam pelajaran", self.WARNA["accent"]
        )
        self.hari_value = self._buat_kartu_ringkasan(
            stats, "Hari belajar", "0", "hari dengan jadwal", self.WARNA["orange"]
        )
        self.mapel_value = self._buat_kartu_ringkasan(
            stats, "Mata pelajaran", "0", "mapel terjadwal", self.WARNA["blue"]
        )

        table_card = tk.Frame(
            self.page,
            bg=self.WARNA["surface"],
            highlightthickness=1,
            highlightbackground=self.WARNA["border"],
        )
        table_card.pack(fill=tk.BOTH, expand=True)

        table_header = tk.Frame(table_card, bg=self.WARNA["surface"])
        table_header.pack(fill=tk.X, padx=20, pady=(18, 12))
        title_frame = tk.Frame(table_header, bg=self.WARNA["surface"])
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            title_frame,
            text="Jadwal mingguan",
            bg=self.WARNA["surface"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_frame,
            text="Pilih hari untuk melihat pelajaran yang berlangsung.",
            bg=self.WARNA["surface"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))
        action_frame = tk.Frame(table_header, bg=self.WARNA["surface"])
        action_frame.pack(side=tk.RIGHT, padx=(10, 0))
        self._buat_tombol(action_frame, "Data master", self.buka_menu_master).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._buat_tombol(action_frame, "Cetak", self.buka_cetak_jadwal).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._buat_tombol(action_frame, "Ekspor", self.buka_ekspor_laporan).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._buat_tombol(action_frame, "Ubah", self.ubah_jadwal_pilihan).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._buat_tombol(action_frame, "Hapus", self.hapus_jadwal_pilihan).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._buat_tombol(
            action_frame, "+ Jadwal", self.buka_form_jadwal, utama=True
        ).pack(side=tk.LEFT)

        self.selector_frame = tk.Frame(table_card, bg=self.WARNA["surface"])
        self.selector_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._buat_filter_hari("Semua", None)
        for hari in self.HARI:
            self._buat_filter_hari(hari, hari)
        class_filter = tk.Frame(self.selector_frame, bg=self.WARNA["surface"])
        class_filter.pack(side=tk.RIGHT, padx=(8, 2))
        tk.Label(
            class_filter,
            text="KELAS",
            bg=self.WARNA["surface"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 6))
        self.kelas_filter = ttk.Combobox(
            class_filter,
            values=("Semua kelas",),
            state="readonly",
            width=14,
        )
        self.kelas_filter.set("Semua kelas")
        self.kelas_filter.pack(side=tk.LEFT)
        self.kelas_filter.bind("<<ComboboxSelected>>", self._filter_kelas_berubah)

        tree_frame = tk.Frame(table_card, bg=self.WARNA["surface"])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        columns = (
            "ID", "Hari", "Jam Pelajaran", "Mata Pelajaran",
            "Guru Pengampu", "Kelas", "Ruangan"
        )
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Jadwal.Treeview",
        )
        self.tree.heading("ID", text="NO.")
        self.tree.column("ID", width=48, anchor=tk.CENTER, stretch=False)
        self.tree.heading("Hari", text="HARI")
        self.tree.column("Hari", width=85, anchor=tk.CENTER, stretch=False)
        self.tree.heading("Jam Pelajaran", text="WAKTU")
        self.tree.column("Jam Pelajaran", width=120, anchor=tk.CENTER, stretch=False)
        self.tree.heading("Mata Pelajaran", text="MATA PELAJARAN")
        self.tree.column("Mata Pelajaran", width=165, anchor=tk.W, stretch=True)
        self.tree.heading("Guru Pengampu", text="GURU PENGAMPU")
        self.tree.column("Guru Pengampu", width=155, anchor=tk.W, stretch=True)
        self.tree.heading("Kelas", text="KELAS")
        self.tree.column("Kelas", width=95, anchor=tk.CENTER, stretch=False)
        self.tree.heading("Ruangan", text="RUANGAN")
        self.tree.column("Ruangan", width=95, anchor=tk.CENTER, stretch=False)
        self.tree.tag_configure("evenrow", background="#ffffff")
        self.tree.tag_configure("oddrow", background="#f8faf9")

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self.tree.yview, style="Jadwal.Vertical.TScrollbar"
        )
        horizontal_scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview
        )
        self.tree.configure(
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.bind("<Double-1>", lambda _event: self.ubah_jadwal_pilihan())

    def _buat_nav_item(self, ikon, teks, aktif=False, command=None):
        bg = self.WARNA["sidebar_hover"] if aktif else self.WARNA["sidebar"]
        item = tk.Button(
            self.sidebar,
            text=f"{ikon}   {teks}",
            command=command,
            bg=bg,
            fg="#d0e4e1" if aktif else "#a9c5c2",
            font=("Segoe UI", 9, "bold" if aktif else "normal"),
            relief=tk.FLAT,
            bd=0,
            anchor="w",
            padx=14,
            pady=11,
            cursor="hand2",
            activebackground=self.WARNA["sidebar_hover"],
            activeforeground="#ffffff",
        )
        item.pack(fill=tk.X, padx=14, pady=3)

    def _fokus_jadwal(self):
        self.tree.focus_set()

    def _buat_tombol(self, parent, teks, command, utama=False):
        return tk.Button(
            parent,
            text=teks,
            command=command,
            bg=self.WARNA["accent"] if utama else self.WARNA["accent_light"],
            fg="#ffffff" if utama else self.WARNA["accent"],
            activebackground=self.WARNA["sidebar_hover"],
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )

    def _buka_koneksi(self):
        conn = buat_koneksi()
        if conn is None:
            messagebox.showerror(
                "Koneksi gagal",
                "Tidak dapat terhubung ke database. Pastikan MySQL aktif dan "
                "database db_jadwal_sekolah sudah dibuat dari database.sql.",
                parent=self.root,
            )
        return conn

    def buka_menu_master(self):
        if not self._is_admin():
            return
        window = tk.Toplevel(self.root)
        window.title("Data Master")
        window.resizable(False, False)
        window.configure(bg=self.WARNA["background"])
        window.transient(self.root)
        window.grab_set()
        tk.Label(
            window,
            text="Kelola data master",
            bg=self.WARNA["background"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 4))
        tk.Label(
            window,
            text="Pilih data yang ingin ditambahkan, diubah, atau dihapus.",
            bg=self.WARNA["background"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=22, pady=(0, 14))

        jenis_data = (
            ("guru", "Data Guru"),
            ("kelas", "Data Kelas"),
            ("mapel", "Mata Pelajaran"),
            ("ruangan", "Data Ruangan"),
        )
        for jenis, label in jenis_data:
            self._buat_tombol(
                window,
                label,
                lambda j=jenis, w=window: self.buka_kelola_master(j, w),
            ).pack(fill=tk.X, padx=22, pady=4)
        tk.Button(
            window,
            text="Tutup",
            command=window.destroy,
            bg=self.WARNA["background"],
            fg=self.WARNA["muted"],
            relief=tk.FLAT,
            padx=12,
            pady=8,
        ).pack(anchor="e", padx=22, pady=(10, 18))

    def buka_kelola_master(self, jenis, menu_window=None):
        konfigurasi = {
            "guru": ("Guru", "guru", "id_guru", "nama_guru"),
            "kelas": ("Kelas", "kelas", "id_kelas", "nama_kelas"),
            "mapel": ("Mata Pelajaran", "mapel", "id_mapel", "nama_mapel"),
            "ruangan": ("Ruangan", "ruangan", "id_ruangan", "nama_ruangan"),
        }
        judul, tabel, kolom_id, kolom_nama = konfigurasi[jenis]
        window = tk.Toplevel(self.root)
        window.title(f"Kelola {judul}")
        window.geometry("600x470")
        window.minsize(520, 400)
        window.configure(bg=self.WARNA["background"])
        window.transient(self.root)

        if menu_window is not None:
            menu_window.grab_release()

        tk.Label(
            window,
            text=f"Data {judul}",
            bg=self.WARNA["background"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 12))

        form = tk.Frame(window, bg=self.WARNA["background"])
        form.pack(fill=tk.X, padx=20)
        tk.Label(
            form,
            text=f"Nama {judul.lower()}",
            bg=self.WARNA["background"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        name_entry = ttk.Entry(form, font=("Segoe UI", 10))
        name_entry.pack(fill=tk.X, pady=(4, 10))

        list_frame = tk.Frame(window, bg=self.WARNA["background"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(4, 10))
        tree = ttk.Treeview(
            list_frame,
            columns=("id", "name"),
            show="headings",
            height=9,
            style="Jadwal.Treeview",
        )
        tree.heading("id", text="ID")
        tree.heading("name", text=f"NAMA {judul.upper()}")
        tree.column("id", width=70, anchor=tk.CENTER, stretch=False)
        tree.column("name", width=400, anchor=tk.W)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def muat_master():
            tree.delete(*tree.get_children())
            conn = self._buka_koneksi()
            if conn is None:
                return
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"SELECT {kolom_id}, {kolom_nama} FROM {tabel} "
                    f"ORDER BY {kolom_nama}"
                )
                for row in cursor.fetchall():
                    tree.insert("", tk.END, values=row)
            except mysql.connector.Error as error:
                messagebox.showerror(
                    "Data gagal dimuat", str(error), parent=window
                )
            finally:
                cursor.close()
                conn.close()

        def pilih_data(_event=None):
            selection = tree.selection()
            if selection:
                name_entry.delete(0, tk.END)
                name_entry.insert(0, tree.item(selection[0], "values")[1])

        def simpan_master():
            nama = name_entry.get().strip()
            if not nama:
                messagebox.showwarning(
                    "Nama belum diisi", "Masukkan nama terlebih dahulu.", parent=window
                )
                return
            selection = tree.selection()
            conn = self._buka_koneksi()
            if conn is None:
                return
            cursor = conn.cursor()
            try:
                if selection:
                    id_data = tree.item(selection[0], "values")[0]
                    cursor.execute(
                        f"UPDATE {tabel} SET {kolom_nama} = %s "
                        f"WHERE {kolom_id} = %s",
                        (nama, id_data),
                    )
                else:
                    cursor.execute(
                        f"INSERT INTO {tabel} ({kolom_nama}) VALUES (%s)",
                        (nama,),
                    )
                conn.commit()
                name_entry.delete(0, tk.END)
                muat_master()
            except mysql.connector.IntegrityError:
                conn.rollback()
                messagebox.showerror(
                    "Data tidak bisa disimpan",
                    "Nama ini sudah digunakan atau datanya masih dipakai jadwal.",
                    parent=window,
                )
            except mysql.connector.Error as error:
                conn.rollback()
                messagebox.showerror(
                    "Data tidak bisa disimpan", str(error), parent=window
                )
            finally:
                cursor.close()
                conn.close()

        def hapus_master():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(
                    "Pilih data", "Pilih data yang ingin dihapus.", parent=window
                )
                return
            if not messagebox.askyesno(
                "Konfirmasi hapus",
                "Hapus data yang dipilih?",
                parent=window,
            ):
                return
            id_data = tree.item(selection[0], "values")[0]
            conn = self._buka_koneksi()
            if conn is None:
                return
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"DELETE FROM {tabel} WHERE {kolom_id} = %s", (id_data,)
                )
                conn.commit()
                name_entry.delete(0, tk.END)
                muat_master()
            except mysql.connector.IntegrityError:
                conn.rollback()
                messagebox.showerror(
                    "Data masih digunakan",
                    "Hapus atau ubah jadwal yang memakai data ini terlebih dahulu.",
                    parent=window,
                )
            except mysql.connector.Error as error:
                conn.rollback()
                messagebox.showerror("Gagal menghapus data", str(error), parent=window)
            finally:
                cursor.close()
                conn.close()

        tree.bind("<<TreeviewSelect>>", pilih_data)
        buttons = tk.Frame(window, bg=self.WARNA["background"])
        buttons.pack(fill=tk.X, padx=20, pady=(0, 18))
        self._buat_tombol(buttons, "Tambah / Simpan", simpan_master, utama=True).pack(
            side=tk.LEFT
        )
        self._buat_tombol(buttons, "Hapus", hapus_master).pack(side=tk.LEFT, padx=8)
        self._buat_tombol(buttons, "Bersihkan", lambda: self._bersihkan_master(tree, name_entry)).pack(
            side=tk.LEFT
        )
        muat_master()
        name_entry.focus_set()

    def _bersihkan_master(self, tree, name_entry):
        tree.selection_remove(tree.selection())
        name_entry.delete(0, tk.END)

    def buka_form_jadwal(self, id_jadwal=None):
        if not self._is_admin():
            return
        conn = self._buka_koneksi()
        if conn is None:
            return
        cursor = conn.cursor()
        pilihan = {}
        try:
            for jenis, kolom_id, kolom_nama in (
                ("kelas", "id_kelas", "nama_kelas"),
                ("mapel", "id_mapel", "nama_mapel"),
                ("guru", "id_guru", "nama_guru"),
                ("ruangan", "id_ruangan", "nama_ruangan"),
            ):
                cursor.execute(
                    f"SELECT {kolom_id}, {kolom_nama} FROM {jenis} ORDER BY {kolom_nama}"
                )
                pilihan[jenis] = cursor.fetchall()
            jadwal_lama = None
            if id_jadwal is not None:
                cursor.execute(
                    """
                    SELECT id_kelas, id_mapel, id_guru, id_ruangan, hari,
                           TIME_FORMAT(jam_mulai, '%H:%i'),
                           TIME_FORMAT(jam_selesai, '%H:%i')
                    FROM jadwal WHERE id_jadwal = %s
                    """,
                    (id_jadwal,),
                )
                jadwal_lama = cursor.fetchone()
        except mysql.connector.Error as error:
            messagebox.showerror("Data gagal dimuat", str(error), parent=self.root)
            return
        finally:
            cursor.close()
            conn.close()

        if any(not pilihan[jenis] for jenis in pilihan):
            messagebox.showwarning(
                "Data master belum lengkap",
                "Tambahkan setidaknya satu kelas, mata pelajaran, guru, dan ruangan "
                "melalui menu Data Master sebelum membuat jadwal.",
                parent=self.root,
            )
            return
        if id_jadwal is not None and jadwal_lama is None:
            messagebox.showerror("Jadwal tidak ditemukan", "Data jadwal sudah tidak tersedia.")
            return

        window = tk.Toplevel(self.root)
        window.title("Ubah Jadwal" if id_jadwal is not None else "Tambah Jadwal")
        window.resizable(False, False)
        window.configure(bg=self.WARNA["background"])
        window.transient(self.root)
        window.grab_set()
        tk.Label(
            window,
            text="Ubah jadwal pelajaran" if id_jadwal is not None else "Jadwal baru",
            bg=self.WARNA["background"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 14))

        form = tk.Frame(window, bg=self.WARNA["background"])
        form.pack(fill=tk.X, padx=22)
        pilihan_ui = {}
        nama_kolom = {
            "kelas": "Kelas",
            "mapel": "Mata pelajaran",
            "guru": "Guru pengampu",
            "ruangan": "Ruangan",
        }
        for jenis in ("kelas", "mapel", "guru", "ruangan"):
            tk.Label(
                form,
                text=nama_kolom[jenis],
                bg=self.WARNA["background"],
                fg=self.WARNA["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(0, 3))
            names = [row[1] for row in pilihan[jenis]]
            combo = ttk.Combobox(form, values=names, state="readonly", width=42)
            combo.pack(fill=tk.X, pady=(0, 10))
            pilihan_ui[jenis] = combo

        tk.Label(
            form,
            text="Hari",
            bg=self.WARNA["background"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 3))
        hari_combo = ttk.Combobox(
            form,             values=self.HARI, state="readonly", width=42
        )
        hari_combo.pack(fill=tk.X, pady=(0, 10))

        waktu_frame = tk.Frame(form, bg=self.WARNA["background"])
        waktu_frame.pack(fill=tk.X)
        waktu_entries = {}
        for key, label in (("mulai", "Jam mulai"), ("selesai", "Jam selesai")):
            cell = tk.Frame(waktu_frame, bg=self.WARNA["background"])
            cell.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            tk.Label(
                cell,
                text=label,
                bg=self.WARNA["background"],
                fg=self.WARNA["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(0, 3))
            entry = ttk.Entry(cell, font=("Segoe UI", 10))
            entry.pack(fill=tk.X, pady=(0, 14))
            waktu_entries[key] = entry

        if jadwal_lama is None:
            for combo in pilihan_ui.values():
                combo.current(0)
            hari_combo.current(0)
            waktu_entries["mulai"].insert(0, "07:00")
            waktu_entries["selesai"].insert(0, "07:45")
        else:
            old_ids = jadwal_lama[:4]
            for jenis, old_id in zip(("kelas", "mapel", "guru", "ruangan"), old_ids):
                selected = next(
                    (row[1] for row in pilihan[jenis] if row[0] == old_id), ""
                )
                pilihan_ui[jenis].set(selected)
            hari_combo.set(jadwal_lama[4])
            waktu_entries["mulai"].insert(0, str(jadwal_lama[5])[:5])
            waktu_entries["selesai"].insert(0, str(jadwal_lama[6])[:5])

        def simpan_jadwal():
            try:
                mulai = datetime.strptime(
                    waktu_entries["mulai"].get().strip(), "%H:%M"
                ).time()
                selesai = datetime.strptime(
                    waktu_entries["selesai"].get().strip(), "%H:%M"
                ).time()
            except ValueError:
                messagebox.showwarning(
                    "Format waktu salah",
                    "Gunakan format 24 jam HH:MM, misalnya 07:30.",
                    parent=window,
                )
                return
            if selesai <= mulai:
                messagebox.showwarning(
                    "Rentang waktu tidak valid",
                    "Jam selesai harus lebih akhir daripada jam mulai.",
                    parent=window,
                )
                return

            selected_ids = {}
            for jenis, combo in pilihan_ui.items():
                nama = combo.get()
                selected = next(
                    (row[0] for row in pilihan[jenis] if row[1] == nama), None
                )
                if selected is None:
                    messagebox.showwarning(
                        "Pilihan belum lengkap",
                        f"Pilih {nama_kolom[jenis].lower()} terlebih dahulu.",
                        parent=window,
                    )
                    return
                selected_ids[jenis] = selected
            hari = hari_combo.get()
            if not hari:
                messagebox.showwarning(
                    "Hari belum dipilih", "Pilih hari jadwal.", parent=window
                )
                return

            conn_save = self._buka_koneksi()
            if conn_save is None:
                return
            cursor_save = conn_save.cursor()
            try:
                cursor_save.execute(
                    """
                    SELECT id_jadwal, id_guru, id_ruangan, id_kelas
                    FROM jadwal
                    WHERE hari = %s
                      AND jam_mulai < %s AND jam_selesai > %s
                      AND (id_guru = %s OR id_ruangan = %s OR id_kelas = %s)
                      AND (%s IS NULL OR id_jadwal <> %s)
                    LIMIT 1
                    """,
                    (
                        hari,
                        selesai.strftime("%H:%M:%S"),
                        mulai.strftime("%H:%M:%S"),
                        selected_ids["guru"],
                        selected_ids["ruangan"],
                        selected_ids["kelas"],
                        id_jadwal,
                        id_jadwal,
                    ),
                )
                bentrok = cursor_save.fetchone()
                if bentrok:
                    alasan = []
                    if bentrok[1] == selected_ids["guru"]:
                        alasan.append("guru")
                    if bentrok[2] == selected_ids["ruangan"]:
                        alasan.append("ruangan")
                    if bentrok[3] == selected_ids["kelas"]:
                        alasan.append("kelas")
                    messagebox.showerror(
                        "Jadwal bentrok",
                        "Waktu tersebut bertabrakan untuk "
                        + ", ".join(alasan)
                        + ". Pilih waktu lain.",
                        parent=window,
                    )
                    return

                values = (
                    selected_ids["kelas"],
                    selected_ids["mapel"],
                    selected_ids["guru"],
                    selected_ids["ruangan"],
                    hari,
                    mulai.strftime("%H:%M:%S"),
                    selesai.strftime("%H:%M:%S"),
                )
                if id_jadwal is None:
                    cursor_save.execute(
                        """
                        INSERT INTO jadwal
                            (id_kelas, id_mapel, id_guru, id_ruangan,
                             hari, jam_mulai, jam_selesai)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        values,
                    )
                else:
                    cursor_save.execute(
                        """
                        UPDATE jadwal
                        SET id_kelas = %s, id_mapel = %s, id_guru = %s,
                            id_ruangan = %s, hari = %s, jam_mulai = %s,
                            jam_selesai = %s
                        WHERE id_jadwal = %s
                        """,
                        values + (id_jadwal,),
                    )
                conn_save.commit()
            except mysql.connector.Error as error:
                conn_save.rollback()
                messagebox.showerror(
                    "Jadwal gagal disimpan", str(error), parent=window
                )
                return
            finally:
                cursor_save.close()
                conn_save.close()

            window.destroy()
            self.muat_data()

        buttons = tk.Frame(window, bg=self.WARNA["background"])
        buttons.pack(fill=tk.X, padx=22, pady=(0, 20))
        self._buat_tombol(buttons, "Simpan jadwal", simpan_jadwal, utama=True).pack(
            side=tk.RIGHT
        )
        self._buat_tombol(buttons, "Batal", window.destroy).pack(
            side=tk.RIGHT, padx=8
        )

    def ubah_jadwal_pilihan(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Pilih jadwal", "Pilih jadwal yang ingin diubah.", parent=self.root
            )
            return
        id_jadwal = selection[0].partition("_")[2]
        self.buka_form_jadwal(id_jadwal)

    def hapus_jadwal_pilihan(self):
        if not self._is_admin():
            return
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Pilih jadwal", "Pilih jadwal yang ingin dihapus.", parent=self.root
            )
            return
        values = self.tree.item(selection[0], "values")
        if not messagebox.askyesno(
            "Konfirmasi hapus",
            f"Hapus jadwal {values[3]} untuk kelas {values[5]}?",
            parent=self.root,
        ):
            return
        conn = self._buka_koneksi()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            id_jadwal = selection[0].partition("_")[2]
            cursor.execute("DELETE FROM jadwal WHERE id_jadwal = %s", (id_jadwal,))
            conn.commit()
            self.muat_data()
        except mysql.connector.Error as error:
            conn.rollback()
            messagebox.showerror("Jadwal gagal dihapus", str(error), parent=self.root)
        finally:
            cursor.close()
            conn.close()

    def _ambil_data_laporan(self, id_kelas=None):
        conn = self._buka_koneksi()
        if conn is None:
            return None
        cursor = conn.cursor()
        try:
            query = """
                SELECT j.hari, TIME_FORMAT(j.jam_mulai, '%H:%i'),
                       TIME_FORMAT(j.jam_selesai, '%H:%i'),
                       m.nama_mapel, g.nama_guru, k.nama_kelas, r.nama_ruangan
                FROM jadwal j
                JOIN mapel m ON j.id_mapel = m.id_mapel
                JOIN guru g ON j.id_guru = g.id_guru
                JOIN kelas k ON j.id_kelas = k.id_kelas
                JOIN ruangan r ON j.id_ruangan = r.id_ruangan
            """
            params = ()
            if id_kelas is not None:
                query += " WHERE j.id_kelas = %s"
                params = (id_kelas,)
            query += """
                ORDER BY k.nama_kelas,
                         FIELD(j.hari, 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'),
                         j.jam_mulai
            """
            cursor.execute(query, params)
            return cursor.fetchall()
        except mysql.connector.Error as error:
            messagebox.showerror("Data laporan gagal dimuat", str(error), parent=self.root)
            return None
        finally:
            cursor.close()
            conn.close()

    def buka_ekspor_laporan(self):
        conn = self._buka_koneksi()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id_kelas, nama_kelas FROM kelas ORDER BY nama_kelas")
            kelas = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        window = tk.Toplevel(self.root)
        window.title("Ekspor Laporan")
        window.resizable(False, False)
        window.configure(bg=self.WARNA["background"])
        window.transient(self.root)
        window.grab_set()
        tk.Label(window, text="Ekspor jadwal",
                 bg=self.WARNA["background"], fg=self.WARNA["text"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22, pady=(20, 8))
        tk.Label(window, text="Pilih kelas dan format laporan.",
                 bg=self.WARNA["background"], fg=self.WARNA["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=22, pady=(0, 10))
        pilihan = {"Semua kelas": None}
        pilihan.update({nama: id_kelas for id_kelas, nama in kelas})
        combo = ttk.Combobox(window, values=list(pilihan), state="readonly", width=38)
        combo.set("Semua kelas")
        combo.pack(fill=tk.X, padx=22, pady=(0, 12))

        def ekspor_excel():
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill
            except ImportError:
                messagebox.showerror("Ekspor gagal",
                                     "Paket openpyxl belum terpasang.",
                                     parent=window)
                return
            rows = self._ambil_data_laporan(pilihan[combo.get()])
            if rows is None:
                return
            path = filedialog.asksaveasfilename(
                parent=window, defaultextension=".xlsx",
                filetypes=[("Excel Workbook", "*.xlsx")],
                initialfile="jadwal_pelajaran.xlsx",
            )
            if not path:
                return
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Jadwal"
            headers = ["Hari", "Mulai", "Selesai", "Mata Pelajaran",
                       "Guru", "Kelas", "Ruangan"]
            sheet.append(headers)
            for cell in sheet[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="DDEBF7")
            for row in rows:
                sheet.append(list(row))
            for column in sheet.columns:
                letter = column[0].column_letter
                sheet.column_dimensions[letter].width = min(
                    max(len(str(cell.value or "")) for cell in column) + 2, 35
                )
            workbook.save(path)
            messagebox.showinfo("Ekspor berhasil",
                                f"Laporan Excel disimpan di:\n{path}",
                                parent=window)

        def ekspor_pdf():
            try:
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import A4, landscape
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
            except ImportError:
                messagebox.showerror("Ekspor gagal",
                                     "Paket reportlab belum terpasang.",
                                     parent=window)
                return
            rows = self._ambil_data_laporan(pilihan[combo.get()])
            if rows is None:
                return
            path = filedialog.asksaveasfilename(
                parent=window, defaultextension=".pdf",
                filetypes=[("PDF Document", "*.pdf")],
                initialfile="jadwal_pelajaran.pdf",
            )
            if not path:
                return
            doc = SimpleDocTemplate(path, pagesize=landscape(A4))
            headers = ["Hari", "Mulai", "Selesai", "Mata Pelajaran",
                       "Guru", "Kelas", "Ruangan"]
            data = [headers] + [list(row) for row in rows]
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3e8b82")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            styles = getSampleStyleSheet()
            story = [Paragraph("Laporan Jadwal Pelajaran", styles["Title"]), table]
            doc.build(story)
            messagebox.showinfo("Ekspor berhasil",
                                f"Laporan PDF disimpan di:\n{path}",
                                parent=window)

        buttons = tk.Frame(window, bg=self.WARNA["background"])
        buttons.pack(fill=tk.X, padx=22, pady=(0, 20))
        self._buat_tombol(buttons, "Ekspor Excel", ekspor_excel, utama=True).pack(
            side=tk.RIGHT
        )
        self._buat_tombol(buttons, "Ekspor PDF", ekspor_pdf).pack(
            side=tk.RIGHT, padx=8
        )

    def _cari_mysql_executable(self, nama):
        path = shutil.which(nama)
        if path:
            return path
        for base in (
            r"C:\xampp\mysql\bin",
            r"C:\Program Files\MySQL\MySQL Server 8.0\bin",
            r"C:\laragon\bin\mysql",
        ):
            kandidat = os.path.join(base, nama + ".exe")
            if os.path.isfile(kandidat):
                return kandidat
            if os.path.isdir(base):
                for dirpath, _dirs, filenames in os.walk(base):
                    if nama + ".exe" in filenames:
                        return os.path.join(dirpath, nama + ".exe")
        return None

    def backup_database(self):
        if not self._is_admin():
            return
        exe = self._cari_mysql_executable("mysqldump")
        if exe is None:
            messagebox.showerror("Backup gagal",
                                 "Program mysqldump tidak ditemukan.",
                                 parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".sql",
            filetypes=[("SQL Backup", "*.sql")],
            initialfile=f"backup_jadwal_{datetime.now():%Y%m%d_%H%M%S}.sql",
        )
        if not path:
            return
        command = [exe, "-h", "localhost", "-u", "root",
                   "db_jadwal_sekolah"]
        try:
            with open(path, "wb") as output:
                subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                               check=True)
            messagebox.showinfo("Backup berhasil",
                                f"Database berhasil dicadangkan ke:\n{path}",
                                parent=self.root)
        except (OSError, subprocess.CalledProcessError) as error:
            messagebox.showerror("Backup gagal", str(error), parent=self.root)

    def restore_database(self):
        if not self._is_admin():
            return
        exe = self._cari_mysql_executable("mysql")
        if exe is None:
            messagebox.showerror("Restore gagal",
                                 "Program mysql tidak ditemukan.",
                                 parent=self.root)
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("SQL Backup", "*.sql"), ("Semua file", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Konfirmasi restore",
            "Data database saat ini akan diganti dengan isi file backup. Lanjutkan?",
            parent=self.root,
        ):
            return
        command = [exe, "-h", "localhost", "-u", "root",
                   "db_jadwal_sekolah"]
        try:
            with open(path, "rb") as sql_file:
                subprocess.run(command, stdin=sql_file, stderr=subprocess.PIPE,
                               check=True)
            self.muat_data()
            messagebox.showinfo("Restore berhasil",
                                "Database berhasil dipulihkan.",
                                parent=self.root)
        except (OSError, subprocess.CalledProcessError) as error:
            messagebox.showerror("Restore gagal", str(error), parent=self.root)

    def buka_pengaturan(self):
        window = tk.Toplevel(self.root)
        window.title("Pengaturan")
        window.resizable(False, False)
        window.configure(bg=self.WARNA["background"])
        window.transient(self.root)
        window.grab_set()
        tk.Label(window, text="Pengaturan aplikasi",
                 bg=self.WARNA["background"], fg=self.WARNA["text"],
                 font=("Segoe UI", 16, "bold")).pack(
                     anchor="w", padx=22, pady=(20, 10))
        tk.Label(window, text=f"Login: {self.current_user} ({self.current_role})",
                 bg=self.WARNA["background"], fg=self.WARNA["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=22, pady=(0, 12))
        self._buat_tombol(window, "Ekspor laporan", self.buka_ekspor_laporan).pack(
            fill=tk.X, padx=22, pady=4
        )
        self._buat_tombol(window, "Backup database", self.backup_database).pack(
            fill=tk.X, padx=22, pady=4
        )
        self._buat_tombol(window, "Restore database", self.restore_database).pack(
            fill=tk.X, padx=22, pady=4
        )
        tk.Button(window, text="Tutup", command=window.destroy,
                  bg=self.WARNA["background"], fg=self.WARNA["muted"],
                  relief=tk.FLAT, padx=12, pady=8).pack(
                      anchor="e", padx=22, pady=(12, 18))

    def buka_cetak_jadwal(self):
        conn = self._buka_koneksi()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id_kelas, nama_kelas FROM kelas ORDER BY nama_kelas")
            kelas = cursor.fetchall()
        except mysql.connector.Error as error:
            messagebox.showerror("Data kelas gagal dimuat", str(error), parent=self.root)
            return
        finally:
            cursor.close()
            conn.close()

        if not kelas:
            messagebox.showinfo(
                "Belum ada kelas",
                "Tambahkan data kelas melalui menu Data Master terlebih dahulu.",
                parent=self.root,
            )
            return

        window = tk.Toplevel(self.root)
        window.title("Cetak Jadwal per Kelas")
        window.resizable(False, False)
        window.configure(bg=self.WARNA["background"])
        window.transient(self.root)
        window.grab_set()
        tk.Label(
            window,
            text="Cetak jadwal kelas",
            bg=self.WARNA["background"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 5))
        tk.Label(
            window,
            text="Laporan akan dibuka di browser agar bisa dicetak.",
            bg=self.WARNA["background"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=22, pady=(0, 12))
        names = {name: id_kelas for id_kelas, name in kelas}
        combo = ttk.Combobox(
            window, values=list(names), state="readonly", width=38
        )
        combo.current(0)
        combo.pack(fill=tk.X, padx=22, pady=(0, 14))

        def buat_laporan():
            nama_kelas = combo.get()
            if not nama_kelas:
                messagebox.showwarning(
                    "Pilih kelas", "Pilih kelas terlebih dahulu.", parent=window
                )
                return
            conn_report = self._buka_koneksi()
            if conn_report is None:
                return
            cursor_report = conn_report.cursor()
            try:
                cursor_report.execute(
                    """
                    SELECT j.hari, TIME_FORMAT(j.jam_mulai, '%H:%i'),
                           TIME_FORMAT(j.jam_selesai, '%H:%i'),
                           m.nama_mapel, g.nama_guru, r.nama_ruangan
                    FROM jadwal j
                    JOIN mapel m ON j.id_mapel = m.id_mapel
                    JOIN guru g ON j.id_guru = g.id_guru
                    JOIN ruangan r ON j.id_ruangan = r.id_ruangan
                    WHERE j.id_kelas = %s
                    ORDER BY FIELD(j.hari, 'Senin', 'Selasa', 'Rabu',
                                   'Kamis', 'Jumat', 'Sabtu'), j.jam_mulai
                    """,
                    (names[nama_kelas],),
                )
                rows = cursor_report.fetchall()
            except mysql.connector.Error as error:
                messagebox.showerror(
                    "Laporan gagal dibuat", str(error), parent=window
                )
                return
            finally:
                cursor_report.close()
                conn_report.close()

            if not rows:
                messagebox.showinfo(
                    "Jadwal kosong",
                    f"Belum ada jadwal untuk kelas {nama_kelas}.",
                    parent=window,
                )
                return
            table_rows = "".join(
                "<tr>"
                + "".join(f"<td>{escape(str(value))}</td>" for value in row)
                + "</tr>"
                for row in rows
            )
            report = f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Jadwal {escape(nama_kelas)}</title>
<style>
body {{ font: 14px Arial, sans-serif; color: #213338; margin: 32px; }}
h1 {{ margin-bottom: 4px; }} p {{ color: #607477; margin-top: 0; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 24px; }}
th, td {{ border: 1px solid #ccd8d5; padding: 10px; text-align: left; }}
th {{ background: #e6f3f0; }}
@media print {{ body {{ margin: 12mm; }} }}
</style>
</head>
<body>
<h1>Jadwal Pelajaran</h1>
<p>Kelas {escape(nama_kelas)}</p>
<table>
<thead><tr><th>Hari</th><th>Mulai</th><th>Selesai</th>
<th>Mata Pelajaran</th><th>Guru</th><th>Ruangan</th></tr></thead>
<tbody>{table_rows}</tbody>
</table>
</body>
</html>"""
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".html", delete=False
                ) as report_file:
                    report_file.write(report)
                webbrowser.open_new_tab(Path(report_file.name).as_uri())
                messagebox.showinfo(
                    "Laporan siap",
                    "Jadwal dibuka di browser. Gunakan Ctrl+P untuk mencetak.",
                    parent=window,
                )
                window.destroy()
            except OSError as error:
                messagebox.showerror(
                    "Laporan gagal dibuka", str(error), parent=window
                )

        buttons = tk.Frame(window, bg=self.WARNA["background"])
        buttons.pack(fill=tk.X, padx=22, pady=(0, 20))
        self._buat_tombol(buttons, "Buka laporan", buat_laporan, utama=True).pack(
            side=tk.RIGHT
        )
        self._buat_tombol(buttons, "Batal", window.destroy).pack(
            side=tk.RIGHT, padx=8
        )

    def _buat_kartu_ringkasan(self, parent, judul, nilai, catatan, warna):
        card = tk.Frame(
            parent,
            bg=self.WARNA["surface"],
            highlightthickness=1,
            highlightbackground=self.WARNA["border"],
        )
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        accent = tk.Frame(card, bg=warna, width=4)
        accent.pack(side=tk.LEFT, fill=tk.Y)
        body = tk.Frame(card, bg=self.WARNA["surface"])
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=13)
        tk.Label(
            body,
            text=judul,
            bg=self.WARNA["surface"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        value_label = tk.Label(
            body,
            text=nilai,
            bg=self.WARNA["surface"],
            fg=self.WARNA["text"],
            font=("Segoe UI", 21, "bold"),
        )
        value_label.pack(anchor="w", pady=(4, 0))
        tk.Label(
            body,
            text=catatan,
            bg=self.WARNA["surface"],
            fg=self.WARNA["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(1, 0))
        return value_label

    def _buat_filter_hari(self, teks, hari):
        button = tk.Button(
            self.selector_frame,
            text=teks,
            command=lambda h=hari: self.pilih_hari(h),
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            bg=self.WARNA["accent_light"] if hari is None else self.WARNA["surface"],
            fg=self.WARNA["accent"] if hari is None else self.WARNA["muted"],
            activebackground=self.WARNA["accent_light"],
            activeforeground=self.WARNA["accent"],
        )
        button.pack(side=tk.LEFT, padx=3)
        self.hari_buttons[hari] = button

    def pilih_hari(self, hari):
        self.hari_aktif = hari
        for key, button in self.hari_buttons.items():
            aktif = key == hari
            button.configure(
                bg=self.WARNA["accent_light"] if aktif else self.WARNA["surface"],
                fg=self.WARNA["accent"] if aktif else self.WARNA["muted"],
            )
        self._tampilkan_baris()

    def _filter_kelas_berubah(self, _event=None):
        selected = self.kelas_filter.get()
        self.kelas_aktif = None if selected == "Semua kelas" else selected
        self._tampilkan_baris()

    def reset_filter(self):
        self.kelas_filter.set("Semua kelas")
        self.kelas_aktif = None
        self.pilih_hari(None)

    def muat_data(self):
        conn = self._buka_koneksi()
        if conn is None:
            return

        cursor = conn.cursor()
        query = """
            SELECT j.id_jadwal, j.hari, CONCAT(j.jam_mulai, ' - ', j.jam_selesai),
                   m.nama_mapel, g.nama_guru, k.nama_kelas, r.nama_ruangan
            FROM jadwal j
            JOIN mapel m ON j.id_mapel = m.id_mapel
            JOIN guru g ON j.id_guru = g.id_guru
            JOIN kelas k ON j.id_kelas = k.id_kelas
            JOIN ruangan r ON j.id_ruangan = r.id_ruangan
            ORDER BY FIELD(j.hari, 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'),
                     j.jam_mulai
        """
        try:
            cursor.execute(query)
            self.semua_data = cursor.fetchall()
            self._perbarui_ringkasan()
            self._tampilkan_baris()
        except mysql.connector.Error as error:
            messagebox.showerror(
                "Data gagal dimuat",
                f"Terjadi masalah saat membaca jadwal dari database:\n{error}",
                parent=self.root,
            )
        finally:
            cursor.close()
            conn.close()

    def _perbarui_ringkasan(self):
        hari_aktif = {row[1] for row in self.semua_data}
        mapel_aktif = {row[3] for row in self.semua_data}
        kelas_tersedia = sorted({row[5] for row in self.semua_data})
        pilihan_kelas = ["Semua kelas"] + kelas_tersedia
        kelas_terpilih = self.kelas_filter.get()
        if kelas_terpilih not in pilihan_kelas:
            kelas_terpilih = "Semua kelas"
        self.kelas_filter.configure(values=pilihan_kelas)
        self.kelas_filter.set(kelas_terpilih)
        self.kelas_aktif = (
            None if kelas_terpilih == "Semua kelas" else kelas_terpilih
        )
        self.total_value.configure(text=str(len(self.semua_data)))
        self.hari_value.configure(text=str(len(hari_aktif)))
        self.mapel_value.configure(text=str(len(mapel_aktif)))

    def _tampilkan_baris(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        rows = [
            row for row in self.semua_data
            if (self.hari_aktif is None or row[1] == self.hari_aktif)
            and (self.kelas_aktif is None or row[5] == self.kelas_aktif)
        ]
        nomor_per_kelas_hari = {}
        for index, row in enumerate(rows):
            key = (row[5], row[1])
            nomor_per_kelas_hari[key] = nomor_per_kelas_hari.get(key, 0) + 1
            nilai_tampilan = (nomor_per_kelas_hari[key],) + tuple(row[1:])
            tag = "evenrow" if index % 2 == 0 else "oddrow"
            self.tree.insert(
                "",
                tk.END,
                iid=f"jadwal_{row[0]}",
                values=nilai_tampilan,
                tags=(tag,),
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = AplikasiJadwalKelas(root)
    root.mainloop()
