import sys
import importlib
if sys.version_info >= (3, 12):
    import importlib.metadata
    import importlib.util
    # Monkey patch for pysnmp which uses 'imp'
    import types
    sys.modules['imp'] = types.ModuleType('imp')
    import imp
    imp.reload = importlib.reload

from pysnmp.hlapi import *
import ipaddress

def str_to_tuple(oid_str):
    """Converts a string OID to a tuple of integers for pysnmp to avoid MIB lookups."""
    try:
        return tuple(int(x) for x in oid_str.strip('.').split('.'))
    except:
        return tuple()

class SNMPHandler:
    def __init__(self, community):
        self.community = community

    def get_system_info(self, ip):
        """Retrieves system name, description, and OID."""
        try:
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1), # SNMP v2c
                       UdpTransportTarget((ip, 161), timeout=1.5, retries=1),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple('1.3.6.1.2.1.1.5.0'))),
                       ObjectType(ObjectIdentity(str_to_tuple('1.3.6.1.2.1.1.1.0'))),
                       ObjectType(ObjectIdentity(str_to_tuple('1.3.6.1.2.1.1.2.0'))))
            )

            if errorIndication:
                print(f"SNMP Error for {ip}: {errorIndication}")
                return None
            elif errorStatus:
                print(f"SNMP Error for {ip}: {errorStatus.prettyPrint()}")
                return None
            else:
                return {
                    'sysName': str(varBinds[0][1]),
                    'sysDescr': str(varBinds[1][1]),
                    'sysObjectID': str(varBinds[2][1])
                }
        except Exception as e:
            print(f"Exception during SNMP get for {ip}: {e}")
            return None

    def get_neighbors_details(self, ip):
        """
        Retrieves LLDP neighbors with IPs and Port details.
        Returns: [{'ip': 'x.x.x.x', 'local_port': 'Gi1/0/1', 'remote_port': 'Fa0/1', ...}]
        """
        neighbors = []
        
        try:
            # 1. Fetch lldpRemPortId (.7)
            remote_ports = {} 
            # 1b. Fetch lldpRemSysCapEnabled (.12)
            remote_caps = {} # {(local, remote): [caps]}

            # Let's walk lldpRemSysCapEnabled 1.0.8802.1.1.2.1.4.1.1.12
            try:
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    SnmpEngine(),
                    CommunityData(self.community, mpModel=1),
                    UdpTransportTarget((ip, 161), timeout=3, retries=2),
                    ContextData(),
                    ObjectType(ObjectIdentity(str_to_tuple('1.0.8802.1.1.2.1.4.1.1.12'))), 
                    lexicographicMode=False
                ):
                    if errorIndication or errorStatus: break
                    for varBind in varBinds:
                        oid, value = varBind
                        try:
                            oid_list = list(oid)
                            if len(oid_list) >= 14:
                                local_port_num = oid_list[12]
                                remote_index = oid_list[13]
                                
                                val_str = value.prettyPrint().strip()
                                current_caps = []
                                
                                if val_str.lower().startswith('0x'):
                                    try:
                                        hex_val = val_str[2:]
                                        if len(hex_val) >= 2:
                                            byte1 = int(hex_val[:2], 16)
                                            if byte1 & 0x20: current_caps.append("Bridge")
                                            if byte1 & 0x10: current_caps.append("WLAN AP")
                                            if byte1 & 0x08: current_caps.append("Router")
                                            if byte1 & 0x01: current_caps.append("Station")
                                    except: pass
                                else:
                                    if 'wlan' in val_str.lower() or 'accesspoint' in val_str.lower(): current_caps.append("WLAN AP")
                                    if 'router' in val_str.lower(): current_caps.append("Router")
                                    if 'bridge' in val_str.lower(): current_caps.append("Bridge")
                                    if 'station' in val_str.lower(): current_caps.append("Station")
                                    
                                remote_caps[(local_port_num, remote_index)] = current_caps
                        except: pass
            except: pass


            # 2. Fetch lldpRemPortId (1.0.8802.1.1.2.1.4.1.1.7) for Remote Port Names
            try:
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    SnmpEngine(),
                    CommunityData(self.community, mpModel=1),
                    UdpTransportTarget((ip, 161), timeout=3, retries=2),
                    ContextData(),
                    ObjectType(ObjectIdentity(str_to_tuple('1.0.8802.1.1.2.1.4.1.1.7'))),
                    lexicographicMode=False
                ):
                    if errorIndication or errorStatus: break
                    for varBind in varBinds:
                        oid, value = varBind
                        try:
                            oid_list = list(oid)
                            if len(oid_list) >= 14:
                                local_port_num = oid_list[12]
                                remote_index = oid_list[13]
                                remote_ports[(local_port_num, remote_index)] = str(value)
                        except: pass
            except: pass

            # 3. Fetch lldpRemSysName (1.0.8802.1.1.2.1.4.1.1.9)
            remote_sysnames = {}
            try:
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    SnmpEngine(),
                    CommunityData(self.community, mpModel=1),
                    UdpTransportTarget((ip, 161), timeout=3, retries=2),
                    ContextData(),
                    ObjectType(ObjectIdentity(str_to_tuple('1.0.8802.1.1.2.1.4.1.1.9'))),
                    lexicographicMode=False
                ):
                    if errorIndication or errorStatus: break
                    for varBind in varBinds:
                        oid, value = varBind
                        try:
                            oid_list = list(oid)
                            if len(oid_list) >= 14:
                                local_port_num = oid_list[12]
                                remote_index = oid_list[13]
                                remote_sysnames[(local_port_num, remote_index)] = str(value)
                        except: pass
            except: pass

            # 4. Fetch lldpRemManAddr (Management IP) and correlate
            try:
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    SnmpEngine(),
                    CommunityData(self.community, mpModel=1),
                    UdpTransportTarget((ip, 161), timeout=3, retries=2),
                    ContextData(),
                    ObjectType(ObjectIdentity(str_to_tuple('1.0.8802.1.1.2.1.4.2.1.3'))),
                    lexicographicMode=False
                ):
                    if errorIndication or errorStatus: break
                    for varBind in varBinds:
                        oid, value = varBind
                        try:
                            oid_list = list(oid)
                            if len(oid_list) >= 16:
                                local_port_num = oid_list[12]
                                remote_index = oid_list[13]
                                subtype = oid_list[14]
                                addr_len = oid_list[15]
                                
                                if subtype == 1 and addr_len == 4 and len(oid_list) >= 16+4:
                                    ip_bytes = oid_list[16:16+4]
                                    ip_addr = ".".join(map(str, ip_bytes))
                                    
                                    local_port_name = self.get_interface_name(ip, local_port_num)
                                    remote_port_name = remote_ports.get((local_port_num, remote_index), "Unknown")
                                    caps = remote_caps.get((local_port_num, remote_index), [])
                                    sys_name = remote_sysnames.get((local_port_num, remote_index), "Unknown")

                                    device_type = 'router'
                                    if 'WLAN AP' in caps: device_type = 'access_point'
                                    elif 'Bridge' in caps: device_type = 'switch'
                                    elif 'Station' in caps and 'Router' not in caps: device_type = 'server'
                                    
                                    neighbors.append({
                                        'sys_name': sys_name,
                                        'ip': ip_addr, 
                                        'local_port': local_port_name,
                                        'local_port_index': local_port_num,
                                        'remote_port': remote_port_name,
                                        'device_type': device_type,
                                        'capabilities': caps
                                    })
                        except: pass
            except: pass
                        
        except Exception as e:
            print(f"Error fetching LLDP neighbors for {ip}: {e}")
        
        return neighbors

    def get_interface_name(self, ip, interface_index):
        """Resolves interface index to name (e.g., Gi0/1)."""
        name = str(interface_index)
        try:
             errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1),
                       UdpTransportTarget((ip, 161), timeout=3.0, retries=2),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.31.1.1.1.1.{interface_index}'))))
            )
             if not errorIndication and not errorStatus and varBinds:
                 name = str(varBinds[0][1])
                 if not name: raise Exception()
        except:
            try:
                errorIndication, errorStatus, errorIndex, varBinds = next(
                   getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1),
                       UdpTransportTarget((ip, 161), timeout=3.0, retries=2),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.2.2.1.2.{interface_index}'))))
                )
                if not errorIndication and not errorStatus and varBinds:
                    name = str(varBinds[0][1])
            except: pass
        return name

    def get_interface_speed(self, ip, interface_index):
        print(f"DEBUG: Fetching Speed for {ip} Index {interface_index}")
        speed_str = ""
        try:
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1),
                       UdpTransportTarget((ip, 161), timeout=3.0, retries=2),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.31.1.1.1.15.{interface_index}'))))
            )
            if not errorIndication and not errorStatus and varBinds:
                val = varBinds[0][1]
                if val is not None:
                    high_speed_mbps = int(val)
                    if high_speed_mbps > 0:
                        if high_speed_mbps >= 1000:
                            speed_str = f"{high_speed_mbps/1000} Gbps"
                        else:
                            speed_str = f"{high_speed_mbps} Mbps"
                        return speed_str
        except: pass

        try:
            errorIndication, errorStatus, errorIndex, varBinds = next(
               getCmd(SnmpEngine(),
                   CommunityData(self.community, mpModel=1),
                   UdpTransportTarget((ip, 161), timeout=3.0, retries=2),
                   ContextData(),
                   ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.2.2.1.5.{interface_index}'))))
            )
            if not errorIndication and not errorStatus and varBinds:
                val = varBinds[0][1]
                if val is not None:
                    speed_bps = int(val)
                    if speed_bps >= 1_000_000_000:
                         speed_str = f"{speed_bps / 1_000_000_000} Gbps"
                    elif speed_bps >= 1_000_000:
                         speed_str = f"{speed_bps / 1_000_000} Mbps"
                    elif speed_bps > 0:
                         speed_str = f"{speed_bps} bps"
        except: pass
            
        return speed_str

    def get_interface_status(self, ip, interface_index):
        print(f"DEBUG: Fetching Status for {ip} Index {interface_index}")
        status_str = "Unknown"
        try:
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1),
                       UdpTransportTarget((ip, 161), timeout=3.0, retries=2),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.2.2.1.8.{interface_index}'))))
            )
            if not errorIndication and not errorStatus and varBinds:
                val = varBinds[0][1]
                if val is not None:
                    status_int = int(val)
                    if status_int == 1: status_str = "Up"
                    elif status_int == 2: status_str = "Down"
                    elif status_int == 5: status_str = "Dormant"
                    else: status_str = "Other"
        except: pass
            
        return status_str

    def get_port_vlan_details(self, ip, interface_index):
        """
        Fetches full VLAN details (Untagged and Tagged).
        Returns string like "U:10, T:20,30"
        """
        print(f"DEBUG: Fetching Advanced VLANs for {ip} Index {interface_index}")
        untagged = None
        tagged = []

        # 1. Get Untagged (PVID/Access)
        # Try Cisco vmVlan
        try:
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1),
                       UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.4.1.9.9.68.1.2.2.1.2.{interface_index}'))))
            )
            if not errorIndication and not errorStatus and varBinds:
                val = int(varBinds[0][1])
                if val > 0: untagged = val
        except: pass

        if not untagged:
            # Try dot1qPvid
            try:
                errorIndication, errorStatus, errorIndex, varBinds = next(
                    getCmd(SnmpEngine(),
                           CommunityData(self.community, mpModel=1),
                           UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                           ContextData(),
                           ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.17.7.1.4.5.1.1.{interface_index}'))))
                )
                if not errorIndication and not errorStatus and varBinds:
                    val = int(varBinds[0][1])
                    if val > 0: untagged = val
            except: pass

        # 2. Get Tagged (static egress ports)
        # This requires walking the VLAN table to see where this port is a member (egress but not untagged)
        try:
            # dot1qVlanStaticEgressPorts: 1.3.6.1.2.1.17.7.1.4.3.1.2
            # dot1qVlanStaticUntaggedPorts: 1.3.6.1.2.1.17.7.1.4.3.1.4
            
            # Since walking large tables is slow, we try a more efficient OID if possible
            # But standard Q-BRIDGE is what we have.
            for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1),
                UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(str_to_tuple('1.3.6.1.2.1.17.7.1.4.3.1.2'))),
                lexicographicMode=False
            ):
                if errorIndication or errorStatus: break
                for varBind in varBinds:
                    oid, value = varBind
                    vlan_id = list(oid)[-1]
                    if vlan_id == untagged: continue # Untagged is handled
                    
                    # Value is a bitmask (OctetString)
                    if self._is_port_in_bitmask(value, interface_index):
                        tagged.append(vlan_id)
        except: pass

        # Format result
        parts = []
        if untagged: parts.append(f"U:{untagged}")
        if tagged: parts.append(f"T:{','.join(map(str, sorted(list(set(tagged)))))}")
        
        return ", ".join(parts) if parts else ""

    def _is_port_in_bitmask(self, bitmask, port_index):
        """Checks if port_index is set in the SNMP bitmask (OctetString)."""
        try:
            if not bitmask: return False
            # Convert to bytes if it's PySNMP type
            data = bytes(bitmask)
            byte_idx = (port_index - 1) // 8
            bit_idx = 7 - ((port_index - 1) % 8)
            if byte_idx < len(data):
                return bool(data[byte_idx] & (1 << bit_idx))
        except: pass
        return False

    def get_stp_root_port(self, ip):
        """Fetches the STP Root Port index and translates it to ifIndex."""
        print(f"DEBUG: Fetching STP Root Port for {ip}")
        try:
            # dot1dStpRootPort: 1.3.6.1.2.1.17.2.7.0
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                       CommunityData(self.community, mpModel=1),
                       UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                       ContextData(),
                       ObjectType(ObjectIdentity(str_to_tuple('1.3.6.1.2.1.17.2.7.0'))))
            )
            if not errorIndication and not errorStatus and varBinds:
                bridge_port_idx = int(varBinds[0][1])
                if bridge_port_idx == 0: return None # No root port (likely the Root Bridge itself)
                
                # Translate dot1dBasePort to ifIndex
                # dot1dBasePortIfIndex: 1.3.6.1.2.1.17.1.4.1.2.{bridge_port_idx}
                errorIndication, errorStatus, errorIndex, varBinds = next(
                    getCmd(SnmpEngine(),
                           CommunityData(self.community, mpModel=1),
                           UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                           ContextData(),
                           ObjectType(ObjectIdentity(str_to_tuple(f'1.3.6.1.2.1.17.1.4.1.2.{bridge_port_idx}'))))
                )
                if not errorIndication and not errorStatus and varBinds:
                    if_index = int(varBinds[0][1])
                    print(f"DEBUG: Translated Bridge Port {bridge_port_idx} -> ifIndex {if_index}")
                    return if_index
                
                return bridge_port_idx # Fallback
        except: pass
        return None
