"""Componentes HTML/JS custom para el dashboard de FRIDAY."""


def friday_orb_html(height: int = 420) -> str:
    """Orbe 3D animado de FRIDAY con Three.js — wireframe icosaedro + partículas + glow."""
    return f"""
    <div id="orb-container" style="width:100%;height:{height}px;position:relative;overflow:hidden;
         background:radial-gradient(ellipse at center, rgba(0,212,255,0.06) 0%, transparent 70%);">
        <canvas id="orbCanvas" style="width:100%;height:100%;display:block;"></canvas>
        <div id="orb-label" style="position:absolute;bottom:20px;left:0;right:0;text-align:center;
             pointer-events:none;">
            <div style="font-family:'Exo 2',sans-serif;font-weight:900;font-size:42px;
                        letter-spacing:16px;
                        background:linear-gradient(180deg,#ffffff 0%,#00d4ff 100%);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        filter:drop-shadow(0 0 30px rgba(0,212,255,0.5));">
                F R I D A Y
            </div>
            <div style="font-family:'Exo 2',sans-serif;font-weight:400;font-size:15px;
                        letter-spacing:6px;color:rgba(0,212,255,0.7);margin-top:2px;">
                AI CORE
            </div>
            <div style="font-family:'Share Tech Mono',monospace;font-size:12px;
                        color:rgba(122,139,160,0.8);margin-top:6px;">
                v0.1.0
            </div>
        </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
    (function() {{
        const canvas = document.getElementById('orbCanvas');
        const container = document.getElementById('orb-container');
        const renderer = new THREE.WebGLRenderer({{ canvas, alpha: true, antialias: true }});
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.setSize(container.clientWidth, container.clientHeight);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
        camera.position.z = 4.5;

        // Wireframe icosahedron (main orb)
        const icoGeo = new THREE.IcosahedronGeometry(1.3, 2);
        const wireMat = new THREE.MeshBasicMaterial({{
            color: 0x00d4ff, wireframe: true, transparent: true, opacity: 0.35
        }});
        const wireOrb = new THREE.Mesh(icoGeo, wireMat);
        scene.add(wireOrb);

        // Inner sphere glow
        const innerGeo = new THREE.SphereGeometry(1.1, 32, 32);
        const innerMat = new THREE.MeshBasicMaterial({{
            color: 0x00d4ff, transparent: true, opacity: 0.04
        }});
        const innerSphere = new THREE.Mesh(innerGeo, innerMat);
        scene.add(innerSphere);

        // Outer glow ring
        const ringGeo = new THREE.TorusGeometry(1.6, 0.015, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({{
            color: 0x00d4ff, transparent: true, opacity: 0.25
        }});
        const ring1 = new THREE.Mesh(ringGeo, ringMat);
        ring1.rotation.x = Math.PI / 2;
        scene.add(ring1);

        const ring2 = ring1.clone();
        ring2.rotation.x = Math.PI / 2.5;
        ring2.rotation.z = Math.PI / 4;
        ring2.material = ringMat.clone();
        ring2.material.opacity = 0.15;
        scene.add(ring2);

        // Particles
        const particlesCount = 200;
        const particlesGeo = new THREE.BufferGeometry();
        const positions = new Float32Array(particlesCount * 3);
        const velocities = [];
        for (let i = 0; i < particlesCount; i++) {{
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            const r = 1.8 + Math.random() * 1.2;
            positions[i*3]   = r * Math.sin(phi) * Math.cos(theta);
            positions[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
            positions[i*3+2] = r * Math.cos(phi);
            velocities.push({{
                speed: 0.001 + Math.random() * 0.003,
                angle: Math.random() * Math.PI * 2,
                radius: r,
                phi: phi
            }});
        }}
        particlesGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        const particlesMat = new THREE.PointsMaterial({{
            color: 0x00d4ff, size: 0.025, transparent: true, opacity: 0.6,
            blending: THREE.AdditiveBlending, depthWrite: false
        }});
        const particles = new THREE.Points(particlesGeo, particlesMat);
        scene.add(particles);

        // Listening state vars
        let isListening = false;
        let listenIntensity = 0;
        let pulsePhase = 0;
        let targetIntensity = 0;

        // Simulate voice activity
        let voiceTimer = 0;
        let voiceActive = false;

        window.setFridayListening = function(state) {{
            isListening = state;
            targetIntensity = state ? 1.0 : 0.0;
        }};

        function animate(time) {{
            requestAnimationFrame(animate);
            const t = time * 0.001;

            // Smooth intensity transition
            listenIntensity += (targetIntensity - listenIntensity) * 0.05;

            // Simulate voice pulses when listening
            if (isListening) {{
                voiceTimer += 0.016;
                if (voiceTimer > 0.1 + Math.random() * 0.2) {{
                    voiceActive = !voiceActive;
                    voiceTimer = 0;
                    if (voiceActive) targetIntensity = 0.5 + Math.random() * 0.5;
                    else targetIntensity = 0.2 + Math.random() * 0.3;
                }}
            }}

            pulsePhase = t * 2;
            const pulse = 1 + Math.sin(pulsePhase) * 0.03 * (1 + listenIntensity * 3);

            // Rotate orb
            wireOrb.rotation.y = t * 0.3;
            wireOrb.rotation.x = Math.sin(t * 0.15) * 0.2;
            wireOrb.scale.setScalar(pulse);

            // Wireframe opacity reacts to listening
            wireMat.opacity = 0.3 + listenIntensity * 0.35;
            innerMat.opacity = 0.03 + listenIntensity * 0.08;

            // Rings rotate
            ring1.rotation.z = t * 0.2;
            ring2.rotation.z = -t * 0.15;
            ring2.rotation.y = t * 0.1;
            ringMat.opacity = 0.2 + Math.sin(t * 1.5) * 0.1 + listenIntensity * 0.2;

            // Particles orbit
            const pos = particlesGeo.attributes.position.array;
            for (let i = 0; i < particlesCount; i++) {{
                velocities[i].angle += velocities[i].speed * (1 + listenIntensity * 2);
                const v = velocities[i];
                const r = v.radius + Math.sin(t + i) * 0.1 * (1 + listenIntensity * 2);
                pos[i*3]   = r * Math.sin(v.phi) * Math.cos(v.angle);
                pos[i*3+1] = r * Math.sin(v.phi) * Math.sin(v.angle);
                pos[i*3+2] = r * Math.cos(v.phi);
            }}
            particlesGeo.attributes.position.needsUpdate = true;
            particlesMat.opacity = 0.5 + listenIntensity * 0.4;
            particlesMat.size = 0.025 + listenIntensity * 0.02;

            renderer.render(scene, camera);
        }}
        animate(0);

        // Start in idle, then toggle listening for demo
        setTimeout(() => window.setFridayListening(true), 2000);
        setTimeout(() => window.setFridayListening(false), 8000);
        setInterval(() => {{
            window.setFridayListening(true);
            setTimeout(() => window.setFridayListening(false), 4000 + Math.random() * 3000);
        }}, 10000);

        window.addEventListener('resize', () => {{
            const w = container.clientWidth;
            const h = container.clientHeight;
            camera.aspect = w / h;
            camera.updateProjectionMatrix();
            renderer.setSize(w, h);
        }});
    }})();
    </script>
    """


def voice_waveform_html(height: int = 60, bar_count: int = 40) -> str:
    """Waveform de voz animada — barras que simulan actividad de audio."""
    return f"""
    <div id="waveform-wrap" style="width:100%;height:{height}px;display:flex;align-items:center;
         justify-content:center;gap:2px;overflow:hidden;">
        <canvas id="waveCanvas" width="400" height="{height}" style="width:100%;height:100%;"></canvas>
    </div>
    <script>
    (function() {{
        const canvas = document.getElementById('waveCanvas');
        const ctx = canvas.getContext('2d');
        const bars = {bar_count};
        const phases = Array.from({{length: bars}}, () => Math.random() * Math.PI * 2);
        const speeds = Array.from({{length: bars}}, () => 0.02 + Math.random() * 0.04);
        const baseAmps = Array.from({{length: bars}}, () => 0.15 + Math.random() * 0.2);

        let listening = true;

        function draw(time) {{
            requestAnimationFrame(draw);
            const t = time * 0.001;
            const w = canvas.width;
            const h = canvas.height;
            ctx.clearRect(0, 0, w, h);

            const barW = (w / bars) * 0.65;
            const gap = w / bars;
            const centerY = h / 2;

            for (let i = 0; i < bars; i++) {{
                phases[i] += speeds[i];
                const centerFactor = 1 - Math.abs(i - bars/2) / (bars/2) * 0.5;
                let amp = listening
                    ? (baseAmps[i] + Math.sin(t * 3 + i * 0.3) * 0.15) * centerFactor
                    : 0.05;
                amp *= h * 0.4;

                const barH = Math.max(3, Math.abs(Math.sin(phases[i]) * amp));
                const x = i * gap + gap * 0.175;

                const gradient = ctx.createLinearGradient(x, centerY - barH, x, centerY + barH);
                gradient.addColorStop(0, 'rgba(0, 212, 255, 0.9)');
                gradient.addColorStop(0.5, 'rgba(0, 255, 200, 0.7)');
                gradient.addColorStop(1, 'rgba(0, 212, 255, 0.9)');

                ctx.fillStyle = gradient;
                ctx.shadowColor = 'rgba(0, 212, 255, 0.5)';
                ctx.shadowBlur = 6;

                // Draw rounded bar
                const radius = barW / 2;
                ctx.beginPath();
                ctx.roundRect(x, centerY - barH, barW, barH * 2, radius);
                ctx.fill();
            }}
            ctx.shadowBlur = 0;
        }}
        draw(0);
    }})();
    </script>
    """


def scanning_line_css() -> str:
    """CSS para la línea de escaneo horizontal que se mueve por los paneles."""
    return """
    <style>
    @keyframes scan-line {
        0% { top: -2px; opacity: 0; }
        10% { opacity: 1; }
        90% { opacity: 1; }
        100% { top: 100%; opacity: 0; }
    }
    .friday-card-scan::after {
        content: '';
        position: absolute;
        left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0,212,255,0.4), transparent);
        animation: scan-line 4s ease-in-out infinite;
        pointer-events: none;
    }
    @keyframes glow-border-pulse {
        0%, 100% { border-color: rgba(0,212,255,0.15); box-shadow: 0 0 8px rgba(0,212,255,0.03); }
        50% { border-color: rgba(0,212,255,0.3); box-shadow: 0 0 20px rgba(0,212,255,0.08); }
    }
    .friday-card-animated {
        animation: glow-border-pulse 4s ease-in-out infinite;
    }
    @keyframes float-up {
        0% { opacity: 0; transform: translateY(20px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    .fade-in { animation: float-up 0.6s ease-out forwards; }
    .fade-in-d1 { animation-delay: 0.1s; opacity: 0; }
    .fade-in-d2 { animation-delay: 0.2s; opacity: 0; }
    .fade-in-d3 { animation-delay: 0.3s; opacity: 0; }
    .fade-in-d4 { animation-delay: 0.4s; opacity: 0; }
    .fade-in-d5 { animation-delay: 0.5s; opacity: 0; }
    </style>
    """


def tool_activity_html(height: int = 280) -> str:
    """Feed de transparencia: qué tools ejecuta FRIDAY en vivo (running → ok/error).

    Hace fetch a /api/agent/activity cada 1s (mismo patrón que el log de voz, sin
    rerun de Streamlit). Cada evento muestra un ícono por estado, así Gonzalo VE qué
    hace FRIDAY — y si dice "listo" sin que aparezca un evento, queda en evidencia.
    """
    return f"""
    <div id="act-container" style="width:100%;max-height:{height}px;overflow-y:auto;
         font-family:'Share Tech Mono',monospace;font-size:11px;line-height:1.5;
         padding:10px 12px;background:rgba(10,14,23,0.6);border-radius:8px;
         border:1px solid rgba(0,212,255,0.12);">
        <div id="act-lines" style="color:#7a8ba0;">(sin actividad de tools todavía…)</div>
    </div>

    <script>
    (function() {{
        const API = 'http://127.0.0.1:8000/api/agent/activity?n=20';
        const el = document.getElementById('act-lines');
        const ICON = {{ running: '⏳', ok: '✅', error: '❌' }};
        const COL  = {{ running: '#ff8c00', ok: '#00ff88', error: '#ff3a3a' }};

        function esc(s) {{ return (s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

        function render(events) {{
            if (!events || events.length === 0) {{
                el.innerHTML = '<span style="color:#555;">(sin actividad de tools todavía…)</span>';
                return;
            }}
            // Más recientes arriba.
            el.innerHTML = events.slice().reverse().map(ev => {{
                const ic = ICON[ev.status] || '•';
                const col = COL[ev.status] || '#7a8ba0';
                const detail = ev.detail ? ' <span style="color:#5b6b80;">— ' + esc(ev.detail) + '</span>' : '';
                return '<div style="padding:3px 0;border-bottom:1px solid rgba(0,212,255,0.04);">' +
                       '<span style="color:#445;">' + ev.ts + '</span> ' +
                       '<span>' + ic + '</span> ' +
                       '<span style="color:' + col + ';font-weight:bold;">' + esc(ev.tool) + '</span>' +
                       detail + '</div>';
            }}).join('');
        }}

        async function tick() {{
            try {{
                const r = await fetch(API);
                const data = await r.json();
                render(data.events);
            }} catch(e) {{
                el.innerHTML = '<span style="color:#ff3a3a;">API no disponible</span>';
            }}
        }}
        tick();
        setInterval(tick, 1000);
    }})();
    </script>
    """


def live_mic_visualizer_html(height: int = 140) -> str:
    """Visualizador de voz EN VIVO estilo Wispr — barras que reaccionan a tu mic real.

    Usa Web Audio (`getUserMedia` + AnalyserNode) sobre el micrófono del navegador.
    Como el dashboard corre en localhost (contexto seguro), el browser deja usar el
    mic y las barras reaccionan a TU voz de verdad. Si negás el permiso o no hay mic,
    cae a una animación idle. Arriba muestra el estado real del listener (WAITING /
    LISTENING / CONVERSING) leído de /api/voice/log.
    """
    return f"""
    <div style="width:100%;background:rgba(10,14,23,0.55);border:1px solid rgba(0,212,255,0.14);
         border-radius:12px;padding:12px 14px;box-sizing:border-box;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span id="mic-dot" style="width:9px;height:9px;border-radius:50%;display:inline-block;
                      background:#7a8ba0;box-shadow:0 0 6px #7a8ba0;"></span>
                <span id="mic-state" style="color:#7a8ba0;font-family:'Exo 2',sans-serif;
                      font-weight:700;font-size:12px;letter-spacing:1.5px;">IDLE</span>
            </div>
            <span id="mic-hint" style="font-family:'Share Tech Mono',monospace;font-size:10px;color:#5b6b80;">
                conectando micrófono…</span>
        </div>
        <canvas id="micCanvas" style="width:100%;height:{height}px;display:block;"></canvas>
    </div>

    <script>
    (function() {{
        const canvas = document.getElementById('micCanvas');
        const ctx = canvas.getContext('2d');
        const dot = document.getElementById('mic-dot');
        const stateEl = document.getElementById('mic-state');
        const hint = document.getElementById('mic-hint');
        const BARS = 48;

        const STATE = {{
            idle:       {{ c:'#7a8ba0', t:'IDLE' }},
            waiting:    {{ c:'#ff8c00', t:'WAITING — Say "FRIDAY"' }},
            listening:  {{ c:'#00ff88', t:'LISTENING' }},
            conversing: {{ c:'#00d4ff', t:'CONVERSING' }},
        }};
        let accent = '#00d4ff';

        function resize() {{
            const dpr = window.devicePixelRatio || 1;
            canvas.width = canvas.clientWidth * dpr;
            canvas.height = canvas.clientHeight * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }}
        window.addEventListener('resize', resize);
        resize();

        // Estado real del listener (polling al log de voz).
        async function pollState() {{
            try {{
                const r = await fetch('http://127.0.0.1:8000/api/voice/log?n=5');
                const d = await r.json();
                const s = STATE[d.state] || STATE.idle;
                accent = s.c;
                stateEl.textContent = s.t; stateEl.style.color = s.c;
                dot.style.background = s.c; dot.style.boxShadow = '0 0 6px ' + s.c;
            }} catch(e) {{}}
        }}
        pollState();
        setInterval(pollState, 1000);

        // Mic real vía Web Audio. Fallback a animación idle si no hay permiso.
        let analyser = null, freq = null, micOn = false;
        const fallbackPhase = Array.from({{length: BARS}}, () => Math.random() * Math.PI * 2);

        async function initMic() {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
                const actx = new (window.AudioContext || window.webkitAudioContext)();
                const src = actx.createMediaStreamSource(stream);
                analyser = actx.createAnalyser();
                analyser.fftSize = 128;
                analyser.smoothingTimeConstant = 0.8;
                src.connect(analyser);
                freq = new Uint8Array(analyser.frequencyBinCount);
                micOn = true;
                hint.textContent = 'micrófono activo';
            }} catch(e) {{
                hint.textContent = 'sin micrófono (permiso denegado)';
            }}
        }}
        initMic();

        function draw(time) {{
            requestAnimationFrame(draw);
            const w = canvas.clientWidth, h = canvas.clientHeight, cy = h / 2;
            ctx.clearRect(0, 0, w, h);
            const gap = w / BARS, bw = gap * 0.55, t = time * 0.001;
            if (micOn && analyser) analyser.getByteFrequencyData(freq);

            for (let i = 0; i < BARS; i++) {{
                let amp;
                if (micOn && analyser) {{
                    const v = freq[Math.floor(i / BARS * freq.length)] / 255;  // 0..1
                    amp = Math.max(0.03, v) * h * 0.46;
                }} else {{
                    fallbackPhase[i] += 0.04;
                    const center = 1 - Math.abs(i - BARS/2) / (BARS/2) * 0.6;
                    amp = (0.05 + Math.abs(Math.sin(fallbackPhase[i] + t)) * 0.12) * center * h * 0.46;
                }}
                const bh = Math.max(3, amp);
                const x = i * gap + (gap - bw) / 2;
                const g = ctx.createLinearGradient(x, cy - bh, x, cy + bh);
                g.addColorStop(0, accent);
                g.addColorStop(0.5, 'rgba(0,255,200,0.85)');
                g.addColorStop(1, accent);
                ctx.fillStyle = g;
                ctx.shadowColor = accent; ctx.shadowBlur = 8;
                ctx.beginPath();
                ctx.roundRect(x, cy - bh, bw, bh * 2, bw / 2);
                ctx.fill();
            }}
            ctx.shadowBlur = 0;
        }}
        draw(0);
    }})();
    </script>
    """


def voice_log_html(height: int = 300) -> str:
    """Sección de Voice Activity con fetch cada 1s al endpoint /api/voice/log.

    Muestra estado (badge animado), transcripciones y respuestas en tiempo real
    sin recargar la página de Streamlit.
    """
    return f"""
    <div id="voice-log-container" style="width:100%;max-height:{height}px;overflow-y:auto;
         font-family:'Share Tech Mono',monospace;font-size:11px;line-height:1.6;
         padding:10px 12px;background:rgba(10,14,23,0.6);border-radius:8px;
         border:1px solid rgba(0,212,255,0.12);">
        <div id="voice-state-badge" style="margin-bottom:8px;display:flex;align-items:center;gap:8px;">
            <span id="voice-dot" style="width:8px;height:8px;border-radius:50%;display:inline-block;
                  background:#7a8ba0;box-shadow:0 0 4px #7a8ba0;"></span>
            <span id="voice-state-text" style="color:#7a8ba0;font-family:'Exo 2',sans-serif;
                  font-weight:600;font-size:11px;letter-spacing:1px;">IDLE</span>
        </div>
        <div id="voice-lines" style="color:#7a8ba0;">(esperando actividad...)</div>
    </div>

    <script>
    (function() {{
        const API = 'http://127.0.0.1:8000/api/voice/log?n=25';
        const linesEl = document.getElementById('voice-lines');
        const stateText = document.getElementById('voice-state-text');
        const stateDot = document.getElementById('voice-dot');

        const STATE_STYLE = {{
            idle:       {{ color: '#7a8ba0', bg: '#7a8ba0', text: 'IDLE' }},
            waiting:    {{ color: '#ff8c00', bg: '#ff8c00', text: 'WAITING — Say "FRIDAY"' }},
            listening:  {{ color: '#00ff88', bg: '#00ff88', text: 'LISTENING' }},
            conversing: {{ color: '#00d4ff', bg: '#00d4ff', text: 'CONVERSING' }},
            no_log:     {{ color: '#7a8ba0', bg: '#7a8ba0', text: 'NO LOG YET' }},
            error:      {{ color: '#ff3a3a', bg: '#ff3a3a', text: 'ERROR' }},
        }};

        function updateState(state) {{
            const s = STATE_STYLE[state] || STATE_STYLE.idle;
            stateText.textContent = s.text;
            stateText.style.color = s.color;
            stateDot.style.background = s.bg;
            stateDot.style.boxShadow = '0 0 6px ' + s.bg;
        }}

        function formatLines(lines) {{
            if (!lines || lines.length === 0) return '<span style="color:#555;">(sin actividad)</span>';
            return lines.map(ln => {{
                let cls = 'color:#7a8ba0;';
                if (ln.includes('WAKE WORD')) cls = 'color:#00ff88;font-weight:bold;';
                else if (ln.includes('Vos:')) cls = 'color:#ff8c00;';
                else if (ln.includes('FRIDAY:')) cls = 'color:#00d4ff;';
                else if (ln.includes('[tiempos]')) cls = 'color:#555;font-size:10px;';
                else if (ln.includes('conversacion')) cls = 'color:#7a8ba0;font-style:italic;';
                return '<span style="' + cls + '">' + ln.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</span>';
            }}).join('<br>');
        }}

        async function fetchLog() {{
            try {{
                const r = await fetch(API);
                const data = await r.json();
                updateState(data.state || 'idle');
                linesEl.innerHTML = formatLines(data.lines);
            }} catch(e) {{
                updateState('error');
                linesEl.innerHTML = '<span style="color:#ff3a3a;">API no disponible</span>';
            }}
        }}

        fetchLog();
        setInterval(fetchLog, 1000);
    }})();
    </script>
    """
