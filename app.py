from flask import Flask, render_template, request, jsonify
from models import init_db, add_device, add_link, get_devices_by_map, get_links_by_map, create_map, get_maps, delete_map, update_map
from snmp_handler import SNMPHandler
import ipaddress
import threading

app = Flask(__name__)

# Initialize DB on startup
init_db()

# Simple in-memory log storage
scan_logs = {} # {map_id: [logs...]}
scan_active = {} # {map_id: bool}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/maps', methods=['GET'])
def list_maps():
    maps = get_maps()
    return jsonify(maps)

@app.route('/api/maps', methods=['POST'])
def create_new_map():
    data = request.json
    name = data.get('name')
    network = data.get('network')
    community = data.get('community')
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    new_id = create_map(name)
    if network or community:
        update_map(new_id, name, network, community)
    return jsonify({'id': new_id, 'name': name})

@app.route('/api/maps/<int:map_id>', methods=['PUT'])
def edit_map(map_id):
    data = request.json
    name = data.get('name')
    network = data.get('network')
    community = data.get('community')
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    update_map(map_id, name, network, community)
    return jsonify({'status': 'updated'})

@app.route('/api/maps/<int:map_id>', methods=['DELETE'])
def remove_map(map_id):
    delete_map(map_id)
    return jsonify({'status': 'deleted'})

@app.route('/scan', methods=['POST'])
def scan_network():
    data = request.json
    network = data.get('network') # e.g., 192.168.1.0/24
    community = data.get('community')
    map_id = data.get('map_id', 1)
    
    if not network or not community:
        return jsonify({'error': 'Missing network or community'}), 400

    if scan_active.get(map_id, False):
         return jsonify({'error': 'Scan already in progress for this map'}), 409

    # Save settings to map record for future rescans
    maps = get_maps()
    m = next((x for x in maps if x['id'] == map_id), None)
    if m:
        update_map(map_id, m['name'], network, community)

    # Initialize logs for map if needed
    scan_logs[map_id] = []
    log_message(map_id, f"Starting scan for {network} on Map {map_id}")
    scan_active[map_id] = True

    # Start scan in a separate thread to not block UI
    thread = threading.Thread(target=perform_scan, args=(map_id, network, community))
    thread.start()

    return jsonify({'status': 'Scan started', 'message': f'Scanning {network} with community {community}'})

@app.route('/scan/stop', methods=['POST'])
def stop_scan():
    data = request.json
    map_id = data.get('map_id', 1)
    
    if map_id in scan_active and scan_active[map_id]:
        scan_active[map_id] = False # Signal to stop
        log_message(map_id, "Stopping scan...")
        return jsonify({'status': 'Stopping', 'message': 'Scan stop requested.'})
    
    return jsonify({'error': 'No active scan for this map'}), 400

@app.route('/api/maps/<int:map_id>/rescan', methods=['POST'])
def rescan_map(map_id):
    maps = get_maps()
    m = next((x for x in maps if x['id'] == map_id), None)
    if not m or not m.get('network') or not m.get('community'):
         return jsonify({'error': 'Map has no saved scan settings'}), 400

    if scan_active.get(map_id, False):
         return jsonify({'error': 'Scan already in progress for this map'}), 409

    scan_logs[map_id] = []
    log_message(map_id, f"Rescanning {m['network']} on Map {map_id}")
    scan_active[map_id] = True
    thread = threading.Thread(target=perform_scan, args=(map_id, m['network'], m['community']))
    thread.start()
    return jsonify({'status': 'Rescan started'})

@app.route('/api/devices')
def get_devices():
    map_id = request.args.get('map_id', 1, type=int)
    devices = get_devices_by_map(map_id)
    links = get_links_by_map(map_id)
    return jsonify({'nodes': devices, 'edges': links})

@app.route('/api/logs')
def get_logs():
    map_id = request.args.get('map_id', 1, type=int)
    logs = scan_logs.get(map_id, [])
    active = scan_active.get(map_id, False)
    return jsonify({'logs': logs, 'active': active})

def log_message(map_id, msg):
    print(f"[Map {map_id}] {msg}")
    if map_id not in scan_logs:
        scan_logs[map_id] = []
    scan_logs[map_id].append(msg)

from concurrent.futures import ThreadPoolExecutor

def perform_scan(map_id, network_cidr, community_string):
    log_message(map_id, f"Starting optimized parallel scan for {network_cidr}")
    
    # Parse comma-separated communities
    communities = [c.strip() for c in community_string.split(',') if c.strip()]
    if not communities:
        communities = ['public']

    scanned_ips = set()
    scanned_ips_lock = threading.Lock()
    
    scan_active[map_id] = True
    
    def scan_ip_worker(ip_str):
        if not scan_active.get(map_id, False):
            return []

        # Try to find a working community
        valid_snmp = None
        sys_info = None
        
        for comm in communities:
            snmp = SNMPHandler(comm)
            sys_info = snmp.get_system_info(ip_str)
            if sys_info:
                valid_snmp = snmp
                break
        
        if sys_info and valid_snmp:
            log_message(map_id, f"Found device: {sys_info['sysName']} ({ip_str})")
            
            # Use lock for DB calls if they share connections (add_device uses its own)
            add_device(map_id, ip_str, sys_info['sysName'], sys_info['sysDescr'], sys_info['sysObjectID'])
            
            # Get Neighbors via LLDP and recurse
            neighbors = valid_snmp.get_neighbors_details(ip_str)
            
            # Fetch STP Root Port
            stp_root_port = valid_snmp.get_stp_root_port(ip_str)

            found_neighbor_ips = []
            for neighbor in neighbors:
                n_ip = neighbor.get('ip')
                local_port = neighbor.get('local_port', 'Unknown') 
                remote_port = neighbor.get('remote_port', 'Unknown') 
                n_type = neighbor.get('device_type', 'router')

                if n_ip:
                     log_message(map_id, f"  Found Link: {ip_str} -> {n_ip} ({n_type})")
                     
                     sys_name = neighbor.get('sys_name', "Unknown")
                     add_device(map_id, n_ip, sys_name, "Discovered via LLDP", "Unknown", device_type=n_type)

                     # Fetch Speed, Status and VLAN
                     speed = ""
                     status = "Unknown"
                     source_vlan = None
                     source_is_root = 0
                     
                     if 'local_port_index' in neighbor:
                         speed = valid_snmp.get_interface_speed(ip_str, neighbor['local_port_index'])
                         status = valid_snmp.get_interface_status(ip_str, neighbor['local_port_index'])
                         source_vlan = valid_snmp.get_port_vlan_details(ip_str, neighbor['local_port_index'])
                         
                         if stp_root_port and int(neighbor['local_port_index']) == stp_root_port:
                             source_is_root = 1
                    
                     add_link(map_id, ip_str, n_ip, "LLDP", source_port=local_port, target_port=remote_port, speed=speed, status=status, source_vlan=source_vlan, source_is_root=source_is_root)
                     found_neighbor_ips.append(n_ip)
            
            return found_neighbor_ips
        return []

    try:
        # Initial candidates
        initial_ips = []
        if '/' in network_cidr:
            network = ipaddress.ip_network(network_cidr, strict=False)
            initial_ips = [str(ip) for ip in network.hosts()]
        else:
            initial_ips = [network_cidr]

        with ThreadPoolExecutor(max_workers=50) as executor:
            to_process = initial_ips
            while to_process:
                if not scan_active.get(map_id, False):
                    break

                # Filter out already scanned
                with scanned_ips_lock:
                    current_batch = [ip for ip in to_process if ip not in scanned_ips]
                    for ip in current_batch:
                        scanned_ips.add(ip)

                if not current_batch:
                    break

                # Map batch to workers
                log_message(map_id, f"Probing {len(current_batch)} IPs in parallel...")
                results = list(executor.map(scan_ip_worker, current_batch))
                
                # Collect new IPs found via LLDP
                next_batch = []
                for neighbors_found in results:
                    next_batch.extend(neighbors_found)
                
                to_process = next_batch

        log_message(map_id, "Scan complete.")
    except Exception as e:
        log_message(map_id, f"Scan Error: {str(e)}")
    finally:
        scan_active[map_id] = False

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5050)
