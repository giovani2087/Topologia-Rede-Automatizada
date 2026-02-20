import sys
import importlib
import asyncio
import ipaddress

if sys.version_info >= (3, 12):
    import importlib.metadata
    import importlib.util
    # Monkey patch for pysnmp which uses 'imp'
    import types
    sys.modules['imp'] = types.ModuleType('imp')
    import imp
    imp.reload = importlib.reload

from pysnmp.hlapi.v3arch import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd, next_cmd, bulk_cmd, walk_cmd
)

def str_to_tuple(oid_str):
    """Converts a string OID to a tuple of integers for pysnmp to avoid MIB lookups."""
    try:
        return tuple(int(x) for x in oid_str.strip('.').split('.'))
    except:
        return tuple()

class SNMPHandler:
    def __init__(self, community):
        self.community = community

    async def _get_cmd_async(self, ip, oids, timeout=1.5, retries=1):
        try:
            transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=retries)
            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1), # SNMP v2c
                transport,
                ContextData(),
                *[ObjectType(ObjectIdentity(str_to_tuple(oid))) for oid in oids]
            )
            return errorIndication, errorStatus, errorIndex, varBinds
        except Exception as e:
            return str(e), 0, 0, []

    def get_system_info(self, ip):
        """Retrieves system name, description, and OID."""
        try:
            oids = [
                '1.3.6.1.2.1.1.5.0', # sysName
                '1.3.6.1.2.1.1.1.0', # sysDescr
                '1.3.6.1.2.1.1.2.0'  # sysObjectID
            ]
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids))

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

    async def _next_cmd_async(self, ip, base_oid, timeout=3, retries=2):
        results = []
        try:
            transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=retries)
            # walk_cmd in pysnmp 7.x returns an async generator
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(str_to_tuple(base_oid))),
                lexicographicMode=False
            ):
                if errorIndication or errorStatus:
                    break
                results.append((errorIndication, errorStatus, errorIndex, varBinds))
        except Exception as e:
            print(f"Async walk error for {ip}: {e}")
        return results

    def get_neighbors_details(self, ip):
        neighbors = []
        try:
            # 1. Fetch lldpRemSysCapEnabled (.12)
            remote_caps = {}
            walk_results = asyncio.run(self._next_cmd_async(ip, '1.0.8802.1.1.2.1.4.1.1.12'))
            for _, _, _, varBinds in walk_results:
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

            # 2. Fetch lldpRemPortId (.7)
            remote_ports = {}
            walk_results = asyncio.run(self._next_cmd_async(ip, '1.0.8802.1.1.2.1.4.1.1.7'))
            for _, _, _, varBinds in walk_results:
                for varBind in varBinds:
                    oid, value = varBind
                    try:
                        oid_list = list(oid)
                        if len(oid_list) >= 14:
                            local_port_num = oid_list[12]
                            remote_index = oid_list[13]
                            remote_ports[(local_port_num, remote_index)] = str(value)
                    except: pass

            # 3. Fetch lldpRemSysName (.9)
            remote_sysnames = {}
            walk_results = asyncio.run(self._next_cmd_async(ip, '1.0.8802.1.1.2.1.4.1.1.9'))
            for _, _, _, varBinds in walk_results:
                for varBind in varBinds:
                    oid, value = varBind
                    try:
                        oid_list = list(oid)
                        if len(oid_list) >= 14:
                            local_port_num = oid_list[12]
                            remote_index = oid_list[13]
                            remote_sysnames[(local_port_num, remote_index)] = str(value)
                    except: pass

            # 4. Fetch lldpRemManAddr correlations
            walk_results = asyncio.run(self._next_cmd_async(ip, '1.0.8802.1.1.2.1.4.2.1.3'))
            for _, _, _, varBinds in walk_results:
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
        except Exception as e:
            print(f"Error fetching LLDP neighbors for {ip}: {e}")
        return neighbors

    def get_interface_name(self, ip, interface_index):
        name = str(interface_index)
        try:
            oids = [f'1.3.6.1.2.1.31.1.1.1.1.{interface_index}']
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=3.0, retries=2))
            if not errorIndication and not errorStatus and varBinds:
                name = str(varBinds[0][1])
                if not name: raise Exception()
        except:
            try:
                oids = [f'1.3.6.1.2.1.2.2.1.2.{interface_index}']
                errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=3.0, retries=2))
                if not errorIndication and not errorStatus and varBinds:
                    name = str(varBinds[0][1])
            except: pass
        return name

    def get_interface_speed(self, ip, interface_index):
        speed_str = ""
        try:
            oids = [f'1.3.6.1.2.1.31.1.1.1.15.{interface_index}']
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=3.0, retries=2))
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
            oids = [f'1.3.6.1.2.1.2.2.1.5.{interface_index}']
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=3.0, retries=2))
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
        status_str = "Unknown"
        try:
            oids = [f'1.3.6.1.2.1.2.2.1.8.{interface_index}']
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=3.0, retries=2))
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
        untagged = None
        tagged = []
        try:
            # 1. Untagged Cisco
            oids = [f'1.3.6.1.4.1.9.9.68.1.2.2.1.2.{interface_index}']
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=2.0, retries=1))
            if not errorIndication and not errorStatus and varBinds:
                val = int(varBinds[0][1])
                if val > 0: untagged = val
        except: pass

        if not untagged:
            try:
                # dot1qPvid
                oids = [f'1.3.6.1.2.1.17.7.1.4.5.1.1.{interface_index}']
                errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=2.0, retries=1))
                if not errorIndication and not errorStatus and varBinds:
                    val = int(varBinds[0][1])
                    if val > 0: untagged = val
            except: pass

        try:
            walk_results = asyncio.run(self._next_cmd_async(ip, '1.3.6.1.2.1.17.7.1.4.3.1.2', timeout=2.0, retries=1))
            for _, _, _, varBinds in walk_results:
                for varBind in varBinds:
                    oid, value = varBind
                    vlan_id = list(oid)[-1]
                    if vlan_id == untagged: continue
                    if self._is_port_in_bitmask(value, interface_index):
                        tagged.append(vlan_id)
        except: pass

        parts = []
        if untagged: parts.append(f"U:{untagged}")
        if tagged: parts.append(f"T:{','.join(map(str, sorted(list(set(tagged)))))}")
        return ", ".join(parts) if parts else ""

    def _is_port_in_bitmask(self, bitmask, port_index):
        try:
            if not bitmask: return False
            data = bytes(bitmask)
            byte_idx = (port_index - 1) // 8
            bit_idx = 7 - ((port_index - 1) % 8)
            if byte_idx < len(data):
                return bool(data[byte_idx] & (1 << bit_idx))
        except: pass
        return False

    def get_stp_root_port(self, ip):
        try:
            oids = ['1.3.6.1.2.1.17.2.7.0']
            errorIndication, errorStatus, errorIndex, varBinds = asyncio.run(self._get_cmd_async(ip, oids, timeout=2.0, retries=1))
            if not errorIndication and not errorStatus and varBinds:
                bridge_port_idx = int(varBinds[0][1])
                if bridge_port_idx == 0: return None
                
                oids2 = [f'1.3.6.1.2.1.17.1.4.1.2.{bridge_port_idx}']
                errorIndication, errorStatus, errorIndex, varBinds2 = asyncio.run(self._get_cmd_async(ip, oids2, timeout=2.0, retries=1))
                if not errorIndication and not errorStatus and varBinds2:
                    if_index = int(varBinds2[0][1])
                    return if_index
                return bridge_port_idx
        except: pass
        return None
