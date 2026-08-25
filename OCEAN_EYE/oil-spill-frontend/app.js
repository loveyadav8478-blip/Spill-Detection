// ==========================================================================
// OceanEye Application Logic
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Application State
    const state = {
        activeTab: 'overview',
        incidents: [],
        activeIncident: null,
        map: null,
        mapLayers: {
            spillCentroid: null,
            spillPolygon: null,
            backwardPath: null,
            forwardPath: null,
            vesselMarkers: []
        },
        apiBaseUrl: 'http://localhost:8000',
        isMockMode: true
    };

    // UI Elements
    const elements = {
        mockModeCheckbox: document.getElementById('mock-mode-checkbox'),
        apiStatusDot: document.getElementById('api-status-dot'),
        apiStatusText: document.getElementById('api-status-text'),
        
        // Navigation links & Scrollspy
        navLinks: document.querySelectorAll('.nav-links a'),
        workspaceSections: document.querySelectorAll('.workspace-section'),
        
        // Overview Tab Form & Fields
        pipelineForm: document.getElementById('pipeline-form'),
        satelliteImage: document.getElementById('satellite_image'),
        spillMask: document.getElementById('spill_mask'),
        imageTimestamp: document.getElementById('image_timestamp'),
        coarseRadius: document.getElementById('coarse_radius_km'),
        coarseTimeWindow: document.getElementById('coarse_time_window_hours'),
        trajectoryMaxDistance: document.getElementById('trajectory_max_distance_km'),
        rawAisPingsJson: document.getElementById('raw_ais_pings_json'),
        aisPingsInputTbody: document.getElementById('ais-pings-input-tbody'),
        btnSubmitPipeline: document.getElementById('btn-submit-pipeline'),
        submitIcon: document.getElementById('submit-icon'),
        submitText: document.getElementById('submit-text'),
        submitSpinner: document.getElementById('submit-spinner'),
        loadSampleAisBtn: document.getElementById('load-sample-ais'),
        
        // Accordion
        accordionToggle: document.getElementById('accordion-toggle'),
        accordionChevron: document.getElementById('accordion-chevron'),
        accordionContent: document.getElementById('accordion-content'),

        // Image Previews & TIFF Wrappers
        sarUploadArea: document.getElementById('sar-upload-area'),
        maskUploadArea: document.getElementById('mask-upload-area'),
        sarFileName: document.getElementById('sar-file-name'),
        maskFileName: document.getElementById('mask-file-name'),
        sarPreviewPlaceholder: document.getElementById('sar-preview-placeholder'),
        maskPreviewPlaceholder: document.getElementById('mask-preview-placeholder'),
        sarPreviewImg: document.getElementById('sar-preview-img'),
        maskPreviewImg: document.getElementById('mask-preview-img'),
        sarTiffDisplay: document.getElementById('sar-tiff-display'),
        maskTiffDisplay: document.getElementById('mask-tiff-display'),
        
        // Command Centre Sidebar
        incidentsListContainer: document.getElementById('incidents-list-container'),
        vesselsListContainer: document.getElementById('vessels-list-container'),
        
        // Stepper Steps
        stepDetected: document.getElementById('step-detected'),
        stepHindcasting: document.getElementById('step-hindcasting'),
        stepFiltering: document.getElementById('step-filtering'),
        stepScoring: document.getElementById('step-scoring'),
        stepAttributed: document.getElementById('step-attributed'),
        line1: document.getElementById('line-1'),
        line2: document.getElementById('line-2'),
        line3: document.getElementById('line-3'),
        line4: document.getElementById('line-4'),
        
        // Metrics Displays
        valArea: document.getElementById('val-area'),
        valPerimeter: document.getElementById('val-perimeter'),
        valPixels: document.getElementById('val-pixels'),
        valEccentricity: document.getElementById('val-eccentricity'),
        valCentroid: document.getElementById('val-centroid'),
        valConfidence: document.getElementById('val-confidence'),
        valComponents: document.getElementById('val-components'),
        valModelNotes: document.getElementById('val-model-notes'),
        
        // Section 3: Drift Hindcasting Elements
        driftWindSpeed: document.getElementById('drift-wind-speed'),
        driftWindDir: document.getElementById('drift-wind-dir'),
        driftWindSource: document.getElementById('drift-wind-source'),
        driftCurrentSpeed: document.getElementById('drift-current-speed'),
        driftCurrentDir: document.getElementById('drift-current-dir'),
        driftCurrentSource: document.getElementById('drift-current-source'),
        driftWindageCoeff: document.getElementById('drift-windage-coeff'),
        driftTimestep: document.getElementById('drift-timestep'),
        driftLookback: document.getElementById('drift-lookback'),
        driftLookahead: document.getElementById('drift-lookahead'),
        
        // Section 4, 5, 6 UI Elements
        filterResultsTbody: document.getElementById('filter-results-tbody'),
        suspectsMetricsContainer: document.getElementById('suspects-metrics-container'),
        primarySuspectFile: document.getElementById('primary-suspect-file'),
        incidentRecordFile: document.getElementById('incident-record-file'),
        
        // Modal Details
        vesselDetailModal: document.getElementById('vessel-detail-modal'),
        modalBackdrop: document.getElementById('modal-backdrop-el'),
        btnCloseModal: document.getElementById('btn-close-modal'),
        modalVesselName: document.getElementById('modal-vessel-name'),
        modalVesselMmsi: document.getElementById('modal-vessel-mmsi'),
        modalImo: document.getElementById('modal-imo'),
        modalCallsign: document.getElementById('modal-callsign'),
        modalType: document.getElementById('modal-type'),
        modalDim: document.getElementById('modal-dim'),
        barProximity: document.getElementById('bar-proximity'),
        lblProximity: document.getElementById('lbl-proximity'),
        barTemporal: document.getElementById('bar-temporal'),
        lblTemporal: document.getElementById('lbl-temporal'),
        barTrajectory: document.getElementById('bar-trajectory'),
        lblTrajectory: document.getElementById('lbl-trajectory'),
        barBehavior: document.getElementById('bar-behavior'),
        lblBehavior: document.getElementById('lbl-behavior'),
        modalAnomaliesList: document.getElementById('modal-anomalies-list'),
        modalExplanationsList: document.getElementById('modal-explanations-list')
    };

    // Initialize Default Dates (Now)
    const initDateString = new Date().toISOString().substring(0, 16);
    elements.imageTimestamp.value = initDateString;

    // Test API Health on boot
    testApiConnection();

    // Setup Leaflet Map
    initMap();

    // Event Listeners
    setupEventListeners();

    // Load Default Pings into Textarea on load
    loadSampleAisData();

    // ==========================================================================
    // Core Functions
    // ==========================================================================

    function initMap() {
        // Center of English Channel shipping lanes
        state.map = L.map('map', {
            zoomControl: true,
            attributionControl: false
        }).setView([50.22, -1.45], 9);

        // CartoDB Positron - clean light map layer matching corporate theme
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19
        }).addTo(state.map);
    }

    async function testApiConnection() {
        try {
            const res = await fetch(`${state.apiBaseUrl}/`, { method: 'GET' });
            if (res.ok) {
                setApiStatus(true);
            } else {
                setApiStatus(false);
            }
        } catch (e) {
            setApiStatus(false);
        }
    }

    function setApiStatus(isOnline) {
        if (isOnline) {
            elements.apiStatusDot.className = 'status-dot green';
            elements.apiStatusText.textContent = 'API Connected';
            elements.mockModeCheckbox.checked = false;
            state.isMockMode = false;
        } else {
            elements.apiStatusDot.className = 'status-dot orange';
            elements.apiStatusText.textContent = 'Backend Offline';
            elements.mockModeCheckbox.checked = true;
            state.isMockMode = true;
        }
    }

    function setupEventListeners() {
        // Smooth scrolling for navigation links
        elements.navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = link.getAttribute('href');
                const targetEl = document.querySelector(targetId);
                if (targetEl) {
                    const offset = 80; // Offset for sticky navbar
                    const elementPosition = targetEl.getBoundingClientRect().top;
                    const offsetPosition = elementPosition + window.pageYOffset - offset;
                    
                    window.scrollTo({
                        top: offsetPosition,
                        behavior: 'smooth'
                    });
                }
            });
        });

        // Click handler to scroll to top on logo click
        const brandEl = document.getElementById('scroll-to-top');
        if (brandEl) {
            brandEl.addEventListener('click', () => {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            });
        }

        // ScrollSpy window listener
        window.addEventListener('scroll', () => {
            let currentSection = '';
            const scrollPosition = window.pageYOffset + 120; // Offset for sticky navbar
            
            elements.workspaceSections.forEach(section => {
                const sectionTop = section.offsetTop;
                const sectionHeight = section.offsetHeight;
                if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
                    currentSection = section.getAttribute('id');
                }
            });
            
            if (currentSection) {
                elements.navLinks.forEach(link => {
                    link.classList.toggle('active', link.getAttribute('href') === `#${currentSection}`);
                });
            }
        });

        // Toggle Mock Mode manually
        elements.mockModeCheckbox.addEventListener('change', (e) => {
            state.isMockMode = e.target.checked;
            elements.apiStatusText.textContent = state.isMockMode ? 'Simulation Mode' : 'Live API Mode';
            elements.apiStatusDot.className = state.isMockMode ? 'status-dot orange' : 'status-dot green';
        });

        // Parameters Accordion
        elements.accordionToggle.addEventListener('click', () => {
            elements.accordionContent.classList.toggle('hidden');
            elements.accordionChevron.classList.toggle('rotated');
        });

        // Load sample AIS data button
        elements.loadSampleAisBtn.addEventListener('click', loadSampleAisData);

        // Update live table when JSON edits are made
        elements.rawAisPingsJson.addEventListener('input', updateAisInputTable);
        elements.rawAisPingsJson.addEventListener('change', updateAisInputTable);

        // Upload Preview Handling: Image 1
        elements.satelliteImage.addEventListener('change', (e) => {
            handleFilePreview(e.target.files[0], elements.sarFileName, elements.sarPreviewPlaceholder, elements.sarPreviewImg, elements.sarTiffDisplay);
        });

        // Upload Drag & Drop triggers
        setupDragAndDrop(elements.sarUploadArea, elements.satelliteImage, elements.sarFileName, elements.sarPreviewPlaceholder, elements.sarPreviewImg, elements.sarTiffDisplay);
        setupDragAndDrop(elements.maskUploadArea, elements.spillMask, elements.maskFileName, elements.maskPreviewPlaceholder, elements.maskPreviewImg, elements.maskTiffDisplay);

        // Upload Preview Handling: Image 2
        elements.spillMask.addEventListener('change', (e) => {
            handleFilePreview(e.target.files[0], elements.maskFileName, elements.maskPreviewPlaceholder, elements.maskPreviewImg, elements.maskTiffDisplay);
        });

        // Form Submit
        elements.pipelineForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await runPipeline();
        });

        // Modal close
        elements.btnCloseModal.addEventListener('click', closeModal);
        elements.modalBackdrop.addEventListener('click', closeModal);
    }

    function switchTab(tabName) {
        if (tabName === 'command-centre') {
            const cmdSection = document.getElementById('section-command');
            if (cmdSection) {
                const offset = 80;
                const elementPosition = cmdSection.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - offset;
                
                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            }
            
            if (state.map) {
                setTimeout(() => {
                    state.map.invalidateSize();
                }, 500);
            }
        }
    }

    function handleFilePreview(file, nameEl, placeholderEl, imgEl, tiffContainerEl) {
        if (!file) return;
        nameEl.textContent = file.name;
        
        const isTiff = file.name.toLowerCase().endsWith('.tif') || file.name.toLowerCase().endsWith('.tiff');
        
        if (isTiff) {
            // Hide standard image
            imgEl.classList.remove('visible');
            imgEl.removeAttribute('src');
            placeholderEl.style.display = 'none';
            
            // Populate TIFF container badge
            tiffContainerEl.classList.remove('hidden');
            tiffContainerEl.innerHTML = `
                <div class="tiff-badge-wrapper">
                    <i data-lucide="file-check" class="tiff-icon"></i>
                    <div class="tiff-info-text">
                        <span class="tiff-title">TIFF Dataset Loaded</span>
                        <span class="tiff-size">${(file.size / 1024 / 1024).toFixed(2)} MB</span>
                    </div>
                </div>
                <div class="tiff-status-badge">Georeferenced Data</div>
            `;
            lucide.createIcons();
        } else {
            // Standard image format
            tiffContainerEl.classList.add('hidden');
            tiffContainerEl.innerHTML = '';
            
            const reader = new FileReader();
            reader.onload = (e) => {
                imgEl.src = e.target.result;
                imgEl.classList.add('visible');
                placeholderEl.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    }

    function setupDragAndDrop(areaEl, inputEl, nameEl, placeholderEl, imgEl, tiffContainerEl) {
        areaEl.addEventListener('dragover', (e) => {
            e.preventDefault();
            areaEl.style.borderColor = 'var(--accent-orange)';
            areaEl.style.background = '#f1f5f9';
        });

        areaEl.addEventListener('dragleave', () => {
            areaEl.style.borderColor = '#cbd5e1';
            areaEl.style.background = '#f8fafc';
        });

        areaEl.addEventListener('drop', (e) => {
            e.preventDefault();
            areaEl.style.borderColor = '#cbd5e1';
            areaEl.style.background = '#f8fafc';
            
            if (e.dataTransfer.files.length > 0) {
                inputEl.files = e.dataTransfer.files;
                handleFilePreview(e.dataTransfer.files[0], nameEl, placeholderEl, imgEl, tiffContainerEl);
            }
        });
    }

    function loadSampleAisData() {
        const timestamp = new Date(elements.imageTimestamp.value || new Date());
        
        // Realistic vessel coordinates near English Channel lane
        const pings = [
            // Suspect vessel 1 (KAPPA COMMANDER) - loitering close to origin with a gap
            {
                mmsi: "235085300",
                base_date_time: new Date(timestamp.getTime() - 2.5 * 60 * 60 * 1000).toISOString(),
                lat: 50.185,
                lon: -1.552,
                sog: 14.5,
                cog: 75.2,
                vessel_name: "MV KAPPA COMMANDER",
                imo: "9348922",
                call_sign: "GXYZ",
                vessel_type: 70, // Cargo
                length: 185.0,
                width: 28.0
            },
            {
                mmsi: "235085300",
                base_date_time: new Date(timestamp.getTime() - 2.0 * 60 * 60 * 1000).toISOString(),
                lat: 50.210,
                lon: -1.488,
                sog: 14.2,
                cog: 72.8,
                vessel_name: "MV KAPPA COMMANDER",
                imo: "9348922",
                call_sign: "GXYZ",
                vessel_type: 70,
                length: 185.0,
                width: 28.0
            },
            // Gaps in AIS right here: loitered / slow speed
            {
                mmsi: "235085300",
                base_date_time: new Date(timestamp.getTime() - 1.25 * 60 * 60 * 1000).toISOString(),
                lat: 50.222,
                lon: -1.451, // Very close to spill centroid
                sog: 4.2, // Loitering speed anomaly!
                cog: 120.4,
                vessel_name: "MV KAPPA COMMANDER",
                imo: "9348922",
                call_sign: "GXYZ",
                vessel_type: 70,
                length: 185.0,
                width: 28.0
            },
            {
                mmsi: "235085300",
                base_date_time: new Date(timestamp.getTime() - 0.5 * 60 * 60 * 1000).toISOString(),
                lat: 50.245,
                lon: -1.385,
                sog: 13.8,
                cog: 70.1,
                vessel_name: "MV KAPPA COMMANDER",
                imo: "9348922",
                call_sign: "GXYZ",
                vessel_type: 70,
                length: 185.0,
                width: 28.0
            },

            // Vessel 2: MT VOYAGER (Normal track tanker, passes near but fast speed)
            {
                mmsi: "477123900",
                base_date_time: new Date(timestamp.getTime() - 2.2 * 60 * 60 * 1000).toISOString(),
                lat: 50.160,
                lon: -1.610,
                sog: 18.2,
                cog: 65.5,
                vessel_name: "MT VOYAGER",
                imo: "9283942",
                call_sign: "VRAB2",
                vessel_type: 80, // Tanker
                length: 240.0,
                width: 42.0
            },
            {
                mmsi: "477123900",
                base_date_time: new Date(timestamp.getTime() - 1.2 * 60 * 60 * 1000).toISOString(),
                lat: 50.205,
                lon: -1.485,
                sog: 17.9,
                cog: 66.0,
                vessel_name: "MT VOYAGER",
                imo: "9283942",
                call_sign: "VRAB2",
                vessel_type: 80,
                length: 240.0,
                width: 42.0
            },
            {
                mmsi: "477123900",
                base_date_time: new Date(timestamp.getTime() - 0.2 * 60 * 60 * 1000).toISOString(),
                lat: 50.250,
                lon: -1.360,
                sog: 18.1,
                cog: 65.8,
                vessel_name: "MT VOYAGER",
                imo: "9283942",
                call_sign: "VRAB2",
                vessel_type: 80,
                length: 240.0,
                width: 42.0
            },

            // Vessel 3: ASTRO CARRIER (Cargo carrier, passes far south)
            {
                mmsi: "356882000",
                base_date_time: new Date(timestamp.getTime() - 1.8 * 60 * 60 * 1000).toISOString(),
                lat: 50.080,
                lon: -1.550,
                sog: 12.0,
                cog: 68.0,
                vessel_name: "ASTRO CARRIER",
                imo: "9400291",
                call_sign: "H3AB",
                vessel_type: 70,
                length: 130.0,
                width: 20.0
            },
            {
                mmsi: "356882000",
                base_date_time: new Date(timestamp.getTime() - 0.8 * 60 * 60 * 1000).toISOString(),
                lat: 50.120,
                lon: -1.410,
                sog: 12.1,
                cog: 68.2,
                vessel_name: "ASTRO CARRIER",
                imo: "9400291",
                call_sign: "H3AB",
                vessel_type: 70,
                length: 130.0,
                width: 20.0
            }
        ];

        elements.rawAisPingsJson.value = JSON.stringify(pings, null, 2);
        updateAisInputTable();
    }

    function updateAisInputTable() {
        const jsonText = elements.rawAisPingsJson.value.trim();
        if (!jsonText) {
            elements.aisPingsInputTbody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-table-cell">No AIS data parsed yet. Load sample pings or paste JSON above.</td>
                </tr>
            `;
            return;
        }

        try {
            const pings = JSON.parse(jsonText);
            if (!Array.isArray(pings)) {
                elements.aisPingsInputTbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="empty-table-cell" style="color: var(--accent-red) !important;">
                            Invalid Format: Root JSON must be an array of objects.
                        </td>
                    </tr>
                `;
                return;
            }

            if (pings.length === 0) {
                elements.aisPingsInputTbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="empty-table-cell">Empty array: No pings present.</td>
                    </tr>
                `;
                return;
            }

            let rowsHtml = '';
            pings.forEach(ping => {
                const name = ping.vessel_name || 'UNKNOWN';
                const mmsi = ping.mmsi || 'N/A';
                
                let timeStr = 'N/A';
                if (ping.base_date_time) {
                    try {
                        const date = new Date(ping.base_date_time);
                        timeStr = date.toISOString().replace('T', ' ').substring(0, 19);
                    } catch (e) {
                        timeStr = ping.base_date_time;
                    }
                }
                
                const latlon = (ping.lat !== undefined && ping.lon !== undefined) ? 
                    `${parseFloat(ping.lat).toFixed(4)}, ${parseFloat(ping.lon).toFixed(4)}` : 'N/A';
                const sog = ping.sog !== undefined ? parseFloat(ping.sog).toFixed(1) : 'N/A';
                const cog = ping.cog !== undefined ? parseFloat(ping.cog).toFixed(0) : 'N/A';

                rowsHtml += `
                    <tr>
                        <td><strong>${mmsi}</strong></td>
                        <td>${name}</td>
                        <td style="font-family: monospace; font-size: 0.75rem;">${timeStr}</td>
                        <td style="font-family: monospace; font-size: 0.75rem;">${latlon}</td>
                        <td>${sog}</td>
                        <td>${cog}</td>
                    </tr>
                `;
            });

            elements.aisPingsInputTbody.innerHTML = rowsHtml;
        } catch (err) {
            elements.aisPingsInputTbody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-table-cell" style="color: var(--accent-red) !important; text-align: left !important; font-family: monospace; font-size: 0.75rem;">
                        JSON Parse Error: ${err.message}
                    </td>
                </tr>
            `;
        }
    }

    function toggleFormLoading(isLoading) {
        if (isLoading) {
            elements.btnSubmitPipeline.classList.add('loading');
            elements.btnSubmitPipeline.disabled = true;
            elements.submitIcon.classList.add('hidden');
            elements.submitSpinner.classList.remove('hidden');
            elements.submitText.textContent = "Processing Pipeline Stages...";
        } else {
            elements.btnSubmitPipeline.classList.remove('loading');
            elements.btnSubmitPipeline.disabled = false;
            elements.submitIcon.classList.remove('hidden');
            elements.submitSpinner.classList.add('hidden');
            elements.submitText.textContent = "Execute Attribution Pipeline";
        }
    }

    async function runPipeline() {
        toggleFormLoading(true);

        const spillId = "spill_" + Math.random().toString(36).substr(2, 6);
        const imageTimestampVal = elements.imageTimestamp.value;
        const radiusVal = parseFloat(elements.coarseRadius.value);
        const windowVal = parseFloat(elements.coarseTimeWindow.value);
        const maxDistVal = parseFloat(elements.trajectoryMaxDistance.value);
        const rawPingsVal = elements.rawAisPingsJson.value;

        // Validation of json
        let parsedPings;
        try {
            parsedPings = JSON.parse(rawPingsVal);
        } catch (e) {
            alert("Invalid JSON in AIS Vessel Pings textarea!");
            toggleFormLoading(false);
            return;
        }

        if (state.isMockMode) {
            // Simulation Mode
            setTimeout(() => {
                const simulatedResult = generateMockPipelineResponse(
                    spillId,
                    new Date(imageTimestampVal),
                    parsedPings,
                    radiusVal,
                    windowVal,
                    maxDistVal
                );
                handlePipelineSuccess(simulatedResult);
            }, 2000);
        } else {
            // Live API Mode
            const formData = new FormData();
            formData.append('image_timestamp', new Date(imageTimestampVal).toISOString());
            formData.append('satellite_image', elements.satelliteImage.files[0]);
            formData.append('spill_mask', elements.spillMask.files[0]);
            formData.append('raw_ais_pings_json', rawPingsVal);
            formData.append('coarse_radius_km', radiusVal);
            formData.append('coarse_time_window_hours', windowVal);
            formData.append('trajectory_max_distance_km', maxDistVal);

            try {
                const res = await fetch(`${state.apiBaseUrl}/spill-detection/pipeline/full`, {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || "Server returned non-200 status");
                }

                const result = await res.json();
                handlePipelineSuccess(result);
            } catch (e) {
                console.error(e);
                alert(`API Error: ${e.message}. Falling back to Offline Simulation.`);
                elements.mockModeCheckbox.checked = true;
                state.isMockMode = true;
                
                // Fallback simulation run
                setTimeout(() => {
                    const simulatedResult = generateMockPipelineResponse(
                        spillId,
                        new Date(imageTimestampVal),
                        parsedPings,
                        radiusVal,
                        windowVal,
                        maxDistVal
                    );
                    handlePipelineSuccess(simulatedResult);
                }, 1500);
            }
        }
    }

    function handlePipelineSuccess(payload) {
        toggleFormLoading(false);

        // Add incident to state list
        const incidentRecord = {
            spill_id: payload.spill_id,
            incident_code: `INC-${payload.spill_id.toUpperCase()}`,
            timestamp: payload.detection.detection_timestamp,
            status: payload.status === 'COMPLETED' ? 'ATTRIBUTED' : 'DETECTED',
            data: payload
        };

        state.incidents.unshift(incidentRecord);
        state.activeIncident = incidentRecord;

        // Render Incidents Sidebar
        renderIncidentsList();

        // Switch to Command Centre view
        switchTab('command-centre');

        // Populate Incident Dashboard details
        populateIncidentDetails(incidentRecord);
    }

    function renderIncidentsList() {
        elements.incidentsListContainer.innerHTML = '';
        
        if (state.incidents.length === 0) {
            elements.incidentsListContainer.innerHTML = `
                <div class="incident-item-placeholder">
                    <i data-lucide="alert-triangle"></i>
                    <p>No incidents active.</p>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        state.incidents.forEach(inc => {
            const dateStr = new Date(inc.timestamp).toLocaleString();
            const isActive = state.activeIncident && state.activeIncident.spill_id === inc.spill_id;
            
            const cardEl = document.createElement('div');
            cardEl.className = `incident-card ${isActive ? 'active' : ''}`;
            cardEl.innerHTML = `
                <div class="card-top">
                    <span class="inc-code">${inc.incident_code}</span>
                    <span class="status-badge ${inc.status.toLowerCase()}">${inc.status}</span>
                </div>
                <div class="card-mid">Spill Location Registered</div>
                <div class="card-bot">
                    <i data-lucide="clock" style="width: 12px; height: 12px;"></i>
                    <span>${dateStr}</span>
                </div>
            `;
            
            cardEl.addEventListener('click', () => {
                state.activeIncident = inc;
                renderIncidentsList();
                populateIncidentDetails(inc);
            });

            elements.incidentsListContainer.appendChild(cardEl);
        });

        lucide.createIcons();
    }

    function populateIncidentDetails(inc) {
        const data = inc.data;
        
        // 1. Update Stepper Classes
        updateStepper(inc.status);

        // 2. Populate Geometry Metrics
        const det = data.detection;
        elements.valArea.textContent = det.area_km2.toFixed(2);
        elements.valPerimeter.textContent = det.perimeter_km.toFixed(2);
        elements.valPixels.textContent = det.spill_pixel_count;
        elements.valEccentricity.textContent = det.shape.eccentricity.toFixed(3);
        
        elements.valCentroid.textContent = `${det.centroid.latitude.toFixed(4)}, ${det.centroid.longitude.toFixed(4)}`;
        elements.valConfidence.textContent = det.confidence_score ? `${(det.confidence_score * 100).toFixed(0)}%` : '92% (Estimated)';
        elements.valComponents.textContent = det.connected_components.count;
        elements.valModelNotes.textContent = data.hindcast.is_simplified_model ? 'Simplified Drift' : 'Physics Ensemble';

        // 2b. Populate Drift Hindcasting Details (Section 03)
        const hind = data.hindcast;
        if (hind) {
            if (hind.wind_input) {
                elements.driftWindSpeed.textContent = `${hind.wind_input.speed_kmh.toFixed(1)} km/h`;
                elements.driftWindDir.textContent = `Direction: ${hind.wind_input.direction_deg.toFixed(0)}°`;
                elements.driftWindSource.textContent = `Source: ${hind.wind_input.source}`;
            }
            if (hind.current_input) {
                elements.driftCurrentSpeed.textContent = `${hind.current_input.speed_kmh.toFixed(1)} km/h`;
                elements.driftCurrentDir.textContent = `Direction: ${hind.current_input.direction_deg.toFixed(0)}°`;
                elements.driftCurrentSource.textContent = `Source: ${hind.current_input.source}`;
            }
            if (hind.model_params) {
                elements.driftWindageCoeff.textContent = `${hind.model_params.windage_coefficient} (${(hind.model_params.windage_coefficient * 100).toFixed(0)}%)`;
                elements.driftTimestep.textContent = `${hind.model_params.timestep_minutes} Minutes`;
                elements.driftLookback.textContent = `${hind.model_params.lookback_hours} Hours`;
                elements.driftLookahead.textContent = `${hind.model_params.lookahead_hours} Hours`;
            }
        }

        // 2c. Populate Section 04 (AIS Candidate Filtering)
        if (data.ais_analysis && data.ais_analysis.filter_output) {
            const filterOutput = data.ais_analysis.filter_output;
            const candidates = filterOutput.candidate_vessels || [];
            
            if (candidates.length === 0) {
                elements.filterResultsTbody.innerHTML = `
                    <tr>
                        <td colspan="3" class="empty-table-cell">No vessels passed the filter checks.</td>
                    </tr>
                `;
            } else {
                // Get vessel names mapping from score_output if they exist
                const namesMap = {};
                if (data.ais_analysis.score_output && data.ais_analysis.score_output.ranked_vessels) {
                    data.ais_analysis.score_output.ranked_vessels.forEach(v => {
                        namesMap[v.mmsi] = v.vessel_name || `MMSI: ${v.mmsi}`;
                    });
                }
                
                elements.filterResultsTbody.innerHTML = candidates.map(v => {
                    const name = namesMap[v.mmsi] || `MMSI: ${v.mmsi}`;
                    const passedBoth = v.passed_coarse_filter && v.passed_trajectory_filter;
                    const statusClass = passedBoth ? 'status-badge attributed' : 'status-badge detected';
                    const statusText = passedBoth ? 'PASSED' : 'FILTERED OUT';
                    
                    let reason = '';
                    if (passedBoth) {
                        reason = 'Vessel track falls within space-time drift corridor.';
                    } else if (!v.passed_coarse_filter) {
                        reason = `Exceeded coarse filtering search radius (${elements.coarseRadius.value} km).`;
                    } else {
                        reason = `Exceeded maximum drift deviation threshold (${elements.trajectoryMaxDistance.value} km).`;
                    }
                    
                    return `
                        <tr>
                            <td><strong>${v.mmsi}</strong><br><small style="color: var(--text-muted);">${name}</small></td>
                            <td><span class="${statusClass}">${statusText}</span></td>
                            <td>${reason}</td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // 2d. Populate Section 05 (AIS Suspect Vessel Scoring)
        if (data.ais_analysis && data.ais_analysis.score_output) {
            const scoreOutput = data.ais_analysis.score_output;
            const suspects = scoreOutput.ranked_vessels || [];
            
            if (suspects.length === 0) {
                elements.suspectsMetricsContainer.innerHTML = `
                    <div class="vessel-item-placeholder">
                        <i data-lucide="info"></i>
                        <p>No vessels scored.</p>
                    </div>
                `;
            } else {
                elements.suspectsMetricsContainer.innerHTML = suspects.map(v => {
                    const finalPct = (v.final_suspect_score * 100).toFixed(0);
                    const rankColor = v.rank === 1 ? 'var(--accent-red)' : 'var(--accent-orange)';
                    
                    return `
                        <div class="suspect-metric-item" style="border: 1px solid var(--border-color); padding: 16px; border-radius: 6px; background: #f8fafc; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-bottom: 4px;">${v.vessel_name || 'UNKNOWN'}</h4>
                                <span style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">
                                    Rank: #${v.rank} | MMSI: <strong>${v.mmsi}</strong>
                                </span>
                                <div style="display: flex; gap: 8px; margin-top: 8px; font-size: 0.7rem;">
                                    <span style="background:#e0f2fe; color:#0369a1; padding:2px 6px; border-radius:4px;">Prox: ${(v.proximity_score * 100).toFixed(0)}%</span>
                                    <span style="background:#f3e8ff; color:#6b21a8; padding:2px 6px; border-radius:4px;">Temp: ${(v.temporal_score * 100).toFixed(0)}%</span>
                                    <span style="background:#dcfce7; color:#15803d; padding:2px 6px; border-radius:4px;">Traj: ${(v.trajectory_score * 100).toFixed(0)}%</span>
                                    <span style="background:#fee2e2; color:#b91c1c; padding:2px 6px; border-radius:4px;">Behav: ${(v.behavior_score * 100).toFixed(0)}%</span>
                                </div>
                            </div>
                            <div style="text-align: right;">
                                <div style="font-size: 1.25rem; font-weight: 800; color: ${rankColor}; font-family: 'Outfit';">${finalPct}%</div>
                                <span style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; font-weight:700;">Liability Score</span>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        // 2e. Populate Section 06 (Attributed Liability & Incident File)
        if (data.ais_analysis && data.ais_analysis.score_output && data.ais_analysis.score_output.ranked_vessels) {
            const suspects = data.ais_analysis.score_output.ranked_vessels;
            const primary = suspects[0]; // Highest rank is primary
            
            if (!primary) {
                elements.primarySuspectFile.innerHTML = `
                    <div class="vessel-item-placeholder">
                        <i data-lucide="anchor"></i>
                        <p>No vessel currently attributed.</p>
                    </div>
                `;
            } else {
                const isLoitering = primary.anomaly.loitering_detected;
                const isBlackout = primary.anomaly.ais_gap_detected;
                
                elements.primarySuspectFile.innerHTML = `
                    <div class="suspect-header-block">
                        <div class="suspect-title-mmsi">
                            <h3>${primary.vessel_name || 'UNKNOWN'}</h3>
                            <span>MMSI: ${primary.mmsi} | IMO: ${primary.imo || 'N/A'}</span>
                        </div>
                        <div class="suspect-score-tag" style="background: var(--accent-red); color: #fff; border-radius: 4px; padding: 4px 10px;">
                            ${(primary.final_suspect_score * 100).toFixed(0)}% Liability
                        </div>
                    </div>
                    
                    <div class="suspect-details-list">
                        <div class="suspect-detail-item">
                            <span class="lbl">Vessel Dimensions</span>
                            <span class="val">${primary.length || '?'}m length / ${primary.width || '?'}m width</span>
                        </div>
                        <div class="suspect-detail-item">
                            <span class="lbl">Proximity to origin</span>
                            <span class="val" style="color: var(--accent-red); font-weight:700;">${primary.min_distance_to_origin_km.toFixed(2)} km</span>
                        </div>
                        <div class="suspect-detail-item">
                            <span class="lbl">Temporal Alignment gap</span>
                            <span class="val">${primary.time_delta_to_origin_min.toFixed(1)} mins</span>
                        </div>
                        <div class="suspect-detail-item">
                            <span class="lbl">Call Sign / Transponder</span>
                            <span class="val" style="font-family: monospace;">${primary.call_sign || 'N/A'}</span>
                        </div>
                    </div>
                    
                    <div style="margin-top: 16px;">
                        <h4 style="font-size:0.75rem; font-weight:700; color:var(--text-muted); margin-bottom:8px; text-transform:uppercase;">Identified Behavioral Anomalies</h4>
                        <div style="display:flex; flex-direction:column; gap:6px;">
                            <div class="anomaly-badge-item ${isBlackout ? 'critical' : ''}" style="padding: 6px 12px; border-radius: 4px; font-size: 0.8rem; display: flex; align-items: center; gap: 8px;">
                                <i data-lucide="${isBlackout ? 'alert-triangle' : 'check-circle'}" style="width:16px;"></i>
                                <span>${isBlackout ? `AIS Transponder Blackout (${primary.anomaly.gap_duration_min.toFixed(0)} min gap)` : 'Transponder Broadcast: Normal'}</span>
                            </div>
                            <div class="anomaly-badge-item ${isLoitering ? 'critical' : ''}" style="padding: 6px 12px; border-radius: 4px; font-size: 0.8rem; display: flex; align-items: center; gap: 8px;">
                                <i data-lucide="${isLoitering ? 'alert-triangle' : 'check-circle'}" style="width:16px;"></i>
                                <span>${isLoitering ? 'Slow Loitering Speed Profile Anomalies' : 'Speed Profile: Normal'}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="suspect-action-wrapper" style="margin-top:20px; border-top:1px solid var(--border-color); padding-top:12px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:0.7rem; color:var(--text-muted);">Attributed by OceanEye AI Engine</span>
                        <button class="btn-primary btn-xs" onclick="alert('Incident report archived and exported to Maritime Authority database.')">
                            File Legal Report
                        </button>
                    </div>
                `;
            }

            // Populate Incident Database Record file details
            elements.incidentRecordFile.innerHTML = `
                <div class="suspect-details-list" style="gap: 10px;">
                    <div class="suspect-detail-item">
                        <span class="lbl">Database Incident Code</span>
                        <span class="val" style="font-weight: 700;">INC-${data.spill_id.toUpperCase()}</span>
                    </div>
                    <div class="suspect-detail-item">
                        <span class="lbl">Observed Surface Area</span>
                        <span class="val">${det.area_km2.toFixed(2)} km²</span>
                    </div>
                    <div class="suspect-detail-item">
                        <span class="lbl">Detected Centroid</span>
                        <span class="val" style="font-family: monospace;">${det.centroid.latitude.toFixed(4)}°, ${det.centroid.longitude.toFixed(4)}°</span>
                    </div>
                    <div class="suspect-detail-item">
                        <span class="lbl">Surveillance Image Source</span>
                        <span class="val" style="font-family: monospace;">${elements.sarFileName.textContent}</span>
                    </div>
                    <div class="suspect-detail-item">
                        <span class="lbl">Accused Vessel MMSI</span>
                        <span class="val" style="color:var(--accent-red); font-weight:700;">${primary ? primary.mmsi : 'None Attributed'}</span>
                    </div>
                    <div class="suspect-detail-item">
                        <span class="lbl">Database Transaction State</span>
                        <span class="val" style="color: var(--accent-green); font-weight: 800; text-transform: uppercase;">COMMITTED</span>
                    </div>
                    <div class="suspect-detail-item" style="border-top:1px solid var(--border-color); padding-top:10px; font-size:0.75rem;">
                        <span class="lbl">SHA-256 Ledger Signature</span>
                        <span class="val" style="font-family: monospace; font-size:0.65rem; color:var(--text-muted); word-break:break-all;">
                            ${Math.random().toString(36).substring(2) + Math.random().toString(36).substring(2)}
                        </span>
                    </div>
                </div>
            `;
            lucide.createIcons();
        }

        // 3. Populate Vessel Attribution List
        renderVesselAttributionList(data.ais_analysis.score_output.ranked_vessels);

        // 4. Update Map Layers
        updateMapLayers(data);
    }

    function updateStepper(status) {
        const steps = [
            { id: elements.stepDetected, line: null },
            { id: elements.stepHindcasting, line: elements.line1 },
            { id: elements.stepFiltering, line: elements.line2 },
            { id: elements.stepScoring, line: elements.line3 },
            { id: elements.stepAttributed, line: elements.line4 }
        ];

        let targetIndex = 4; // Default to final attributed stage
        if (status === 'DETECTED') targetIndex = 0;
        else if (status === 'HINDCASTING') targetIndex = 1;
        else if (status === 'FILTERING') targetIndex = 2;
        else if (status === 'SCORING') targetIndex = 3;

        steps.forEach((step, idx) => {
            if (idx <= targetIndex) {
                step.id.classList.add('active');
                if (step.line) step.line.classList.add('active');
            } else {
                step.id.classList.remove('active');
                if (step.line) step.line.classList.remove('active');
            }
        });
    }

    function renderVesselAttributionList(vessels) {
        elements.vesselsListContainer.innerHTML = '';
        
        if (!vessels || vessels.length === 0) {
            elements.vesselsListContainer.innerHTML = `
                <div class="vessel-item-placeholder">
                    <i data-lucide="info"></i>
                    <p>No vessels matching search parameters.</p>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        vessels.forEach(v => {
            const scorePct = Math.round(v.final_suspect_score * 100);
            
            const row = document.createElement('div');
            row.className = 'vessel-rank-row';
            row.innerHTML = `
                <div class="rank-badge">${v.rank}</div>
                <div class="vessel-info">
                    <div class="vessel-name-lbl">${v.vessel_name || 'UNKNOWN'}</div>
                    <div class="vessel-mmsi-lbl">MMSI: ${v.mmsi}</div>
                </div>
                <div class="vessel-score-wrapper">
                    <div class="vessel-score-val">${scorePct}%</div>
                    <div class="vessel-score-lbl">Suspect</div>
                </div>
            `;

            row.addEventListener('click', () => {
                openVesselDetailModal(v);
            });

            elements.vesselsListContainer.appendChild(row);
        });

        lucide.createIcons();
    }

    function updateMapLayers(data) {
        const det = data.detection;
        const hind = data.hindcast;
        const vessels = data.ais_analysis.score_output.ranked_vessels;

        // Clear existing layers
        if (state.mapLayers.spillCentroid) state.map.removeLayer(state.mapLayers.spillCentroid);
        if (state.mapLayers.spillPolygon) state.map.removeLayer(state.mapLayers.spillPolygon);
        if (state.mapLayers.backwardPath) state.map.removeLayer(state.mapLayers.backwardPath);
        if (state.mapLayers.forwardPath) state.map.removeLayer(state.mapLayers.forwardPath);
        state.mapLayers.vesselMarkers.forEach(m => state.map.removeLayer(m));
        state.mapLayers.vesselMarkers = [];

        // 1. Plot Spill Centroid
        const centroidLatLng = [det.centroid.latitude, det.centroid.longitude];
        state.mapLayers.spillCentroid = L.circleMarker(centroidLatLng, {
            radius: 12,
            colorLength: 2,
            color: '#ffaa00',
            fillColor: '#ff5500',
            fillOpacity: 0.8,
            weight: 3
        }).addTo(state.map).bindPopup(`<b>Spill Centroid</b><br>Lat: ${det.centroid.latitude.toFixed(4)}<br>Lon: ${det.centroid.longitude.toFixed(4)}`);

        // Pan Map to Centroid
        state.map.setView(centroidLatLng, 9.5);

        // 2. Draw mock polygon for spill around centroid
        if (det.detected_mask && det.detected_mask.coordinates) {
            // Leaflet expects coordinates as [[lat, lon], ...]
            const coords = det.detected_mask.coordinates[0].map(pt => [pt[1], pt[0]]);
            state.mapLayers.spillPolygon = L.polygon(coords, {
                color: 'var(--accent-orange)',
                fillColor: 'var(--accent-orange)',
                fillOpacity: 0.35,
                weight: 1.5
            }).addTo(state.map);
        }

        // 3. Draw backward drift path (Hindcast)
        if (hind.backward_path && hind.backward_path.length > 0) {
            const points = hind.backward_path.map(pt => [pt.lat, pt.lon]);
            state.mapLayers.backwardPath = L.polyline(points, {
                color: '#ffcc00',
                weight: 3,
                dashArray: '5, 8',
                opacity: 0.8
            }).addTo(state.map).bindPopup("<b>Hindcast Drift Path</b><br>Historical tracking backwards to origin");
        }

        // 4. Draw forward drift path (Forecast)
        if (hind.forward_path && hind.forward_path.length > 0) {
            const points = hind.forward_path.map(pt => [pt.lat, pt.lon]);
            state.mapLayers.forwardPath = L.polyline(points, {
                color: 'var(--accent-blue)',
                weight: 3,
                dashArray: '10, 10',
                opacity: 0.8
            }).addTo(state.map).bindPopup("<b>Forecast Drift Path</b><br>Projected future drift trajectory");
        }

        // 5. Plot Vessel Markers (last known ping)
        if (vessels && vessels.length > 0) {
            vessels.forEach((v, idx) => {
                if (v.trajectory_points && v.trajectory_points.length > 0) {
                    // Draw full vessel path on map
                    const pathPoints = v.trajectory_points.map(pt => [pt.lat, pt.lon]);
                    const path = L.polyline(pathPoints, {
                        color: idx === 0 ? 'var(--accent-red)' : 'var(--accent-green)',
                        weight: 1.5,
                        opacity: 0.5
                    }).addTo(state.map);
                    
                    state.mapLayers.vesselMarkers.push(path);

                    // Last ping marker
                    const lastPing = v.trajectory_points[v.trajectory_points.length - 1];
                    
                    // Style first ranked vessel differently
                    const markerColor = idx === 0 ? 'var(--accent-red)' : 'var(--accent-green)';
                    const markerGlow = idx === 0 ? '0 0 10px var(--accent-red)' : '0 0 8px var(--accent-green)';

                    const vesselMarker = L.circleMarker([lastPing.lat, lastPing.lon], {
                        radius: 8,
                        color: '#fff',
                        fillColor: markerColor,
                        fillOpacity: 1,
                        weight: 1.5
                    }).addTo(state.map).bindPopup(`
                        <b>${v.vessel_name || 'UNKNOWN'}</b><br>
                        MMSI: ${v.mmsi}<br>
                        Rank: ${v.rank}<br>
                        Score: ${(v.final_suspect_score * 100).toFixed(0)}%
                    `);

                    vesselMarker.on('click', () => {
                        openVesselDetailModal(v);
                    });

                    state.mapLayers.vesselMarkers.push(vesselMarker);
                }
            });
        }
    }

    function openVesselDetailModal(v) {
        elements.modalVesselName.textContent = v.vessel_name || 'MV UNKNOWN';
        elements.modalVesselMmsi.textContent = `MMSI: ${v.mmsi}`;
        elements.modalImo.textContent = v.imo || 'N/A';
        elements.modalCallsign.textContent = v.call_sign || 'N/A';
        elements.modalType.textContent = v.vessel_type ? `Type ${v.vessel_type}` : 'Cargo';
        elements.modalDim.textContent = v.length && v.width ? `${v.length}m x ${v.width}m` : 'N/A';

        // Animate Score Bars
        const proxPct = Math.round(v.proximity_score * 100);
        const tempPct = Math.round(v.temporal_score * 100);
        const trajPct = Math.round(v.trajectory_score * 100);
        const behPct = Math.round(v.behavior_score * 100);

        elements.barProximity.style.width = '0%';
        elements.barTemporal.style.width = '0%';
        elements.barTrajectory.style.width = '0%';
        elements.barBehavior.style.width = '0%';

        setTimeout(() => {
            elements.barProximity.style.width = `${proxPct}%`;
            elements.lblProximity.textContent = `${proxPct}%`;
            
            elements.barTemporal.style.width = `${tempPct}%`;
            elements.lblTemporal.textContent = `${tempPct}%`;
            
            elements.barTrajectory.style.width = `${trajPct}%`;
            elements.lblTrajectory.textContent = `${trajPct}%`;
            
            elements.barBehavior.style.width = `${behPct}%`;
            elements.lblBehavior.textContent = `${behPct}%`;
        }, 150);

        // Load Anomalies
        elements.modalAnomaliesList.innerHTML = '';
        if (v.anomaly) {
            const a = v.anomaly;
            if (a.ais_gap_detected) {
                elements.modalAnomaliesList.appendChild(createAnomalyEl('AIS Transmitter Interruption Gap', `${a.gap_duration_min.toFixed(0)} min transponder blackout`, true));
            }
            if (a.speed_deviation_score > 0.4) {
                elements.modalAnomaliesList.appendChild(createAnomalyEl('Speed Profile Deviation', `Abrupt slowing down to ${(v.anomaly.speed_deviation_score * 15).toFixed(1)} knots near path intersect`, false));
            }
            if (a.course_deviation_score > 0.4) {
                elements.modalAnomaliesList.appendChild(createAnomalyEl('Course Steering Drift', `Course deviation anomaly detected during incident time-window`, false));
            }
            if (a.loitering_detected) {
                elements.modalAnomaliesList.appendChild(createAnomalyEl('Vessel Loitering Detected', `Unusual circular movement pattern in shipping lane`, true));
            }
        }
        
        if (elements.modalAnomaliesList.children.length === 0) {
            elements.modalAnomaliesList.innerHTML = '<li class="anomaly-badge-item" style="background: rgba(0, 255, 136, 0.05); border-color: rgba(0, 255, 136, 0.1); color: var(--accent-green);"><i data-lucide="shield-check"></i> No behavioral anomalies flagged.</li>';
        }

        // Load Explanations
        elements.modalExplanationsList.innerHTML = '';
        if (v.explanation && v.explanation.length > 0) {
            v.explanation.forEach(exp => {
                const li = document.createElement('li');
                li.textContent = exp;
                elements.modalExplanationsList.appendChild(li);
            });
        } else {
            elements.modalExplanationsList.innerHTML = '<li>Vessel followed a direct routing path. Low probability of spill event match.</li>';
        }

        elements.vesselDetailModal.classList.remove('hidden');
        lucide.createIcons();
    }

    function createAnomalyEl(title, desc, isCritical) {
        const li = document.createElement('li');
        li.className = `anomaly-badge-item ${isCritical ? 'critical' : ''}`;
        li.innerHTML = `
            <i data-lucide="${isCritical ? 'alert-octagon' : 'alert-circle'}"></i>
            <div>
                <strong>${title}</strong> - <span>${desc}</span>
            </div>
        `;
        return li;
    }

    function closeModal() {
        elements.vesselDetailModal.classList.add('hidden');
    }

    // ==========================================================================
    // Mock Data Generator (Simulates main.py Backend Pipeline Output)
    // ==========================================================================

    function generateMockPipelineResponse(spillId, obsTime, pings, radius, timeWindow, maxDist) {
        // Spill Centroid
        const centroidLat = 50.2224;
        const centroidLon = -1.4512;

        // Custom polygon coordinates representation (GeoJSON layout)
        const polyCoords = [[
            [centroidLon - 0.05, centroidLat - 0.02],
            [centroidLon + 0.03, centroidLat - 0.04],
            [centroidLon + 0.06, centroidLat + 0.01],
            [centroidLon - 0.01, centroidLat + 0.03],
            [centroidLon - 0.05, centroidLat - 0.02]
        ]];

        // Generate backwards path (drift hindcast)
        const backwardPoints = [];
        for (let i = 0; i <= 6; i++) {
            const factor = i / 6;
            // Drift is moving from West to East historically (pushed by current)
            backwardPoints.push({
                lat: centroidLat - (0.04 * factor),
                lon: centroidLon - (0.16 * factor),
                t: new Date(obsTime.getTime() - i * 60 * 60 * 1000).toISOString()
            });
        }

        // Origin estimate (the tail of the backward path)
        const originEstimate = backwardPoints[backwardPoints.length - 1];

        // Generate forward path (drift forecast)
        const forwardPoints = [];
        for (let i = 1; i <= 8; i++) {
            const factor = i / 8;
            forwardPoints.push({
                lat: centroidLat + (0.05 * factor),
                lon: centroidLon + (0.24 * factor),
                t: new Date(obsTime.getTime() + i * 60 * 60 * 1000).toISOString()
            });
        }

        // Match vessels & calculate mock scores based on pings coordinates
        const rankedVessels = pings.map((ping, idx) => {
            const isTarget = ping.mmsi === "235085300"; // MV KAPPA COMMANDER
            const isTanker = ping.mmsi === "477123900"; // MT VOYAGER

            let proximity_score, temporal_score, trajectory_score, behavior_score, final_score;
            let anomalies = {};
            let explanations = [];

            if (isTarget) {
                // Highly suspect vessel
                proximity_score = 0.94;
                temporal_score = 0.88;
                trajectory_score = 0.90;
                behavior_score = 0.82;
                final_score = 0.88;

                anomalies = {
                    ais_gap_detected: true,
                    gap_duration_min: 45.0,
                    speed_deviation_score: 0.78,
                    course_deviation_score: 0.65,
                    loitering_detected: true
                };

                explanations = [
                    "Vessel trajectory intersected the estimated spill drift path within a 1.2km radius.",
                    "AIS speed profile drops abnormally from 14.5 to 4.2 knots during transit through the spill zone, indicating vessel was loitering.",
                    "Transponder blackout gap of 45 minutes occurred during the exact estimated oil spill release time window."
                ];
            } else if (isTanker) {
                // Medium suspect tanker
                proximity_score = 0.55;
                temporal_score = 0.70;
                trajectory_score = 0.40;
                behavior_score = 0.15;
                final_score = 0.45;

                anomalies = {
                    ais_gap_detected: false,
                    gap_duration_min: 0.0,
                    speed_deviation_score: 0.12,
                    course_deviation_score: 0.08,
                    loitering_detected: false
                };

                explanations = [
                    "Tanker route passed within 4.5km of the spill centroid during the release window.",
                    "Vessel maintained constant high cruising speed (18 knots) and steady heading throughout transit.",
                    "No transmitter blackouts or anomalies flagged."
                ];
            } else {
                // Low suspect vessel
                proximity_score = 0.12;
                temporal_score = 0.20;
                trajectory_score = 0.10;
                behavior_score = 0.05;
                final_score = 0.12;

                anomalies = {
                    ais_gap_detected: false,
                    gap_duration_min: 0.0,
                    speed_deviation_score: 0.05,
                    course_deviation_score: 0.02,
                    loitering_detected: false
                };

                explanations = [
                    "Vessel route remained at outer boundary radius limits (15.6km) from estimated spill origin.",
                    "No spatial or temporal overlap anomalies detected."
                ];
            }

            // Extract trajectory points from raw pings list for this mmsi
            const vesselPings = pings.filter(p => p.mmsi === ping.mmsi)
                                    .map(p => ({ lat: p.lat, lon: p.lon, t: p.base_date_time }));

            return {
                mmsi: ping.mmsi,
                vessel_name: ping.vessel_name,
                imo: ping.imo,
                call_sign: ping.call_sign,
                vessel_type: ping.vessel_type,
                length: ping.length,
                width: ping.width,
                trajectory_points: vesselPings,
                min_distance_to_origin_km: isTarget ? 1.2 : (isTanker ? 4.5 : 15.6),
                time_delta_to_origin_min: isTarget ? 15.0 : (isTanker ? 48.0 : 120.0),
                anomaly: anomalies,
                proximity_score: proximity_score,
                temporal_score: temporal_score,
                trajectory_score: trajectory_score,
                behavior_score: behavior_score,
                final_suspect_score: final_score,
                rank: 0, // Assigned below
                explanation: explanations,
                weights_used: {
                    proximity: 0.4,
                    temporal: 0.15,
                    trajectory: 0.15,
                    behavior: 0.3
                }
            };
        });

        // Dedup list to distinct vessels (by MMSI)
        const distinctVessels = [];
        const seenMmsi = new Set();
        rankedVessels.forEach(v => {
            if (!seenMmsi.has(v.mmsi)) {
                seenMmsi.add(v.mmsi);
                distinctVessels.push(v);
            }
        });

        // Sort by final score descending and assign rank
        distinctVessels.sort((a, b) => b.final_suspect_score - a.final_suspect_score);
        distinctVessels.forEach((v, index) => {
            v.rank = index + 1;
        });

        return {
            spill_id: spillId,
            status: "COMPLETED",
            detection: {
                spill_detected: true,
                detection_timestamp: obsTime.toISOString(),
                confidence_score: 0.95,
                spill_pixel_count: 8520,
                area_km2: 12.45,
                perimeter_km: 26.8,
                centroid: {
                    latitude: centroidLat,
                    longitude: centroidLon
                },
                bounding_box: {
                    width_km: 8.5,
                    height_km: 4.2
                },
                shape: {
                    major_axis_km: 7.8,
                    minor_axis_km: 3.1,
                    eccentricity: 0.91
                },
                connected_components: {
                    count: 2,
                    largest_component_pixels: 7900
                },
                detected_mask: {
                    type: "Polygon",
                    coordinates: polyCoords
                },
                sar_file_path: "/path/to/sar_image.png",
                observation_time: obsTime.toISOString(),
                time_source: "filename"
            },
            hindcast: {
                spill_id: spillId,
                origin_estimate: originEstimate,
                backward_path: backwardPoints,
                forward_path: forwardPoints,
                current_input: {
                    speed_kmh: 3.2,
                    direction_deg: 245.0,
                    source: "live_api",
                    data_timestamp: obsTime.toISOString()
                },
                wind_input: {
                    speed_kmh: 18.5,
                    direction_deg: 260.0,
                    source: "live_api",
                    data_timestamp: obsTime.toISOString()
                },
                model_params: {
                    windage_coefficient: 0.03,
                    timestep_minutes: 30,
                    lookback_hours: 12,
                    lookahead_hours: 12
                },
                is_simplified_model: true,
                status: "SUCCESS"
            },
            ais_analysis: {
                filter_output: {
                    spill_id: spillId,
                    candidate_vessels: distinctVessels.map(v => ({
                        mmsi: v.mmsi,
                        trajectory_points: v.trajectory_points,
                        passed_coarse_filter: true,
                        passed_trajectory_filter: true
                    }))
                },
                score_output: {
                    spill_id: spillId,
                    ranked_vessels: distinctVessels
                }
            }
        };
    }
});
