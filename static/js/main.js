document.addEventListener('DOMContentLoaded', function () {
    const scanBtn = document.getElementById('scan-btn');
    const networkInput = document.getElementById('network-input');
    const communityInput = document.getElementById('community-input');
    const statusDiv = document.getElementById('status');
    const container = document.getElementById('network-map');
    const exportPngBtn = document.getElementById('export-png-btn');
    const exportPdfBtn = document.getElementById('export-pdf-btn');
    const reorganizeBtn = document.getElementById('reorganize-btn');

    // Map Management UI
    const mapList = document.getElementById('map-list');
    const createMapBtn = document.getElementById('create-map-btn');
    const newMapNameInput = document.getElementById('new-map-name');

    let currentMapId = 1; // Default
    let network = null;
    let nodes = new vis.DataSet([]);
    let edges = new vis.DataSet([]);

    // Modal Elements
    const editModal = document.getElementById('edit-modal');
    const modalTitle = document.getElementById('modal-title');
    const closeLocalBtn = document.getElementById('close-modal');
    const cancelEditBtn = document.getElementById('cancel-edit');
    const saveEditBtn = document.getElementById('save-edit');
    const editMapId = document.getElementById('edit-map-id');
    const editMapName = document.getElementById('edit-map-name');
    const editMapNetwork = document.getElementById('edit-map-network');
    const editMapCommunity = document.getElementById('edit-map-community');

    let lastScanActive = false;

    const data = {
        nodes: nodes,
        edges: edges
    };

    const options = {
        nodes: {
            shape: 'dot',
            size: 30,
            font: { size: 14, color: '#333' },
            borderWidth: 2
        },
        edges: {
            width: 2,
            color: '#ccc'
        },
        physics: {
            enabled: true,
            stabilization: {
                enabled: true,
                iterations: 1000,
                updateInterval: 50
            },
            barnesHut: {
                gravitationalConstant: -20000,
                springConstant: 0.04,
                springLength: 150
            }
        },
        groups: {
            router: {
                shape: 'image',
                image: '/static/img/fw.png',
                size: 30
            },
            switch: {
                shape: 'image',
                image: '/static/img/switch.png',
                size: 25
            },
            access_point: {
                shape: 'image',
                image: '/static/img/ap2.png',
                size: 25
            },
            server: {
                shape: 'image',
                image: '/static/img/pc.png',
                size: 25
            }
        }
    };

    network = new vis.Network(container, data, options);

    // Disable physics once stabilization is finished to keep map static
    network.on("stabilized", function (params) {
        console.log("Stabilization finished. Freezing layout.");
        network.setOptions({ physics: { enabled: false } });
    });

    // --- Map Management Functions ---

    function loadMaps() {
        fetch('/api/maps')
            .then(res => res.json())
            .then(maps => {
                mapList.innerHTML = '';
                if (maps.length === 0) {
                    currentMapId = null;
                    nodes.clear();
                    edges.clear();
                    document.getElementById('log-content').innerText = '';
                    document.getElementById('scan-status').textContent = 'Idle';
                    document.getElementById('scan-status').className = 'badge badge-idle';
                    return;
                }

                const exists = maps.find(m => m.id === currentMapId);
                if (!exists && maps.length > 0) currentMapId = maps[0].id;

                maps.forEach(map => {
                    const li = document.createElement('li');
                    if (map.id === currentMapId) li.classList.add('active');

                    const nameSpan = document.createElement('span');
                    nameSpan.className = 'map-name';
                    nameSpan.textContent = map.name;
                    nameSpan.onclick = () => switchMap(map.id);
                    li.appendChild(nameSpan);

                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'map-actions';

                    // Rescan Button
                    if (map.network && map.community) {
                        const rescanBtn = document.createElement('button');
                        rescanBtn.className = 'btn-action btn-rescan';
                        rescanBtn.innerHTML = '🔄';
                        rescanBtn.title = 'Rescan';
                        rescanBtn.onclick = (e) => { e.stopPropagation(); rescanMap(map.id); };
                        actionsDiv.appendChild(rescanBtn);
                    }

                    // Edit Button
                    const editBtn = document.createElement('button');
                    editBtn.className = 'btn-action btn-edit';
                    editBtn.innerHTML = '✏️';
                    editBtn.title = 'Edit';
                    editBtn.onclick = (e) => { e.stopPropagation(); openEditModal(map); };
                    actionsDiv.appendChild(editBtn);

                    // Delete Button
                    const delBtn = document.createElement('button');
                    delBtn.className = 'btn-action btn-delete';
                    delBtn.innerHTML = '🗑️';
                    delBtn.title = 'Delete';
                    delBtn.onclick = (e) => { e.stopPropagation(); deleteMap(map.id); };
                    actionsDiv.appendChild(delBtn);

                    li.appendChild(actionsDiv);
                    mapList.appendChild(li);
                });

                if (currentMapId) {
                    refreshMap();
                    refreshLogs();
                } else {
                    nodes.clear();
                    edges.clear();
                }
            });
    }

    function createMap(name) {
        if (!name) return;
        fetch('/api/maps', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        })
            .then(res => res.json())
            .then(newMap => {
                currentMapId = newMap.id;
                loadMaps(); // Reload list and switch
                newMapNameInput.value = '';
            })
            .catch(err => console.error("Error creating map:", err));
    }

    function switchMap(id) {
        currentMapId = id;
        loadMaps();

        nodes.clear();
        edges.clear();
        document.getElementById('log-content').innerText = '';
        document.getElementById('scan-status').textContent = 'Idle';
        document.getElementById('scan-status').className = 'badge badge-idle';

        statusDiv.textContent = `Switched to Map ID: ${id}`;
    }

    function deleteMap(id) {
        if (!confirm("Tem certeza que deseja excluir este mapa e todos os seus dados?")) return;
        fetch(`/api/maps/${id}`, { method: 'DELETE' })
            .then(() => {
                if (currentMapId === id) currentMapId = null;
                loadMaps();
            });
    }

    function rescanMap(id) {
        statusDiv.textContent = "Iniciando re-escaneamento...";

        fetch(`/api/maps/${id}/rescan`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.error) alert(data.error);
                else {
                    switchMap(id);
                    refreshLogs();
                }
            });
    }

    function openEditModal(map) {
        editMapId.value = map.id;
        editMapName.value = map.name;
        editMapNetwork.value = map.network || '';
        editMapCommunity.value = map.community || '';
        editModal.style.display = 'block';
    }

    function closeEditModal() {
        editModal.style.display = 'none';
    }

    closeLocalBtn.onclick = closeEditModal;
    cancelEditBtn.onclick = closeEditModal;
    window.onclick = (event) => { if (event.target == editModal) closeEditModal(); };

    saveEditBtn.onclick = () => {
        const id = editMapId.value;
        const data = {
            name: editMapName.value,
            network: editMapNetwork.value,
            community: editMapCommunity.value
        };
        fetch(`/api/maps/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(() => {
            closeEditModal();
            loadMaps();
        });
    };

    createMapBtn.addEventListener('click', () => {
        createMap(newMapNameInput.value);
    });

    // --- UI Elements ---
    const stopBtn = document.getElementById('stop-btn');

    // --- Core Functions ---

    function refreshMap() {
        if (!currentMapId) return;
        fetch(`/api/devices?map_id=${currentMapId}`)
            .then(response => response.json())
            .then(data => {
                const newNodes = data.nodes.map(device => {
                    let group = 'router';

                    // Priority 1: Use explicit device_type if it's NOT just the default 'router'
                    if (device.device_type && device.device_type !== 'router') {
                        group = device.device_type;
                    }
                    // Priority 2: Name/Description heuristics (overrides default 'router' type)
                    else if (device.sysName && (device.sysName.toLowerCase().includes('switch') || device.sysName.toLowerCase().includes('aruba') || (device.sysDescr && (device.sysDescr.toLowerCase().includes('switch') || device.sysDescr.toLowerCase().includes('aruba'))))) {
                        group = 'switch';
                    }
                    // Priority 3: Fallback to whatever device_type is (which is likely 'router')
                    else if (device.device_type) {
                        group = device.device_type;
                    }

                    // Debug log
                    // console.log(`Node ${device.ip}: Type=${device.device_type} Group=${group}`);

                    return {
                        id: device.ip,
                        label: (device.sysName && device.sysName !== 'Unknown' && device.sysName !== device.ip) ? `${device.sysName}\n${device.ip}` : device.ip,
                        title: `IP: ${device.ip}\nType: ${device.device_type}\nDescr: ${device.sysDescr}`,
                        group: group
                    };
                });

                const newEdges = data.edges.map(link => {
                    let label = "";
                    if (link.source_port && link.target_port) {
                        // PortX (U:10, T:20,30) (ROOT) <-> PortY (U:100)
                        let srcLabel = link.source_port;
                        if (link.source_vlan) srcLabel += ` (${link.source_vlan})`;
                        if (link.source_is_root) srcLabel += " (ROOT)";

                        let tgtLabel = link.target_port;
                        if (link.target_vlan) tgtLabel += ` (${link.target_vlan})`;
                        if (link.target_is_root) tgtLabel += " (ROOT)";

                        // Also octets to help identity
                        let srcIpLastOctet = link.source_ip.split('.').pop();
                        let tgtIpLastOctet = link.target_ip.split('.').pop();

                        label = `${srcLabel} (.${srcIpLastOctet}) <-> ${tgtLabel} (.${tgtIpLastOctet})`;
                    } else if (link.source_port) {
                        label = link.source_port;
                        if (link.source_vlan) label += ` (${link.source_vlan})`;
                        if (link.source_is_root) label += " (ROOT)";
                        label += " ->";
                    }

                    if (link.speed) {
                        label += `\n(${link.speed})`;
                    }

                    let color = { color: '#848484' }; // Default grey
                    if (link.status === 'Up') {
                        // Standard Green
                        color = { color: '#28a745', highlight: '#34ce57' };

                        // Check for speed bottlenecks
                        if (link.speed) {
                            const speed = link.speed.toLowerCase();
                            if (speed.includes('100 mbps')) {
                                color = { color: '#fbc02d', highlight: '#fff176' }; // Yellow/Gold
                            } else if (speed.includes('10 mbps')) {
                                color = { color: '#d32f2f', highlight: '#ef5350' }; // Red
                            }
                        }
                    } else if (link.status === 'Down') {
                        color = { color: '#9e9e9e', highlight: '#bdbdbd' }; // Grey for Down
                    } else if (link.status === 'Dormant') {
                        color = { color: 'orange' };
                    }

                    return {
                        id: link.id, // Using DB ID to prevent duplicates!
                        from: link.source_ip,
                        to: link.target_ip,
                        label: label,
                        color: color,
                        font: { align: 'top', size: 10 }
                    };
                });

                // Update nodes without clearing to preserve manual positions
                // newNodes contain latest data from DB
                const currentNodes = nodes.get();
                let hasNewNodes = false;
                newNodes.forEach(newNode => {
                    const existing = currentNodes.find(n => n.id === newNode.id);
                    if (!existing) {
                        nodes.add(newNode);
                        hasNewNodes = true;
                    } else {
                        nodes.update(newNode);
                    }
                });

                // Trigger stabilization if new nodes were added
                if (hasNewNodes) {
                    console.log("New nodes detected. Stabilizing...");
                    network.setOptions({ physics: { enabled: true } });
                }

                // Remove nodes that are no longer in DB
                const newIds = newNodes.map(n => n.id);
                const toRemove = nodes.getIds().filter(id => !newIds.includes(id));
                nodes.remove(toRemove);

                // For edges, we can clear and re-add since they depend on nodes
                edges.clear();
                edges.add(newEdges);

                // If many new nodes were added, stabilization might be needed
                // But we'll leave that to the Manual Re-organize button or automated scan start

                // Same for edges? Complex with generated IDs. 
                // Since we regenerate edges every time map logic runs, we might just clear if too mismatched.
                // For now, simple update appends/modifies. 
            })
            .catch(err => console.error("Error fetching map data:", err));
    }

    function refreshLogs() {
        if (!currentMapId) return;
        fetch(`/api/logs?map_id=${currentMapId}`)
            .then(response => response.json())
            .then(data => {
                const logContent = document.getElementById('log-content');
                const statusBadge = document.getElementById('scan-status');

                if (logContent) {
                    // Check if content changed to avoid auto-scroll if user scrolling?
                    // Simple replacement for now.
                    logContent.innerText = data.logs.join('\n');
                    logContent.scrollTop = logContent.scrollHeight;
                }

                const isActive = data.active;

                if (statusBadge) {
                    if (isActive) {
                        statusBadge.textContent = "Scanning...";
                        statusBadge.className = "badge badge-scanning";
                    } else {
                        statusBadge.textContent = "Idle";
                        statusBadge.className = "badge badge-idle";
                    }
                }

                // Update Button State
                if (isActive) {
                    scanBtn.style.display = 'none';
                    stopBtn.style.display = 'inline-block';
                } else {
                    scanBtn.style.display = 'inline-block';
                    stopBtn.style.display = 'none';
                }

                lastScanActive = isActive;
            })
            .catch(err => console.error("Error fetching logs:", err));
    }

    // Initial load
    loadMaps();

    setInterval(() => {
        if (currentMapId) refreshMap();
    }, 5000);

    setInterval(() => {
        if (currentMapId) refreshLogs();
    }, 2000);

    // Scan Button Handler
    scanBtn.addEventListener('click', function () {
        const net = networkInput.value;
        const comm = communityInput.value;

        if (!net || !comm) {
            alert("Please enter both Network and Community String");
            return;
        }

        if (!currentMapId) {
            alert("Select a map first!");
            return;
        }

        statusDiv.textContent = "Initiating scan...";

        // Optimistic UI update
        scanBtn.style.display = 'none';
        stopBtn.style.display = 'inline-block';

        fetch('/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                network: net,
                community: comm,
                map_id: currentMapId
            })
        })
            .then(response => response.json())
            .then(data => {
                console.log(data);
                statusDiv.textContent = data.message;
                refreshLogs(); // Immediate update
            })
            .catch(err => {
                console.error(err);
                statusDiv.textContent = "Error starting scan.";
                // Revert UI on error
                scanBtn.style.display = 'inline-block';
                stopBtn.style.display = 'none';
            });
    });

    // Stop Button Handler
    stopBtn.addEventListener('click', function () {
        if (!currentMapId) return;

        if (!confirm("Tem certeza que deseja parar o escaneamento?")) return;

        statusDiv.textContent = "Stopping scan...";

        fetch('/scan/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ map_id: currentMapId })
        })
            .then(res => res.json())
            .then(data => {
                console.log(data);
                statusDiv.textContent = data.message;
            })
            .catch(err => {
                console.error(err);
                statusDiv.textContent = "Error stopping scan.";
            });
    });

    // --- True HD Export Functions ---

    /**
     * Renders the map onto a hidden, high-resolution canvas to ensure native sharpness.
     * @param {string} format 'png' or 'pdf'
     */
    function exportHD(format) {
        statusDiv.textContent = "Gerando exportação ULTRA-HD Dinâmica...";
        console.log("Starting Dynamic Ultra-HD Export...");

        let hiddenContainer = null;
        let hdNetwork = null;

        try {
            const SCALE_FACTOR = 4.0;
            const currentNodesData = nodes.get();
            if (!currentNodesData || currentNodesData.length === 0) {
                throw new Error("Nenhum dispositivo encontrado.");
            }

            console.log("Calculating map bounding box...");
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            const positions = network.getPositions();

            currentNodesData.forEach(node => {
                const pos = positions[node.id];
                if (pos) {
                    if (pos.x < minX) minX = pos.x;
                    if (pos.x > maxX) maxX = pos.x;
                    if (pos.y < minY) minY = pos.y;
                    if (pos.y > maxY) maxY = pos.y;
                }
            });

            // If only one node or none found
            if (minX === Infinity) { minX = -100; maxX = 100; minY = -100; maxY = 100; }

            const spanX = (maxX - minX) || 200;
            const spanY = (maxY - minY) || 200;

            // Calculate target canvas size with padding
            // We scale the span and add significant padding for labels
            let targetWidth = (spanX * SCALE_FACTOR) + (1000 * SCALE_FACTOR);
            let targetHeight = (spanY * SCALE_FACTOR) + (1000 * SCALE_FACTOR);

            // Cap the size for browser compatibility (safe limit around 10k-12k)
            targetWidth = Math.min(Math.max(targetWidth, 4000), 12000);
            targetHeight = Math.min(Math.max(targetHeight, 3000), 12000);

            console.log(`Dynamic Canvas Size: ${Math.round(targetWidth)}x${Math.round(targetHeight)}`);

            console.log("Creating dynamic hidden container...");
            hiddenContainer = document.createElement('div');
            hiddenContainer.id = 'hd-export-container';
            hiddenContainer.style.position = 'absolute';
            hiddenContainer.style.left = '-20000px';
            hiddenContainer.style.top = '-20000px';
            hiddenContainer.style.width = Math.round(targetWidth) + 'px';
            hiddenContainer.style.height = Math.round(targetHeight) + 'px';
            document.body.appendChild(hiddenContainer);

            console.log("Applying Ultra-HD options...");
            const hdOptions = JSON.parse(JSON.stringify(options));
            hdOptions.physics = { enabled: false };

            // Force label visibility even at small scales during render
            hdOptions.interaction = {
                hideEdgesOnDrag: false,
                hideEdgesOnZoom: false,
                hideNodesOnDrag: false,
                navigationButtons: false,
                selectable: false
            };

            if (hdOptions.nodes) {
                hdOptions.nodes.size = (hdOptions.nodes.size || 30) * SCALE_FACTOR;
                if (!hdOptions.nodes.font) hdOptions.nodes.font = {};
                // Reduced node font scale (2.2x) to prevent overlapping names
                hdOptions.nodes.font.size = (hdOptions.nodes.font.size || 14) * 2.2;
                hdOptions.nodes.font.strokeWidth = 3;
                hdOptions.nodes.font.strokeColor = '#ffffff';
            }

            if (hdOptions.edges) {
                hdOptions.edges.width = (hdOptions.edges.width || 2) * SCALE_FACTOR;
                if (!hdOptions.edges.font) {
                    hdOptions.edges.font = { size: 14, color: '#000000' };
                }
                // Balanced edge font scale (2.5x) for legibility
                hdOptions.edges.font.size = (hdOptions.edges.font.size || 14) * 2.5;
                hdOptions.edges.font.background = '#ffffff';
                hdOptions.edges.font.strokeWidth = 4;
                hdOptions.edges.font.strokeColor = '#ffffff';
                hdOptions.edges.font.align = 'middle';
                // Force labels to be drawn even if tiny
                hdOptions.edges.font.vadjust = 0;
            }

            if (hdOptions.groups) {
                Object.keys(hdOptions.groups).forEach(key => {
                    hdOptions.groups[key].size = (hdOptions.groups[key].size || 25) * SCALE_FACTOR;
                    if (!hdOptions.groups[key].font) hdOptions.groups[key].font = { size: 14 * 2.2 };
                    hdOptions.groups[key].font.size = (hdOptions.groups[key].font.size || 14) * 2.2;
                });
            }

            console.log("Scaling node coordinates for HD space...");
            const currentNodes = currentNodesData.map(node => {
                const pos = positions[node.id];
                if (pos) {
                    return {
                        ...node,
                        x: pos.x * SCALE_FACTOR,
                        y: pos.y * SCALE_FACTOR,
                        fixed: { x: true, y: true }
                    };
                }
                return node;
            });
            const currentEdges = edges.get();

            const hdData = {
                nodes: new vis.DataSet(currentNodes),
                edges: new vis.DataSet(currentEdges)
            };

            console.log("Initializing Dynamic Ultra Network...");
            hdNetwork = new vis.Network(hiddenContainer, hdData, hdOptions);

            let exportDone = false;
            const finalizeExport = () => {
                if (exportDone) return;
                exportDone = true;

                console.log("Finalizing render...");
                // Force a fit with extra padding to ensure all labels are inside
                hdNetwork.fit({ padding: 200 });

                setTimeout(() => {
                    try {
                        const canvas = hiddenContainer.getElementsByTagName('canvas')[0];
                        if (!canvas) throw new Error("Canvas falhou.");

                        const finalCanvas = document.createElement('canvas');
                        finalCanvas.width = canvas.width;
                        finalCanvas.height = canvas.height;
                        const ctx = finalCanvas.getContext('2d');

                        // Ultra-sharp rendering
                        ctx.imageSmoothingEnabled = false;

                        ctx.fillStyle = "#ffffff";
                        ctx.fillRect(0, 0, finalCanvas.width, finalCanvas.height);
                        ctx.drawImage(canvas, 0, 0);

                        const timestamp = new Date().getTime();
                        if (format === 'png') {
                            const dataUrl = finalCanvas.toDataURL('image/png', 1.0);
                            const link = document.createElement('a');
                            link.download = `mapa-rede-ULTRA-HD-${timestamp}.png`;
                            link.href = dataUrl;
                            link.click();
                        } else if (format === 'pdf') {
                            const dataUrl = finalCanvas.toDataURL('image/png', 1.0);
                            const { jsPDF } = window.jspdf;
                            const orientation = canvas.width > canvas.height ? 'l' : 'p';

                            const pdf = new jsPDF({
                                orientation: orientation,
                                unit: 'mm',
                                format: 'a3',
                                compress: true
                            });

                            const pageWidth = pdf.internal.pageSize.getWidth();
                            const pageHeight = pdf.internal.pageSize.getHeight();
                            const canvasRatio = canvas.width / canvas.height;
                            const pageRatio = pageWidth / pageHeight;

                            let renderWidth, renderHeight;
                            if (canvasRatio > pageRatio) {
                                renderWidth = pageWidth - 10;
                                renderHeight = renderWidth / canvasRatio;
                            } else {
                                renderHeight = pageHeight - 10;
                                renderWidth = renderHeight * canvasRatio;
                            }

                            const x = (pageWidth - renderWidth) / 2;
                            const y = (pageHeight - renderHeight) / 2;

                            pdf.addImage(dataUrl, 'PNG', x, y, renderWidth, renderHeight, undefined, 'FAST');
                            pdf.save(`mapa-rede-ULTRA-HD-${timestamp}.pdf`);
                        }

                        statusDiv.textContent = "Exportação ULTRA-HD concluída!";
                    } catch (err) {
                        console.error("Export inner error:", err);
                        statusDiv.textContent = "Erro na imagem: " + err.message;
                    } finally {
                        if (hdNetwork) hdNetwork.destroy();
                        if (hiddenContainer && hiddenContainer.parentNode) document.body.removeChild(hiddenContainer);
                        setTimeout(() => { if (statusDiv.textContent.includes("concluída")) statusDiv.textContent = ""; }, 3000);
                    }
                }, 2000); // 2s to ensure labels and large map render fully
            };

            hdNetwork.once('afterDrawing', finalizeExport);

            setTimeout(() => {
                if (!exportDone) finalizeExport();
            }, 10000);

        } catch (err) {
            console.error("Export main error:", err);
            statusDiv.textContent = "Erro: " + err.message;
            if (hdNetwork) hdNetwork.destroy();
            if (hiddenContainer && hiddenContainer.parentNode) document.body.removeChild(hiddenContainer);
        }
    }
    if (exportPngBtn) exportPngBtn.addEventListener('click', () => exportHD('png'));
    if (exportPdfBtn) exportPdfBtn.addEventListener('click', () => exportHD('pdf'));

    if (reorganizeBtn) {
        reorganizeBtn.addEventListener('click', () => {
            console.log("Manual reorganization triggered.");
            network.setOptions({ physics: { enabled: true } });
            network.stabilize();
        });
    }

    // --- Resizable Columns Logic ---
    const resizer = document.getElementById('resizer');
    const logContainer = document.getElementById('log-container');
    const leftContainer = document.querySelector('.content-wrapper');

    if (resizer && logContainer) {
        let isResizing = false;

        resizer.addEventListener('mousedown', function (e) {
            isResizing = true;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
            // Disable pointers for the network map while resizing to avoid glitches
            document.getElementById('network-map').style.pointerEvents = 'none';
        });

        document.addEventListener('mousemove', function (e) {
            if (!isResizing) return;

            // Calculate new width for the right panel (logs)
            // We subtract the current mouse position from the total window width
            // accounting for some padding if necessary.
            const totalWidth = document.body.clientWidth;
            const newLogWidth = totalWidth - e.clientX - 20; // 20px buffer

            if (newLogWidth > 150 && newLogWidth < totalWidth * 0.7) {
                logContainer.style.width = newLogWidth + 'px';
                // Trigger vis.js resize
                if (network) network.setSize('100%', '100%');
            }
        });

        document.addEventListener('mouseup', function () {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('resizing');
                document.body.style.cursor = 'default';
                document.getElementById('network-map').style.pointerEvents = 'auto';
            }
        });
    }
});
