# keep_alive.py
from flask import Flask, render_template_string, jsonify
from threading import Thread
import time
import os
import math

app = Flask(__name__)

start_time = time.time()
bot_instance = None


def format_uptime(seconds):
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}min"


def get_ping():
  if bot_instance is not None:
    latency = bot_instance.latency
    if latency is not None and math.isfinite(latency):
      return round(latency * 1000)
    return None


def get_gateway_status(ping):
    if ping is None:
        return "INDISPONÍVEL", "gray"
    elif ping < 150:
        return "RÁPIDA", "green"
    elif ping < 300:
        return "ESTÁVEL", "yellow"
    return "LENTA", "red"


@app.route("/api/status")
def api_status():
    uptime = format_uptime(time.time() - start_time)
    ping = get_ping()
    status, css_class = get_gateway_status(ping)

    return jsonify({
        "uptime": uptime,
        "ping": ping if ping is not None else "---",
        "gateway_status": status,
        "gateway_class": css_class,
        "port": os.getenv("PORT", "5000")
    })


@app.route("/")
def home():
    html = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#F7F2EA" />
  <meta name="description" content="Status do bot HAKARI em tempo real." />
  <title>HAKARI | Central de Status</title>

  <!-- Fontes Premium -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=JetBrains+Mono:wght@400;600;700;800&display=swap" rel="stylesheet">

  <style>
    :root {
      /* Paleta Editorial Minimalista */
      --bg-base: #F7F2EA;
      --panel-bg: #FFFFFF;
      --border-color: #E6DFD3;
      --text-primary: #1C1917;
      --text-muted: #78716C;
      --accent-orange: #E8590C;
      --accent-amber: #F59E0B;
      --accent-peach: #FDBA74;
      --accent-lime: #84CC16;
      --accent-red: #EF4444;
      --shadow-relief: 0 10px 25px rgba(212, 200, 184, 0.6);
      --shadow-sm: 0 4px 12px rgba(0, 0, 0, 0.04);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      min-height: 100vh;
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: 'JetBrains Mono', monospace;
      -webkit-font-smoothing: antialiased;
      padding: 20px;
      overflow-x: hidden;
    }

    .dashboard { max-width: 1440px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }

    /* --- Cabeçalho --- */
    .header { display: flex; flex-direction: column; border-bottom: 2px solid var(--border-color); padding-bottom: 15px; }
    .header h1 { font-family: 'Inter', sans-serif; font-size: clamp(2.2rem, 4vw, 3.5rem); font-weight: 900; text-transform: uppercase; letter-spacing: -0.02em; color: var(--text-primary); margin-bottom: 12px; }
    .header-sub { display: flex; gap: 20px; font-size: 0.8rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase; }

    /* --- Métricas Topo --- */
    .top-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
    .metric-panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 18px; box-shadow: var(--shadow-sm); position: relative; }
    .metric-title { font-size: 0.75rem; color: var(--text-muted); font-weight: 700; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.8rem; font-weight: 800; color: var(--text-primary); display: flex; align-items: baseline; gap: 6px; }
    .metric-unit { font-size: 1rem; color: var(--text-muted); font-weight: 600; }
    .bar-chart-mini { position: absolute; right: 18px; bottom: 18px; display: flex; align-items: flex-end; gap: 4px; height: 25px; }
    .bar-chart-mini .bar { width: 5px; background: var(--accent-orange); border-radius: 2px; }
    .bar-1 { height: 40%; } .bar-2 { height: 70%; } .bar-3 { height: 100%; } .bar-4 { height: 60%; } .bar-5 { height: 80%; }

    /* --- Layout Principal (Esquerda / Núcleo / Direita) --- */
    .main-stage { display: grid; grid-template-columns: 280px 1fr 280px; gap: 15px; margin-top: 24px; position: relative; }
    .side-col { display: flex; flex-direction: column; gap: 20px; z-index: 2; }

    .module-box { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; box-shadow: var(--shadow-sm); position: relative; overflow: hidden; }
    .module-box::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--accent-peach); }
    .module-header { font-size: 0.8rem; font-weight: 800; color: var(--accent-orange); margin-bottom: 12px; letter-spacing: 0.05em; }
    .module-title { font-family: 'Inter', sans-serif; font-size: 1rem; font-weight: 700; margin-bottom: 8px; text-transform: uppercase; }
    .module-content { font-size: 0.8rem; color: var(--text-muted); line-height: 1.6; }
    .module-list { list-style: none; margin-top: 12px; }
    .module-list li { display: flex; justify-content: space-between; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border-color); font-size: 0.8rem; }
    .module-list li span:last-child { color: var(--text-primary); font-weight: 700; }

    /* --- NÚCLEO INFOGRÁFICO SVG --- */
    .core-area { position: relative; display: flex; align-items: center; justify-content: center; min-height: 480px; z-index: 1; }
    .core-svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: visible; }

    @keyframes dash-flow { to { stroke-dashoffset: -450; } }
    @keyframes twinkle   { 50% { opacity: .12; } }
    .wire { fill: none; stroke-linecap: round; }
    .pk { fill: none; stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 9 141; animation: dash-flow 3.2s linear infinite; }
    .pk.rev { animation-direction: reverse; }
    .spark { animation: twinkle 2.6s ease-in-out infinite; }
    @media (prefers-reduced-motion: reduce) { .pk, .spark { animation: none; } }

    /* --- Painéis Inferiores --- */
    .data-panels-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 10px; }
    .data-card { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; box-shadow: var(--shadow-sm); }
    .data-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; }
    .data-card-title { font-size: 0.85rem; font-weight: 800; color: var(--text-primary); letter-spacing: 0.05em; }
    .data-card-subtitle { font-size: 0.7rem; color: var(--text-muted); font-weight: 700; letter-spacing: 0.05em; }
    .running-dot { display: inline-block; width: 8px; height: 8px; background: var(--accent-orange); border-radius: 50%; margin-right: 6px; animation: blink 1s infinite; }
    @keyframes blink { 50% { opacity: 0; } }

    .pipeline-row, .matrix-row { display: flex; align-items: center; gap: 15px; margin-bottom: 14px; font-size: 0.8rem; }
    .pipe-label, .matrix-label { width: 85px; color: var(--text-muted); font-weight: 700; }
    .matrix-label { width: 100px; }
    .pipe-bar-container { flex: 1; display: flex; gap: 4px; height: 10px; align-items: center; }
    .pipe-segment { height: 100%; border-radius: 2px; }
    .pipe-segment.solid { background: var(--accent-orange); }
    .pipe-segment.faded { background: var(--accent-peach); opacity: 0.6; }
    .pipe-segment.empty { background: var(--border-color); }
    .pipe-value { width: 40px; text-align: right; font-weight: 800; color: var(--text-primary); }
    .matrix-chart { display: flex; align-items: center; gap: 10px; width: 100px; color: var(--text-muted); font-weight: 600; font-size: 0.75rem; }
    .matrix-chart svg { width: 35px; height: 14px; stroke: var(--text-muted); stroke-width: 1.5; fill: none; }
    .matrix-squares { flex: 1; display: flex; gap: 4px; }
    .sq { width: 10px; height: 14px; border-radius: 2px; }
    .sq.orange { background: var(--accent-orange); }
    .sq.yellow { background: var(--accent-amber); }
    .sq.gray { background: var(--border-color); }

    /* Console Terminal */
    .bottom-console { background: var(--text-primary); border-radius: 12px; padding: 20px; margin-top: 10px; box-shadow: var(--shadow-sm); }
    .console-header { font-size: 0.75rem; color: var(--accent-peach); font-weight: 800; margin-bottom: 12px; }
    .console-text { font-size: 0.85rem; color: #F3F4F6; display: flex; align-items: center; gap: 12px; font-family: 'JetBrains Mono', monospace; }
    .blinking-cursor { display: inline-block; width: 10px; height: 18px; background-color: var(--accent-peach); animation: blink 1s step-end infinite; }

    @media (max-width: 1024px) {
      .main-stage { grid-template-columns: 1fr; }
      .core-area { min-height: 450px; order: -1; }
      .side-col { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
      .data-panels-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <div class="dashboard">
    <!-- Header -->
    <header class="header">
      <h1>HAKARI CORE.</h1>
      <div class="header-sub">
        <span>ORQUESTRADOR EDITORIAL &rarr; FLUXO DE DADOS &rarr; PRODUCTION</span>
        <span>ENGINE V5</span>
      </div>
    </header>

    <!-- Top Metrics -->
    <section class="top-metrics">
      <div class="metric-panel">
        <div class="metric-title">LATENCY / DISTRIBUTION</div>
        <div class="metric-value"><span id="ping-val">--</span> <span class="metric-unit">ms</span></div>
        <div class="bar-chart-mini"><div class="bar bar-1"></div><div class="bar bar-2"></div><div class="bar bar-3"></div><div class="bar bar-4"></div><div class="bar bar-5"></div></div>
      </div>
      <div class="metric-panel">
        <div class="metric-title">SYSTEM LIFESPAN / UPTIME</div>
        <div class="metric-value" style="font-size: 1.5rem;"><span id="uptime-val">Aguardando...</span></div>
        <div class="bar-chart-mini"><div class="bar bar-2"></div><div class="bar bar-5"></div><div class="bar bar-1"></div><div class="bar bar-3"></div><div class="bar bar-4"></div></div>
      </div>
      <div class="metric-panel">
        <div class="metric-title">NETWORK / PORT</div>
        <div class="metric-value"><span id="port-val">--</span></div>
      </div>
      <div class="metric-panel">
        <div class="metric-title">SYSTEM STATE</div>
        <div class="metric-value" style="color: var(--accent-orange);"><span id="gateway-val">SYNCING</span></div>
      </div>
    </section>

    <!-- ÁREA PRINCIPAL: Painéis e SVG -->
    <section class="main-stage">
      <svg class="core-svg" id="core-svg" aria-hidden="true"></svg>

      <!-- Coluna Esquerda -->
      <div class="side-col">
        <div class="module-box">
          <div class="module-header">01 / IDENTIDADE</div>
          <div class="module-title">HAKARI BOT</div>
          <div class="module-content">Moderação, utilidades, automação e entretenimento perfeitamente orquestrados. Famoso pelo comando <strong>/tomate</strong>.</div>
        </div>
        <div class="module-box">
          <div class="module-header">02 / ARQUITETURA</div>
          <div class="module-title">SYSTEM SPECS</div>
          <ul class="module-list">
            <li><span>Linguagem</span> <span>Python 3</span></li>
            <li><span>Framework</span> <span>Discord.py</span></li>
            <li><span>Web Server</span> <span>Flask API</span></li>
          </ul>
        </div>
      </div>

      <!-- NÚCLEO CENTRAL INFOGRÁFICO -->
      <div class="core-area">
      </div>

      <!-- Coluna Direita -->
      <div class="side-col">
        <div class="module-box">
          <div class="module-header">03 / THREADING</div>
          <div class="module-title">SERVER DAEMON</div>
          <ul class="module-list">
            <li><span>Processo</span> <span>Thread Ativa</span></li>
            <li><span>Bloqueio</span> <span>Falso (Daemon)</span></li>
            <li><span>Execução</span> <span>Paralela / Async</span></li>
          </ul>
        </div>
        <div class="module-box">
          <div class="module-header">04 / VERIFICAÇÃO</div>
          <div class="module-title">LIVE CHECKS</div>
          <ul class="module-list">
            <li><span>API Status</span> <span style="color: var(--accent-lime);">PASS</span></li>
            <li><span>Web Socket</span> <span style="color: var(--accent-lime);">PASS</span></li>
            <li><span>Latency</span> <span style="color: var(--accent-amber);">TRACKING</span></li>
          </ul>
        </div>
      </div>

    </section>

    <!-- Terminal -->
    <section class="bottom-console">
      <div class="console-header">TERMINAL DE ESTADO</div>
      <div class="console-text">
        <span style="color: var(--accent-orange);">></span>
        <span id="console-msg">Iniciando sincronização da malha de dados... Conexão estável estabelecida.</span>
        <span class="blinking-cursor"></span>
      </div>
    </section>

    <!-- Painéis de Pipeline e Matrix -->
    <section class="data-panels-grid">

      <!-- BUILD PIPELINE -->
      <div class="data-card">
        <div class="data-card-header">
          <div>
            <div class="data-card-title">05 / BUILD PIPELINE</div>
            <div class="data-card-subtitle">COMPILE / BUNDLE / VERIFY</div>
          </div>
        </div>
        <div class="pipeline-row">
          <div class="pipe-label">NEXT.JS</div>
          <div class="pipe-bar-container"><div class="pipe-segment solid" style="width: 30%"></div><div class="pipe-segment solid" style="width: 35%"></div><div class="pipe-segment faded" style="width: 10%"></div><div class="pipe-segment empty" style="width: 25%"></div></div>
          <div class="pipe-value">78%</div>
        </div>
        <div class="pipeline-row">
          <div class="pipe-label">PRISMA</div>
          <div class="pipe-bar-container"><div class="pipe-segment solid" style="width: 20%"></div><div class="pipe-segment solid" style="width: 40%"></div><div class="pipe-segment faded" style="width: 10%"></div><div class="pipe-segment empty" style="width: 30%"></div></div>
          <div class="pipe-value">71%</div>
        </div>
        <div class="pipeline-row">
          <div class="pipe-label">REACT</div>
          <div class="pipe-bar-container"><div class="pipe-segment solid" style="width: 30%"></div><div class="pipe-segment solid" style="width: 30%"></div><div class="pipe-segment empty" style="width: 40%"></div></div>
          <div class="pipe-value">66%</div>
        </div>
        <div class="pipeline-row">
          <div class="pipe-label">NODE</div>
          <div class="pipe-bar-container"><div class="pipe-segment solid" style="width: 25%"></div><div class="pipe-segment solid" style="width: 35%"></div><div class="pipe-segment faded" style="width: 10%"></div><div class="pipe-segment empty" style="width: 30%"></div></div>
          <div class="pipe-value">73%</div>
        </div>
        <div class="pipeline-row">
          <div class="pipe-label">ASTRO</div>
          <div class="pipe-bar-container"><div class="pipe-segment solid" style="width: 30%"></div><div class="pipe-segment solid" style="width: 30%"></div><div class="pipe-segment faded" style="width: 5%"></div><div class="pipe-segment empty" style="width: 35%"></div></div>
          <div class="pipe-value">67%</div>
        </div>
      </div>

      <!-- VERIFICATION MATRIX -->
      <div class="data-card">
        <div class="data-card-header">
          <div>
            <div class="data-card-title">06 / VERIFICATION MATRIX</div>
            <div class="data-card-subtitle" style="color: var(--accent-orange);"><span class="running-dot"></span> RUNNING PROCESSES</div>
          </div>
        </div>
        <div class="matrix-row">
          <div class="matrix-label">UNIT TESTS</div>
          <div class="matrix-chart"><svg viewBox="0 0 30 12"><polyline points="0,6 5,2 10,10 15,6 20,8 25,2 30,6"/></svg> 313/428</div>
          <div class="matrix-squares"><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq gray"></div><div class="sq gray"></div></div>
        </div>
        <div class="matrix-row">
          <div class="matrix-label">E2E CHECKS</div>
          <div class="matrix-chart" style="color: var(--accent-lime);"><svg viewBox="0 0 30 12" style="stroke: var(--accent-lime);"><polyline points="0,8 10,8 15,3 20,8 30,8"/></svg> 72/102</div>
          <div class="matrix-squares"><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div></div>
        </div>
        <div class="matrix-row">
          <div class="matrix-label">TYPE VERIFY</div>
          <div class="matrix-chart"><svg viewBox="0 0 30 12"><polyline points="0,6 8,6 12,2 18,10 22,6 30,6"/></svg> 106/156</div>
          <div class="matrix-squares"><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div></div>
        </div>
        <div class="matrix-row">
          <div class="matrix-label">SECURITY</div>
          <div class="matrix-chart"><svg viewBox="0 0 30 12"><polyline points="0,6 5,4 10,8 15,2 20,10 25,6 30,6"/></svg> 15/24</div>
          <div class="matrix-squares"><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq orange"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div></div>
        </div>
        <div class="matrix-row">
          <div class="matrix-label">REGIONS</div>
          <div class="matrix-chart" style="color: var(--accent-lime);"><svg viewBox="0 0 30 12" style="stroke: var(--accent-lime);"><polyline points="0,6 15,6 20,2 25,10 30,6"/></svg> 2/4</div>
          <div class="matrix-squares"><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq yellow"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div><div class="sq gray"></div></div>
        </div>
      </div>
    </section>

  </div>

  <script>
(function () {
  const svg = document.getElementById('core-svg');
  const stage = document.querySelector('.main-stage');
  const core = document.querySelector('.core-area');
  const O = '#E8590C', A = '#F59E0B', P = '#FDBA74', L = '#84CC16', Y = '#D9C24A';
  const cols = ['#F2D3B0', '#F5BE8A', '#F7CFA2', '#E8D68C', '#F0B98A'];
  let seed = 23;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const R = (a, b) => a + rnd() * (b - a);
  const f = n => n.toFixed(1);
  const rad = d => d * Math.PI / 180;
  const bez = (p, t) => { const u = 1 - t; return [0, 1].map(k => u*u*u*p[0][k] + 3*u*u*t*p[1][k] + 3*u*t*t*p[2][k] + t*t*t*p[3][k]); };
  const spin = (dur, dir) => `<animateTransform attributeName="transform" type="rotate" from="0" to="${dir * 360}" dur="${dur}s" repeatCount="indefinite"/>`;

  function draw() {
    seed = 23;
    const sr = stage.getBoundingClientRect(), cr = core.getBoundingClientRect();
    const W = sr.width, H = sr.height;
    const cx = cr.left - sr.left + cr.width / 2;
    let cy = cr.top - sr.top + cr.height / 2;
    let top0 = Infinity, bot0 = -Infinity;                          // alinha o núcleo ao meio dos cartões
    stage.querySelectorAll('.module-box').forEach(b => {
      const r = b.getBoundingClientRect();
      if (r.right <= cr.left + 40 || r.left >= cr.right - 40) { top0 = Math.min(top0, r.top - sr.top); bot0 = Math.max(bot0, r.bottom - sr.top); }
    });
    if (isFinite(top0)) cy = (top0 + bot0) / 2;
    const CORE_SCALE = 0.72;                                       // 1 = tamanho anterior; menor = núcleo menor
    const s = Math.min(cr.width, 650) / 2 / 300 * CORE_SCALE; // escala do núcleo
    svg.setAttribute('viewBox', `0 0 ${f(W)} ${f(H)}`);

    /* ---------- 1) Pontos de saída: borda interna de cada cartão lateral ---------- */
    const anchors = [];
    stage.querySelectorAll('.module-box').forEach(b => {
      const r = b.getBoundingClientRect();
      const left = r.right <= cr.left + 40, right = r.left >= cr.right - 40;
      if (!left && !right) return;                                  // celular: cartões empilhados, sem fios
      const edge = left ? r.right - sr.left : r.left - sr.left;
      const dir = left ? 1 : -1, top = r.top - sr.top;
      for (let k = 0; k < 4; k++) anchors.push({ edge, ax: edge + dir * 8, ay: top + r.height * (.2 + .6 * k / 3), dir });
    });

    /* ---------- 2) Fios: cada cartão -> triângulo central ---------- */
    let defs = '', wires = '', dashes = '', pk = '', arrows = '', nodes = '', n = 0;
    anchors.forEach(a => {
      nodes += `<line x1="${f(a.edge)}" y1="${f(a.ay)}" x2="${f(a.ax)}" y2="${f(a.ay)}" stroke="${O}" stroke-width="1.4"/>`
             + `<circle cx="${f(a.ax)}" cy="${f(a.ay)}" r="4.5" fill="#F7F2EA" stroke="${O}" stroke-width="1.4"/><circle cx="${f(a.ax)}" cy="${f(a.ay)}" r="1.7" fill="${O}"/>`;
      for (let v = 0; v < 4; v++, n++) {
        const dx = cx - a.ax;
        let ey = cy - (a.ay - cy) * R(.1, .22) + R(-14, 14);
        ey = Math.max(cy - 55 * s, Math.min(cy + 110 * s, ey));
        const p = [[a.ax, a.ay],
                   [a.ax + dx * R(.3, .5), a.ay + (v ? R(-28, 28) : 0)],
                   [cx - a.dir * R(80, 150) * s, ey + R(-45, 45)],
                   [cx - a.dir * R(0, 8), ey]];
        defs += `<path id="w${n}" d="M ${p[0].map(f)} C ${p[1].map(f)}, ${p[2].map(f)}, ${p[3].map(f)}"/>`;
        const c = cols[n % 5];
        wires += `<use href="#w${n}" stroke="${c}" stroke-width="${v ? .6 : 1.1}" opacity="${v ? .8 : 1}"/>`;
        for (let k = 0; k < 3; k++) {
          const t = k === 0 ? R(.1, .45) : R(.5, .92), q = bez(p, t), b = bez(p, t + .015);
          const ang = Math.atan2(b[1] - q[1], b[0] - q[0]), h = R(4, 9);
          dashes += `<line x1="${f(q[0] - Math.cos(ang) * h)}" y1="${f(q[1] - Math.sin(ang) * h)}" x2="${f(q[0] + Math.cos(ang) * h)}" y2="${f(q[1] + Math.sin(ang) * h)}" stroke="${rnd() > .35 ? O : A}" stroke-width="${f(R(1.8, 3.2))}" stroke-linecap="round"/>`;
        }
        if (v === 0 || v === 2) pk += `<use href="#w${n}" class="pk${a.dir < 0 ? ' rev' : ''}" stroke="${n % 6 ? O : A}" style="animation-delay:-${f(R(0, 3))}s"/>`;
        if (v === 1) arrows += `<polygon points="-6,-3.5 5,0 -6,3.5" fill="${O}"><animateMotion dur="${f(R(2.6, 4))}s" begin="-${f(R(0, 3))}s" repeatCount="indefinite" rotate="auto"><mpath href="#w${n}"/></animateMotion></polygon>`;
      }
    });

    /* ---------- 3) Núcleo (desenhado em 800x600 e reposicionado/escalado) ---------- */
    const CX = 400, CY = 300;
    const pt = (r, d) => [CX + r * Math.cos(rad(d)), CY + r * Math.sin(rad(d))];
    const target = (r, d, c) => { const [x, y] = pt(r, d); return `<g transform="translate(${f(x)} ${f(y)})"><circle r="6" fill="#F7F2EA" stroke="${c}" stroke-width="1.5"/><circle r="2" fill="${c}"/></g>`; };
    const orbits = `
      <circle cx="${CX}" cy="${CY}" r="165" fill="none" stroke="${L}" stroke-width=".9" stroke-dasharray="3 7"/>
      <circle cx="${CX}" cy="${CY}" r="215" fill="none" stroke="${O}" stroke-width=".7" opacity=".5"/>
      <circle cx="${CX}" cy="${CY}" r="262" fill="none" stroke="${A}" stroke-width=".8" stroke-dasharray="40 10 5 10" opacity=".7"/>
      <circle cx="${CX + 8}" cy="${CY - 6}" r="236" fill="none" stroke="${Y}" stroke-width=".8" opacity=".8"/>
      <ellipse cx="${CX}" cy="${CY}" rx="272" ry="190" transform="rotate(-18 ${CX} ${CY})" fill="none" stroke="${A}" stroke-width=".8" opacity=".7"/>
      <ellipse cx="${CX}" cy="${CY}" rx="250" ry="172" transform="rotate(22 ${CX} ${CY})" fill="none" stroke="${L}" stroke-width=".9" opacity=".85"/>
      <g transform="translate(${CX} ${CY})">
        <g>${spin(40, 1)}<circle r="190" fill="none" stroke="${O}" stroke-width="3" stroke-linecap="round" stroke-dasharray="18 120 6 90"/></g>
        <g>${spin(55, -1)}<circle r="236" fill="none" stroke="${L}" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="30 200"/></g>
        <g>${spin(70, 1)}<circle r="262" fill="none" stroke="${O}" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="14 160 8 120"/></g>
      </g>
      ${target(165, 200, L)}${target(215, -62, O)}${target(215, 118, A)}${target(250, 24, L)}${target(270, 196, A)}${target(236, -20, Y)}`;

    let cubes = '';
    for (let k = 0; k < 12; k++) {
      const rr = 218 + R(-6, 8) + (k === 6 ? 14 : 0), by = k % 2 ? 7 : -8, col = k % 3 === 1 ? A : O;
      cubes += `<g transform="rotate(${k * 30}) translate(0 -${f(rr)}) rotate(${f(R(-28, 28))})">
        <rect x="-19" y="-13" width="42" height="32" rx="5" fill="#EFE2CF"/>
        <rect x="-21" y="-16" width="42" height="32" rx="5" fill="url(#cf)" stroke="#F1E4D2" filter="url(#sc)"/>
        <line x1="-11" y1="${by}" x2="${f(R(2, 10))}" y2="${by}" stroke="${col}" stroke-width="2.6" stroke-linecap="round"/>
        <circle cx="12" cy="${-by}" r="1.6" fill="${P}"/></g>`;
    }
    const lens = [52, 34, 60, 40, 47, 32], rc = [O, A, O, Y, O, A];
    let rays = '';
    for (let k = 0; k < 24; k++) rays += `<line y1="-21" y2="-${lens[k % 6]}" transform="rotate(${k * 15})" stroke="${rc[k % 6]}" stroke-width="${k % 2 ? 3 : 4}" stroke-linecap="round"/>`;

    let sparks = '';
    for (let k = 0; k < 24; k++) {
      const r = R(255, 300);
      sparks += `<line class="spark" style="animation-delay:-${f(R(0, 2.6))}s" y1="-${f(r)}" y2="-${f(r + R(8, 14))}" transform="translate(${CX} ${CY}) rotate(${f(R(0, 360))})" stroke="${rnd() > .4 ? O : A}" stroke-width="2" stroke-linecap="round"/>`;
    }
    for (let k = 0; k < 9; k++) {
      const [x, y] = pt(R(245, 295), R(0, 360));
      sparks += k < 6 ? `<circle cx="${f(x)}" cy="${f(y)}" r="${f(R(1.5, 3))}" fill="${[O, A, P][k % 3]}"/>` : `<circle cx="${f(x)}" cy="${f(y)}" r="4.5" fill="none" stroke="${A}" stroke-width="1"/>`;
    }
    const tri = z => [[253, 215], [547, 215], [400, 470]].map(([x, y]) => `${f(CX + (x - CX) * z)},${f(CY + (y - CY) * z)}`).join(' ');

    svg.innerHTML = `
      <defs>
        <filter id="sr" x="-30%" y="-30%" width="160%" height="175%"><feDropShadow dx="0" dy="16" stdDeviation="14" flood-color="#D4C8B8" flood-opacity=".85"/></filter>
        <filter id="sc" x="-40%" y="-40%" width="180%" height="190%"><feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#D4C8B8" flood-opacity=".55"/></filter>
        <linearGradient id="face" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".7" stop-color="#FFF7EC"/><stop offset="1" stop-color="#FFEBD3"/></linearGradient>
        <linearGradient id="rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFD9B0"/><stop offset="1" stop-color="#F9A95E"/></linearGradient>
        <linearGradient id="cf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#FFF4E6"/></linearGradient>
        <radialGradient id="glow"><stop offset="0" stop-color="#FFE3C2" stop-opacity=".9"/><stop offset="1" stop-color="#FFE3C2" stop-opacity="0"/></radialGradient>
        ${defs}
      </defs>
      <g class="wire">${wires}</g><g class="wire">${dashes}</g>${arrows}${pk}${nodes}
      <g transform="translate(${f(cx - CX * s)} ${f(cy - CY * s)}) scale(${f(s)})">
        ${orbits}${sparks}
        <g transform="translate(${CX} ${CY})"><g>${spin(70, -1)}${cubes}</g></g>
        <polygon points="253,226 547,226 400,481" fill="#EADBC6" stroke="#EADBC6" stroke-width="12" stroke-linejoin="round"/>
        <polygon points="253,215 547,215 400,470" fill="#fff" stroke="url(#rim)" stroke-width="12" stroke-linejoin="round" filter="url(#sr)"/>
        <polygon points="${tri(.92)}" fill="url(#face)" stroke="#FFD9B3" stroke-width="3" stroke-linejoin="round"/>
        <polygon points="${tri(.78)}" fill="none" stroke="${P}" stroke-width="1" opacity=".4" stroke-linejoin="round"/>
        <polygon points="${tri(.62)}" fill="none" stroke="${P}" stroke-width="1" opacity=".25" stroke-linejoin="round"/>
        <circle cx="${CX}" cy="${CY}" r="80" fill="url(#glow)"/>
        <circle cx="${CX}" cy="${CY}" r="15" fill="none" stroke="${P}" stroke-width=".8"/>
        <g transform="translate(${CX} ${CY})"><g>${spin(28, 1)}${rays}</g></g>
      </g>`;
  }

  // redesenha quando o layout muda (resize, fontes, cartões)
  let raf;
  const redraw = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); };
  new ResizeObserver(redraw).observe(stage);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(redraw);
  draw();
})();
</script>

  <script>
    async function updateStatus() {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error("API Offline");
        const data = await response.json();

        document.getElementById("ping-val").textContent = data.ping !== "---" ? data.ping : "--";
        document.getElementById("uptime-val").textContent = data.uptime || "Calculando...";
        document.getElementById("gateway-val").textContent = data.gateway_status || "UNKNOWN";
        document.getElementById("port-val").textContent = data.port || "5000";

        const gatewayEl = document.getElementById("gateway-val");
        if (data.gateway_class === "red") gatewayEl.style.color = "var(--accent-red)";
        else if (data.gateway_class === "yellow") gatewayEl.style.color = "var(--accent-amber)";
        else gatewayEl.style.color = "var(--accent-lime)";

        const date = new Date().toLocaleTimeString("pt-BR");
        document.getElementById("console-msg").textContent = `[${date}] Orquestração de dados bem sucedida. Latência processada. Intervalo de recuo: 5000ms.`;

      } catch (error) {
        document.getElementById("ping-val").textContent = "ERR";
        document.getElementById("gateway-val").textContent = "OFFLINE";
        document.getElementById("gateway-val").style.color = "var(--accent-red)";
        document.getElementById("console-msg").textContent = "[CRITICAL ERROR] Falha catastrófica ao comunicar com o servidor principal.";
      }
    }

    updateStatus();
    setInterval(updateStatus, 5000);
  </script>
</body>
</html>
"""

    return render_template_string(html)


def run():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


def keep_alive(bot=None):
    global bot_instance
    bot_instance = bot

    server = Thread(target=run)
    server.daemon = True
    server.start()