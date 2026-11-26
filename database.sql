CREATE DATABASE IF NOT EXISTS db_jadwal_sekolah
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE db_jadwal_sekolah;

CREATE TABLE IF NOT EXISTS pengguna (
    id_pengguna INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    nama_lengkap VARCHAR(120) NOT NULL,
    role ENUM('admin', 'operator') NOT NULL DEFAULT 'operator'
) ENGINE=InnoDB;

-- Akun awal: username admin, password awal admin.
INSERT INTO pengguna (username, password_hash, salt, nama_lengkap, role)
SELECT 'admin', '2725c4e4a3148c81b3a7ad94ce59b2f22effa5d7c1a6bd35a348497fc99d3a5a',
       'jadwal2026', 'Administrator', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM pengguna WHERE username = 'admin');

UPDATE pengguna
SET password_hash = '2725c4e4a3148c81b3a7ad94ce59b2f22effa5d7c1a6bd35a348497fc99d3a5a',
    salt = 'jadwal2026',
    nama_lengkap = 'Administrator',
    role = 'admin'
WHERE username = 'admin'
  AND password_hash LIKE 'hash_password_%';

CREATE TABLE IF NOT EXISTS guru (
    id_guru INT AUTO_INCREMENT PRIMARY KEY,
    nama_guru VARCHAR(120) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS kelas (
    id_kelas INT AUTO_INCREMENT PRIMARY KEY,
    nama_kelas VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mapel (
    id_mapel INT AUTO_INCREMENT PRIMARY KEY,
    nama_mapel VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ruangan (
    id_ruangan INT AUTO_INCREMENT PRIMARY KEY,
    nama_ruangan VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS jadwal (
    id_jadwal INT AUTO_INCREMENT PRIMARY KEY,
    id_kelas INT NOT NULL,
    id_mapel INT NOT NULL,
    id_guru INT NOT NULL,
    id_ruangan INT NOT NULL,
    hari ENUM('Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu') NOT NULL,
    jam_mulai TIME NOT NULL,
    jam_selesai TIME NOT NULL,
    CONSTRAINT chk_jadwal_waktu CHECK (jam_selesai > jam_mulai),
    CONSTRAINT fk_jadwal_kelas FOREIGN KEY (id_kelas)
        REFERENCES kelas (id_kelas) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_jadwal_mapel FOREIGN KEY (id_mapel)
        REFERENCES mapel (id_mapel) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_jadwal_guru FOREIGN KEY (id_guru)
        REFERENCES guru (id_guru) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_jadwal_ruangan FOREIGN KEY (id_ruangan)
        REFERENCES ruangan (id_ruangan) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_jadwal_hari_waktu (hari, jam_mulai, jam_selesai),
    INDEX idx_jadwal_guru (id_guru),
    INDEX idx_jadwal_kelas (id_kelas),
    INDEX idx_jadwal_ruangan (id_ruangan)
) ENGINE=InnoDB;

-- Migrate jadwal lama tanpa menghapus data yang sudah ada.
SET @schema_name = DATABASE();

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = @schema_name AND table_name = 'jadwal'
       AND column_name = 'id_kelas') = 0,
    'ALTER TABLE jadwal ADD COLUMN id_kelas INT NULL AFTER id_jadwal',
    'SET @migration_noop = 1'
);
PREPARE migration_stmt FROM @sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = @schema_name AND table_name = 'jadwal'
       AND column_name = 'id_ruangan') = 0,
    'ALTER TABLE jadwal ADD COLUMN id_ruangan INT NULL AFTER id_guru',
    'SET @migration_noop = 1'
);
PREPARE migration_stmt FROM @sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

INSERT INTO kelas (nama_kelas)
SELECT 'XI RPL 2'
WHERE NOT EXISTS (SELECT 1 FROM kelas WHERE nama_kelas = 'XI RPL 2');

INSERT INTO ruangan (nama_ruangan)
SELECT 'Ruang RPL 2'
WHERE NOT EXISTS (SELECT 1 FROM ruangan WHERE nama_ruangan = 'Ruang RPL 2');

SET @default_class_id = (
    SELECT id_kelas FROM kelas WHERE nama_kelas = 'XI RPL 2' ORDER BY id_kelas LIMIT 1
);
SET @default_room_id = (
    SELECT id_ruangan FROM ruangan
    WHERE nama_ruangan = 'Ruang RPL 2' ORDER BY id_ruangan LIMIT 1
);
UPDATE jadwal SET id_kelas = @default_class_id WHERE id_kelas IS NULL;
UPDATE jadwal j
JOIN kelas k ON k.id_kelas = j.id_kelas
JOIN ruangan old_room ON old_room.id_ruangan = j.id_ruangan
SET j.id_ruangan = @default_room_id
WHERE k.nama_kelas = 'XI RPL 2'
  AND old_room.nama_ruangan = 'Belum ditentukan';
UPDATE jadwal SET id_ruangan = @default_room_id WHERE id_ruangan IS NULL;
DELETE FROM ruangan
WHERE nama_ruangan = 'Belum ditentukan'
  AND NOT EXISTS (
      SELECT 1 FROM jadwal WHERE jadwal.id_ruangan = ruangan.id_ruangan
  );
ALTER TABLE jadwal MODIFY id_kelas INT NOT NULL;
ALTER TABLE jadwal MODIFY id_ruangan INT NOT NULL;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics
     WHERE table_schema = @schema_name AND table_name = 'jadwal'
       AND index_name = 'idx_jadwal_kelas') = 0,
    'ALTER TABLE jadwal ADD INDEX idx_jadwal_kelas (id_kelas)',
    'SET @migration_noop = 1'
);
PREPARE migration_stmt FROM @sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics
     WHERE table_schema = @schema_name AND table_name = 'jadwal'
       AND index_name = 'idx_jadwal_ruangan') = 0,
    'ALTER TABLE jadwal ADD INDEX idx_jadwal_ruangan (id_ruangan)',
    'SET @migration_noop = 1'
);
PREPARE migration_stmt FROM @sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.table_constraints
     WHERE constraint_schema = @schema_name AND table_name = 'jadwal'
       AND constraint_name = 'fk_jadwal_kelas') = 0,
    CONCAT(
        'ALTER TABLE jadwal ADD CONSTRAINT fk_jadwal_kelas ',
        'FOREIGN KEY (id_kelas) REFERENCES kelas (id_kelas) ',
        'ON UPDATE CASCADE ON DELETE RESTRICT'
    ),
    'SET @migration_noop = 1'
);
PREPARE migration_stmt FROM @sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.table_constraints
     WHERE constraint_schema = @schema_name AND table_name = 'jadwal'
       AND constraint_name = 'fk_jadwal_ruangan') = 0,
    CONCAT(
        'ALTER TABLE jadwal ADD CONSTRAINT fk_jadwal_ruangan ',
        'FOREIGN KEY (id_ruangan) REFERENCES ruangan (id_ruangan) ',
        'ON UPDATE CASCADE ON DELETE RESTRICT'
    ),
    'SET @migration_noop = 1'
);
PREPARE migration_stmt FROM @sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;