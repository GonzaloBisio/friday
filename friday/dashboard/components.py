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


def talk_bar_html(height: int = 70) -> str:
    """Barra inferior 'TALK TO FRIDAY' con waveform y micrófono animado."""
    return f"""
    <div style="width:100%;height:{height}px;background:linear-gradient(180deg,rgba(10,14,23,0.95),rgba(13,19,33,0.98));
         border:1px solid rgba(0,212,255,0.2);border-radius:16px;display:flex;align-items:center;
         justify-content:center;gap:20px;position:relative;overflow:hidden;">

        <!-- Dot pattern left -->
        <div style="display:flex;gap:4px;align-items:center;">
            <svg width="150" height="8"><g id="dots-left"></g></svg>
        </div>

        <!-- Central voice area -->
        <div style="display:flex;align-items:center;gap:16px;
                    background:linear-gradient(90deg,transparent,rgba(0,212,255,0.08),transparent);
                    padding:8px 30px;border-radius:30px;border:1px solid rgba(0,212,255,0.15);">

            <!-- Waveform -->
            <canvas id="talkWave" width="200" height="35" style="width:200px;height:35px;"></canvas>

            <!-- Label -->
            <div style="text-align:center;">
                <div style="font-family:'Exo 2',sans-serif;font-weight:700;font-size:15px;
                            letter-spacing:4px;color:#00d4ff;
                            text-shadow:0 0 15px rgba(0,212,255,0.5);">
                    TALK TO FRIDAY
                </div>
                <div style="font-family:'Share Tech Mono',monospace;font-size:10px;
                            color:rgba(0,212,255,0.5);letter-spacing:2px;
                            animation:blink-text 2s ease-in-out infinite;">
                    I am listening...
                </div>
            </div>

            <!-- Waveform right -->
            <canvas id="talkWave2" width="200" height="35" style="width:200px;height:35px;"></canvas>
        </div>

        <!-- Dot pattern right -->
        <div style="display:flex;gap:4px;align-items:center;">
            <svg width="150" height="8"><g id="dots-right"></g></svg>
        </div>
    </div>

    <style>
    @keyframes blink-text {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.3; }}
    }}
    </style>

    <script>
    (function() {{
        // Dot patterns
        ['dots-left','dots-right'].forEach(id => {{
            const g = document.getElementById(id);
            for (let i = 0; i < 25; i++) {{
                const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
                c.setAttribute('cx', 4 + i * 6);
                c.setAttribute('cy', 4);
                c.setAttribute('r', 2);
                c.setAttribute('fill', 'rgba(0,212,255,' + (0.15 + Math.random()*0.25) + ')');
                g.appendChild(c);
            }}
        }});

        // Mini waveforms
        ['talkWave','talkWave2'].forEach(canvasId => {{
            const cv = document.getElementById(canvasId);
            const ctx = cv.getContext('2d');
            const bars = 30;
            const phases = Array.from({{length:bars}}, ()=>Math.random()*Math.PI*2);
            const speeds = Array.from({{length:bars}}, ()=>0.03+Math.random()*0.05);

            function draw(t) {{
                requestAnimationFrame(draw);
                ctx.clearRect(0, 0, cv.width, cv.height);
                const barW = cv.width / bars * 0.6;
                const gap = cv.width / bars;
                const cy = cv.height / 2;

                for (let i = 0; i < bars; i++) {{
                    phases[i] += speeds[i];
                    const center = 1 - Math.abs(i-bars/2)/(bars/2)*0.6;
                    const amp = (0.2 + Math.sin(phases[i])*0.3) * center * cy * 0.7;
                    const h = Math.max(2, Math.abs(amp));
                    const x = i*gap + gap*0.2;

                    ctx.fillStyle = 'rgba(0,212,255,0.7)';
                    ctx.shadowColor = 'rgba(0,212,255,0.4)';
                    ctx.shadowBlur = 4;
                    ctx.beginPath();
                    ctx.roundRect(x, cy-h, barW, h*2, barW/2);
                    ctx.fill();
                }}
                ctx.shadowBlur = 0;
            }}
            draw(0);
        }});
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
