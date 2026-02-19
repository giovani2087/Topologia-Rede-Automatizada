import sqlite3
import os

DB_NAME = "network_map.db"

def init_db():
    # Remove the check 'if not os.path.exists(DB_NAME)' so we always check/migrate
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Maps table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Devices table (added map_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            ip TEXT,
            map_id INTEGER,
            sysName TEXT,
            sysDescr TEXT,
            sysObjectID TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ip, map_id),
            FOREIGN KEY(map_id) REFERENCES maps(id)
        )
    ''')

    # Links table (added map_id, speed, status)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER,
            source_ip TEXT,
            target_ip TEXT,
            source_port TEXT,
            target_port TEXT,
            protocol TEXT,
            speed TEXT,
            status TEXT,
            source_vlan TEXT,
            target_vlan TEXT,
            source_is_root INTEGER DEFAULT 0,
            target_is_root INTEGER DEFAULT 0,
            FOREIGN KEY(source_ip, map_id) REFERENCES devices(ip, map_id),
            FOREIGN KEY(map_id) REFERENCES maps(id)
        )
    ''')
    
    # Migrations for existing tables if needed
    cursor.execute("PRAGMA table_info(maps)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'network' not in columns:
        cursor.execute("ALTER TABLE maps ADD COLUMN network TEXT")
    if 'community' not in columns:
        cursor.execute("ALTER TABLE maps ADD COLUMN community TEXT")

    cursor.execute("PRAGMA table_info(links)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'map_id' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN map_id INTEGER DEFAULT 1")
    if 'speed' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN speed TEXT")
    if 'status' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN status TEXT")
    if 'source_vlan' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN source_vlan TEXT")
    if 'target_vlan' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN target_vlan TEXT")
    if 'source_is_root' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN source_is_root INTEGER DEFAULT 0")
    if 'target_is_root' not in columns:
        cursor.execute("ALTER TABLE links ADD COLUMN target_is_root INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()
    print(f"Database {DB_NAME} initialized/checked.")

def create_map(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO maps (name) VALUES (?)", (name,))
        new_id = cursor.lastrowid
        conn.commit()
        return new_id
    finally:
        conn.close()

def get_maps():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM maps ORDER BY created_at DESC")
    maps = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return maps

def delete_map(map_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Delete links and devices first due to FK constraints if any (though SQLite FKs often off by default)
        cursor.execute("DELETE FROM links WHERE map_id = ?", (map_id,))
        cursor.execute("DELETE FROM devices WHERE map_id = ?", (map_id,))
        cursor.execute("DELETE FROM maps WHERE id = ?", (map_id,))
        conn.commit()
    finally:
        conn.close()

def update_map(map_id, name, network=None, community=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        if network is not None and community is not None:
            cursor.execute("UPDATE maps SET name = ?, network = ?, community = ? WHERE id = ?", 
                           (name, network, community, map_id))
        else:
            cursor.execute("UPDATE maps SET name = ? WHERE id = ?", (name, map_id))
        conn.commit()
    finally:
        conn.close()

def add_device(map_id, ip, sysName, sysDescr, sysObjectID, device_type='router'):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        if sysName and sysName != 'Unknown':
            cursor.execute('''
                INSERT INTO devices (ip, map_id, sysName, sysDescr, sysObjectID, last_seen, device_type)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(ip, map_id) DO UPDATE SET
                    sysName=excluded.sysName,
                    sysDescr=excluded.sysDescr,
                    sysObjectID=excluded.sysObjectID,
                    last_seen=CURRENT_TIMESTAMP,
                    device_type=excluded.device_type
            ''', (ip, map_id, sysName, sysDescr, sysObjectID, device_type))
        else:
            # Only update type if it's not unknown
            cursor.execute('''
                INSERT INTO devices (ip, map_id, sysName, sysDescr, sysObjectID, last_seen, device_type)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(ip, map_id) DO UPDATE SET
                    last_seen=CURRENT_TIMESTAMP,
                    device_type=CASE WHEN excluded.device_type != 'router' THEN excluded.device_type ELSE devices.device_type END
            ''', (ip, map_id, sysName, sysDescr, sysObjectID, device_type))
        conn.commit()
    except Exception as e:
        print(f"Error adding device {ip}: {e}")
    finally:
        conn.close()

import threading

DB_LOCK = threading.Lock()

def add_link(map_id, source_ip, target_ip, protocol, source_port=None, target_port=None, speed=None, status=None, source_vlan=None, target_vlan=None, source_is_root=0, target_is_root=0):
    with DB_LOCK:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            # Normalize direction: Always store/search as smaller_ip -> larger_ip
            if source_ip < target_ip:
                u_source, u_target = source_ip, target_ip
                u_src_port, u_tgt_port = source_port, target_port
                u_src_vlan, u_tgt_vlan = source_vlan, target_vlan
                u_src_root, u_tgt_root = source_is_root, target_is_root
            else:
                u_source, u_target = target_ip, source_ip
                u_src_port, u_tgt_port = target_port, source_port
                u_src_vlan, u_tgt_vlan = target_vlan, source_vlan
                u_src_root, u_tgt_root = target_is_root, source_is_root
            
            # Check if this link exists (direction-agnostic due to normalization)
            cursor.execute('''
                SELECT id FROM links 
                WHERE map_id = ? AND source_ip = ? AND target_ip = ?
            ''', (map_id, u_source, u_target))
            existing_link = cursor.fetchone()
            
            if existing_link:
                # Update existing link
                # print(f"DEBUG: Link exists {u_source}->{u_target}. Updating...")
                
                updates = []
                params = []
                if u_src_port and u_src_port != 'Unknown': 
                    updates.append("source_port = ?")
                    params.append(u_src_port)
                if u_tgt_port and u_tgt_port != 'Unknown': 
                    updates.append("target_port = ?")
                    params.append(u_tgt_port)
                if speed and speed != '':
                    updates.append("speed = ?")
                    params.append(speed)
                if status and status != 'Unknown':
                    updates.append("status = ?")
                    params.append(status)
                if u_src_vlan and u_src_vlan != '':
                    updates.append("source_vlan = ?")
                    params.append(str(u_src_vlan))
                if u_tgt_vlan and u_tgt_vlan != '':
                    updates.append("target_vlan = ?")
                    params.append(str(u_tgt_vlan))
                
                updates.append("source_is_root = ?")
                params.append(u_src_root)
                updates.append("target_is_root = ?")
                params.append(u_tgt_root)
                
                if updates:
                    sql = f"UPDATE links SET {', '.join(updates)} WHERE id = ?"
                    params.append(existing_link[0])
                    cursor.execute(sql, tuple(params))
                    conn.commit()
            else:
                # Insert new link
                # print(f"DEBUG: Inserting link {u_source} -> {u_target} (Speed: {speed})")
                cursor.execute('''
                    INSERT INTO links (map_id, source_ip, target_ip, protocol, source_port, target_port, speed, status, source_vlan, target_vlan, source_is_root, target_is_root)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (map_id, u_source, u_target, protocol, u_src_port, u_tgt_port, speed, status, u_src_vlan, u_tgt_vlan, u_src_root, u_tgt_root))
                conn.commit()
                # print("DEBUG: Link inserted.")

        except Exception as e:
            print(f"Error adding link {source_ip}->{target_ip}: {e}")
        finally:
            conn.close()

def get_devices_by_map(map_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices WHERE map_id = ?", (map_id,))
    devices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return devices

def get_links_by_map(map_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM links WHERE map_id = ?", (map_id,))
    links = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return links

