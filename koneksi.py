import mysql.connector

def buat_koneksi():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="db_jadwal_sekolah",
            use_pure=True,
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Koneksi ke database gagal: {err}")
        return None