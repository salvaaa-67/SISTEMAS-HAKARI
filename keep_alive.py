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
        return "Indisponível", "gray"
    elif ping < 150:
        return "Rápida", "green"
    elif ping < 300:
        return "Estável", "yellow"
    return "Lenta", "red"


@app.route("/api/status")
def api_status():
    uptime = format_uptime(time.time() - start_time)
    ping = get_ping()
    status, css_class = get_gateway_status(ping)

    return jsonify({
        "uptime": uptime,
        "ping": ping if ping is not None else "Indisponível",
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
  <meta name="theme-color" content="#000000" />
  <meta name="description" content="Acompanhe em tempo real o status, a latência e a hospedagem do bot HAKARI." />
  <title>HAKARI | Central de Status</title>

  <!-- Fontes Premium: Inter para texto, JetBrains Mono para números/dados -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">

  <style>
    :root {
      color-scheme: dark;
      --bg-base: #050505;
      --bg-surface: rgba(255, 255, 255, 0.03);
      --bg-surface-hover: rgba(255, 255, 255, 0.06);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-hover: rgba(255, 255, 255, 0.2);
      
      --text-primary: #ffffff;
      --text-secondary: #a1a1aa;
      --text-muted: #71717a;
      
      --accent-blue: #3b82f6;
      --accent-green: #10b981;
      --accent-red: #ef4444;
      --accent-yellow: #f59e0b;
      
      --glow-green: rgba(16, 185, 129, 0.4);
      --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      min-height: 100vh;
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
      position: relative;
    }

    /* Efeito de Fundo Animado (Aurora/Glow) */
    body::before {
      content: "";
      position: absolute;
      top: -20%;
      left: -10%;
      width: 50vw;
      height: 50vw;
      background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%);
      filter: blur(100px);
      z-index: -1;
      animation: floatBg 20s infinite alternate ease-in-out;
    }
    body::after {
      content: "";
      position: absolute;
      bottom: -20%;
      right: -10%;
      width: 40vw;
      height: 40vw;
      background: radial-gradient(circle, rgba(16, 185, 129, 0.1) 0%, transparent 70%);
      filter: blur(100px);
      z-index: -1;
      animation: floatBg 25s infinite alternate-reverse ease-in-out;
    }

    .page { 
      width: min(1100px, 100%); 
      margin: 0 auto; 
      padding: 40px 24px;
      animation: fadeInUp 0.8s ease-out forwards;
    }

    /* Header */
    .masthead {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 48px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border-color);
    }

    .brand { display: flex; align-items: center; gap: 16px; }

    .brand-mark {
      display: grid;
      width: 48px;
      height: 48px;
      place-items: center;
      border-radius: 14px;
      background: linear-gradient(135deg, #1e3a8a, #3b82f6);
      color: #fff;
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -.06em;
      box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.2);
    }

    .brand-name { font-size: 1.1rem; font-weight: 800; letter-spacing: .05em; }
    .brand-caption { margin-top: 2px; color: var(--text-secondary); font-size: .8rem; }

    .public-label {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 16px;
      border: 1px solid rgba(16, 185, 129, 0.2);
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.05);
      color: var(--accent-green);
      font-size: .8rem;
      font-weight: 600;
      backdrop-filter: blur(8px);
    }

    /* Hero Section */
    .hero {
      position: relative;
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: center;
      gap: 40px;
      padding: 56px;
      border-radius: 24px;
      background: linear-gradient(145deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.01));
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-glass);
      backdrop-filter: blur(20px);
      overflow: hidden;
      margin-bottom: 48px;
    }

    .hero-copy { position: relative; z-index: 1; }
    
    .eyebrow { 
      display: inline-block;
      color: var(--accent-blue); 
      font-size: .75rem; 
      font-weight: 700; 
      letter-spacing: .15em; 
      text-transform: uppercase; 
      margin-bottom: 16px;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(59, 130, 246, 0.1);
      border: 1px solid rgba(59, 130, 246, 0.2);
    }

    h1 {
      margin: 0 0 16px;
      font-size: clamp(3rem, 6vw, 4.5rem);
      line-height: 1;
      font-weight: 800;
      letter-spacing: -.04em;
      background: linear-gradient(to right, #ffffff, #a1a1aa);
      -webkit-background-clip: text;
      color: transparent;
    }

    .hero p { 
      max-width: 600px; 
      color: var(--text-secondary); 
      font-size: 1.05rem; 
      line-height: 1.7; 
    }
    
    .hero p strong { color: #fff; }

    .hero-avatar-wrapper {
      position: relative;
      z-index: 1;
      width: 200px;
      height: 200px;
      border-radius: 50%;
      padding: 6px;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-green));
      animation: float 6s ease-in-out infinite;
      box-shadow: 0 0 40px rgba(59, 130, 246, 0.3);
    }

    .hero-avatar {
      width: 100%;
      height: 100%;
      object-fit: cover;
      border-radius: 50%;
      border: 4px solid var(--bg-base);
    }

    /* Section Headings */
    .section-heading {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      margin-bottom: 24px;
    }

    .section-heading h2 { font-size: 1.4rem; font-weight: 700; letter-spacing: -.02em; }
    .section-heading p { margin-top: 6px; color: var(--text-secondary); font-size: .9rem; }
    
    .refresh-note { 
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--text-muted); 
      font-size: .8rem; 
      font-family: 'JetBrains Mono', monospace;
    }

    /* Metrics Grid */
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 20px;
      margin-bottom: 48px;
    }

    .metric, .card {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 20px;
      backdrop-filter: blur(12px);
      transition: all 0.3s ease;
    }

    .metric { 
      padding: 24px; 
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 160px;
      position: relative;
      overflow: hidden;
    }

    .metric:hover, .card:hover {
      background: var(--bg-surface-hover);
      border-color: var(--border-hover);
      transform: translateY(-4px);
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    }

    .metric-icon {
      position: absolute;
      top: 24px;
      right: 24px;
      color: var(--border-hover);
      opacity: 0.5;
      transition: all 0.3s ease;
    }
    .metric:hover .metric-icon { opacity: 1; color: var(--text-primary); }

    .metric-label { color: var(--text-secondary); font-size: .85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    
    .metric-value { 
      display: flex; 
      align-items: center; 
      gap: 12px; 
      margin-top: auto; 
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.5rem; 
      font-weight: 700; 
      color: var(--text-primary);
      transition: color 0.3s;
    }
    
    .metric-value.small { font-size: 1.2rem; }
    .metric-hint { margin-top: 8px; color: var(--text-muted); font-size: .75rem; }

    /* Pulse Dots & Status Colors */
    .pulse, .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent-green);
      box-shadow: 0 0 0 0 var(--glow-green);
      animation: pulseGlow 2s infinite;
    }

    .value-yellow { color: var(--accent-yellow); }
    .value-red { color: var(--accent-red); }
    .value-gray { color: var(--text-muted); }
    
    .status-dot.offline { 
      background: var(--accent-red); 
      box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); 
      animation: pulseGlowRed 2s infinite; 
    }

    /* Details Section */
    .details {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 24px;
    }

    .card { padding: 32px; }
    .card h2 { margin: 0 0 20px; font-size: 1.15rem; font-weight: 700; }
    .card p { margin-bottom: 16px; color: var(--text-secondary); font-size: .95rem; line-height: 1.7; }
    
    .detail-list { display: grid; gap: 20px; }
    .detail-item { display: flex; flex-direction: column; gap: 6px; }
    .detail-item strong { color: var(--text-primary); font-size: .85rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .detail-item span { color: var(--text-secondary); font-size: .95rem; line-height: 1.6; }
    
    .notice { 
      margin-top: 24px !important; 
      padding-top: 20px; 
      border-top: 1px solid var(--border-color); 
      font-size: .85rem !important; 
      color: var(--text-muted) !important;
      display: flex;
      gap: 10px;
    }

    /* Footer */
    .footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 64px;
      padding-top: 24px;
      border-top: 1px solid var(--border-color);
      color: var(--text-muted);
      font-size: .85rem;
    }

    /* Animations */
    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(30px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes float {
      0% { transform: translateY(0px); }
      50% { transform: translateY(-12px); }
      100% { transform: translateY(0px); }
    }
    
    @keyframes pulseGlow {
      0% { box-shadow: 0 0 0 0 var(--glow-green); }
      70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
      100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    @keyframes pulseGlowRed {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
      70% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }

    @keyframes floatBg {
      0% { transform: translate(0, 0) scale(1); }
      100% { transform: translate(5%, 5%) scale(1.1); }
    }

    /* Responsive */
    @media (max-width: 900px) {
      .details { grid-template-columns: 1fr; }
    }

    @media (max-width: 768px) {
      .hero { grid-template-columns: 1fr; text-align: center; padding: 40px 24px; }
      .eyebrow { margin: 0 auto 16px; }
      .hero-avatar-wrapper { margin: 0 auto; width: 160px; height: 160px; }
      .section-heading { flex-direction: column; align-items: flex-start; gap: 12px; }
      .footer { flex-direction: column; gap: 16px; text-align: center; }
    }

    @media (max-width: 480px) {
      .masthead { flex-direction: column; align-items: flex-start; gap: 20px; }
      .metrics { grid-template-columns: 1fr; }
      h1 { font-size: 2.5rem; }
    }
    
    /* Utilitário do JS para efeito de atualização */
    .data-updated {
      animation: flashText 0.8s ease-out;
    }
    @keyframes flashText {
      0% { color: var(--accent-green); text-shadow: 0 0 10px var(--glow-green); }
      100% { color: var(--text-primary); text-shadow: none; }
    }
  </style>
</head>

<body>
  <div class="page">
    <header class="masthead">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">H.</div>
        <div>
          <div class="brand-name">HAKARI</div>
          <div class="brand-caption">Central de Operações</div>
        </div>
      </div>
      <div class="public-label">
        <span class="pulse" aria-hidden="true"></span>
        Monitoramento ao vivo
      </div>
    </header>

    <main>
      <section class="hero" aria-labelledby="hero-title">
        <div class="hero-copy">
          <div class="eyebrow">Feito pelo salva · Bot para Discord</div>
          <h1 id="hero-title">HAKARI</h1>
          <p>Moderação, utilidades, automação e entretenimento em um só lugar. Criado em Python e conhecido pelo famoso comando <strong>/tomate</strong>.</p>
        </div>
        <div class="hero-avatar-wrapper">
          <img
            class="hero-avatar"
            src="https://i.postimg.cc/ncHYNPsF/4f1589b0a2549afad241ab8cc78b5828.jpg"
            alt="Avatar do bot HAKARI"
            width="200"
            height="200"
          />
        </div>
      </section>

      <section aria-labelledby="status-heading">
        <div class="section-heading">
          <div>
            <h2 id="status-heading">Status do Ecossistema</h2>
            <p>Métricas em tempo real da infraestrutura e latência.</p>
          </div>
          <span class="refresh-note" id="lastUpdated" aria-live="polite">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.92-10.44l5.36 5.36"/></svg>
            Conectando...
          </span>
        </div>

        <div class="metrics" aria-live="polite">
          <article class="metric">
            <svg class="metric-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            <div class="metric-label">Status do bot</div>
            <div class="metric-value"><span class="status-dot" aria-hidden="true"></span><span id="status">Online 24/7</span></div>
            <div class="metric-hint">UptimeRobot + Render</div>
          </article>
          
          <article class="metric">
            <svg class="metric-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <div class="metric-label">Tempo ativo</div>
            <div class="metric-value small" id="uptime">Aguardando...</div>
            <div class="metric-hint">Desde a inicialização do container</div>
          </article>
          
          <article class="metric">
            <svg class="metric-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>
            <div class="metric-label">Gateway do Discord</div>
            <div class="metric-value small" id="gateway">Aguardando...</div>
            <div class="metric-hint">Estabilidade de conexão à API</div>
          </article>
          
          <article class="metric">
            <svg class="metric-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div class="metric-label">Latência (Ping)</div>
            <div class="metric-value" id="ping">--- ms</div>
            <div class="metric-hint">Resposta do WebSocket</div>
          </article>
        </div>
      </section>

      <section class="details" aria-label="Sobre o HAKARI e detalhes técnicos">
        <article class="card">
          <h2>Sobre o HAKARI</h2>
          <p>Mantido com atualizações constantes e otimizado para alta disponibilidade, o HAKARI foi projetado para facilitar a administração de servidores enquanto oferece uma experiência moderna e intuitiva para administradores e membros.</p>
          <p>Mais do que um simples bot, é o resultado de dedicação, criatividade e muitas horas de desenvolvimento contínuo focando sempre em estabilidade e performance.</p>
          <div class="notice">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span>O propósito principal é entreter. Algumas informações de monitoramento podem sofrer delays conforme limitação das APIs externas.</span>
          </div>
        </article>

        <article class="card">
          <h2>Infraestrutura Técnica</h2>
          <div class="detail-list">
            <div class="detail-item">
              <strong>Desenvolvimento</strong>
              <span>Salvador, desenvolvedor dedicado à arquitetura e criação de funcionalidades inovadoras.</span>
            </div>
            <div class="detail-item">
              <strong>Hosting Cloud</strong>
              <span>Construído em Python. O serviço roda de maneira ininterrupta sustentado por clusters UptimeRobot e Render.</span>
            </div>
            <div class="detail-item">
              <strong>Porta de Comunicação</strong>
              <span id="port" style="font-family: 'JetBrains Mono', monospace; color: var(--text-primary);">Aguardando...</span>
            </div>
          </div>
          <div class="notice">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            <span>Segurança garantida. Nenhuma credencial ou token do bot é exposto neste ambiente.</span>
          </div>
        </article>
      </section>
    </main>

    <footer class="footer">
      <span>&copy; Status System HAKARI · Desenvolvido por Salvador</span>
      <span>Live Sync ativado · Atualização automática a cada 5s</span>
    </footer>
  </div>

  <script>
    // Função para aplicar animação de flash nos valores atualizados
    function animateValueUpdate(elementId, newValue) {
      const el = document.getElementById(elementId);
      if (el && el.textContent !== newValue) {
        el.textContent = newValue;
        el.classList.remove('data-updated');
        void el.offsetWidth; // Trigger reflow
        el.classList.add('data-updated');
      }
    }

    async function updateStatus() {
      const lastUpdated = document.getElementById("lastUpdated");
      const status = document.getElementById("status");
      const statusDot = document.querySelector(".status-dot");
      const gateway = document.getElementById("gateway");

      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error(`API status ${response.status}`);

        const data = await response.json();
        
        // Atualiza métricas com efeito visual simulando dashboard real-time
        animateValueUpdate("uptime", data.uptime ?? "Indisponível");
        animateValueUpdate("ping", data.ping !== null && data.ping !== undefined ? `${data.ping} ms` : "---");
        animateValueUpdate("port", data.port ?? "Protegida");
        animateValueUpdate("gateway", data.gateway_status ?? "Estável");

        gateway.className = "metric-value small";
        if (data.gateway_class === "yellow") gateway.classList.add("value-yellow");
        if (data.gateway_class === "red") gateway.classList.add("value-red");
        if (data.gateway_class === "gray") gateway.classList.add("value-gray");

        status.textContent = "Sistemas Operacionais";
        statusDot.classList.remove("offline");
        
        const now = new Date();
        lastUpdated.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.92-10.44l5.36 5.36"/></svg> Atualizado às ${now.toLocaleTimeString("pt-BR")}`;
        
      } catch (error) {
        document.getElementById("uptime").textContent = "---";
        document.getElementById("ping").textContent = "---";
        document.getElementById("port").textContent = "---";
        gateway.textContent = "Falha Crítica";
        gateway.className = "metric-value small value-red";
        
        status.textContent = "Sistema Indisponível";
        statusDot.classList.add("offline");
        
        lastUpdated.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> Falha de sincronização`;
        console.error("Falha ao consultar o status do HAKARI:", error);
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
