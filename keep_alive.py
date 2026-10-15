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
  <meta name="theme-color" content="#f4f7fb" />
  <meta name="description" content="Acompanhe em tempo real o status, a latência e a hospedagem do bot HAKARI." />
  <title>HAKARI | Central de status</title>

  <style>
    :root {
      color-scheme: light;
      --ink: #172338;
      --muted: #68758a;
      --line: #e5eaf1;
      --surface: #fff;
      --canvas: #f4f7fb;
      --blue: #4968df;
      --green: #14845d;
      --green-soft: #e8f7f0;
      --shadow: 0 18px 50px rgba(34, 53, 86, .08);
    }

    * { box-sizing: border-box; }

    body {
      min-height: 100vh;
      margin: 0;
      padding: 34px 22px 28px;
      background: var(--canvas);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    .page { width: min(1080px, 100%); margin: 0 auto; }

    .masthead {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 30px;
    }

    .brand { display: flex; align-items: center; gap: 12px; }

    .brand-mark {
      display: grid;
      width: 42px;
      height: 42px;
      place-items: center;
      border-radius: 13px;
      background: #202f51;
      color: #fff;
      font-size: 15px;
      font-weight: 800;
      letter-spacing: -.06em;
    }

    .brand-name { font-size: .96rem; font-weight: 800; letter-spacing: .04em; }
    .brand-caption { margin-top: 3px; color: var(--muted); font-size: .76rem; }

    .public-label {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 13px;
      border: 1px solid #dcefe6;
      border-radius: 999px;
      background: #f5fbf8;
      color: #287351;
      font-size: .76rem;
      font-weight: 700;
    }

    .pulse, .status-dot {
      width: 8px;
      height: 8px;
      flex: 0 0 auto;
      border-radius: 50%;
      background: #21a574;
      box-shadow: 0 0 0 4px rgba(33, 165, 116, .12);
    }

    .hero {
      position: relative;
      overflow: hidden;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 250px;
      align-items: center;
      gap: 28px;
      min-height: 280px;
      padding: 42px 48px;
      border-radius: 22px;
      background: #202f51;
      color: #fff;
      box-shadow: 0 20px 55px rgba(32, 47, 81, .16);
    }

    .hero::after {
      position: absolute;
      top: -130px;
      right: 80px;
      width: 360px;
      height: 360px;
      border: 1px solid rgba(255, 255, 255, .08);
      border-radius: 50%;
      content: "";
      box-shadow: 0 0 0 45px rgba(255, 255, 255, .025), 0 0 0 90px rgba(255, 255, 255, .02);
      pointer-events: none;
    }

    .hero-copy, .hero-avatar { position: relative; z-index: 1; }
    .eyebrow { color: #aab9dd; font-size: .72rem; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }

    h1 {
      margin: 14px 0 13px;
      font-size: clamp(3.2rem, 8vw, 5.3rem);
      line-height: .92;
      letter-spacing: -.085em;
    }

    .hero p { max-width: 600px; margin: 0; color: #d1d9e9; font-size: .98rem; line-height: 1.75; }

    .hero-avatar {
      display: block;
      width: 190px;
      height: 190px;
      justify-self: center;
      object-fit: cover;
      border: 1px solid rgba(255, 255, 255, .2);
      border-radius: 50%;
      box-shadow: 0 16px 40px rgba(0, 0, 0, .24);
    }

    .section-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 18px;
      margin: 38px 0 16px;
    }

    .section-heading h2 { margin: 0; font-size: 1.25rem; letter-spacing: -.035em; }
    .section-heading p { margin: 7px 0 0; color: var(--muted); font-size: .86rem; line-height: 1.5; }
    .refresh-note { color: var(--muted); font-size: .76rem; white-space: nowrap; }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }

    .metric, .card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }

    .metric { min-height: 142px; padding: 19px 20px; }
    .metric-label { color: var(--muted); font-size: .79rem; font-weight: 650; }
    .metric-value { display: flex; align-items: center; gap: 10px; margin-top: 22px; font-size: 1.4rem; font-weight: 760; letter-spacing: -.04em; }
    .metric-value.small { font-size: 1.15rem; }
    .metric-hint { margin-top: 7px; color: #8a95a6; font-size: .74rem; }
    .metric .status-dot { width: 9px; height: 9px; }

    .details {
      display: grid;
      grid-template-columns: 1.15fr .85fr;
      gap: 16px;
      margin-top: 16px;
    }

    .card { padding: 24px; }
    .card h2 { margin: 0 0 14px; font-size: 1rem; letter-spacing: -.02em; }
    .card p { margin: 0; color: var(--muted); font-size: .88rem; line-height: 1.75; }
    .detail-list { display: grid; gap: 17px; }
    .detail-item { display: grid; grid-template-columns: 112px 1fr; gap: 14px; font-size: .84rem; line-height: 1.55; }
    .detail-item strong { color: var(--ink); }
    .detail-item span { color: var(--muted); }
    .notice { margin-top: 18px !important; padding-top: 15px; border-top: 1px solid var(--line); font-size: .78rem !important; }

    .footer {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 23px;
      color: #8590a1;
      font-size: .74rem;
    }

    .value-yellow { color: #a76d0c; }
    .value-red { color: #c03c45; }
    .value-gray { color: #69758a; }
    .status-dot.offline { background: #c03c45; box-shadow: 0 0 0 4px rgba(192, 60, 69, .12); }

    @media (max-width: 760px) {
      body { padding: 22px 15px; }
      .hero { grid-template-columns: 1fr; min-height: 0; padding: 34px 28px; }
      .hero-avatar { display: none; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .details { grid-template-columns: 1fr; }
      .section-heading { align-items: start; flex-direction: column; }
    }

    @media (max-width: 440px) {
      .masthead { align-items: flex-start; }
      .public-label { padding: 8px 10px; font-size: .68rem; }
      .metrics { grid-template-columns: 1fr 1fr; gap: 9px; }
      .metric { min-height: 125px; padding: 15px 13px; }
      .metric-value { font-size: 1.17rem; }
      .metric-value.small { font-size: 1rem; }
      .card { padding: 20px; }
      .detail-item { grid-template-columns: 1fr; gap: 3px; }
      .footer { flex-direction: column; }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; }
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
          <div class="brand-caption">Central de status</div>
        </div>
      </div>
      <div class="public-label"><span class="pulse" aria-hidden="true"></span> Monitoramento público</div>
    </header>

    <main>
      <section class="hero" aria-labelledby="hero-title">
        <div class="hero-copy">
          <div class="eyebrow">Feito pelo salva · Bot para Discord</div>
          <h1 id="hero-title">HAKARI</h1>
          <p>Moderação, utilidades, automação e entretenimento em um só lugar. Criado em Python e conhecido pelo famoso comando <strong>/tomate</strong>.</p>
        </div>
        <img
          class="hero-avatar"
          src="https://i.postimg.cc/ncHYNPsF/4f1589b0a2549afad241ab8cc78b5828.jpg"
          alt="Avatar do bot HAKARI"
          width="190"
          height="190"
        />
      </section>

      <section aria-labelledby="status-heading">
        <div class="section-heading">
          <div>
            <h2 id="status-heading">Status dos serviços</h2>
            <p>Informações da hospedagem e da conexão do HAKARI.</p>
          </div>
          <span class="refresh-note" id="lastUpdated" aria-live="polite">Conectando ao monitor...</span>
        </div>

        <div class="metrics" aria-live="polite">
          <article class="metric">
            <div class="metric-label">Status do bot</div>
            <div class="metric-value"><span class="status-dot" aria-hidden="true"></span><span id="status">Online 24/7</span></div>
            <div class="metric-hint">UptimeRobot + Render</div>
          </article>
          <article class="metric">
            <div class="metric-label">Tempo ativo</div>
            <div class="metric-value small" id="uptime">Carregando...</div>
            <div class="metric-hint">Desde a inicialização do serviço</div>
          </article>
          <article class="metric">
            <div class="metric-label">Gateway do Discord</div>
            <div class="metric-value small" id="gateway">Carregando...</div>
            <div class="metric-hint">Estado da conexão com o Discord</div>
          </article>
          <article class="metric">
            <div class="metric-label">Latência (ping)</div>
            <div class="metric-value" id="ping">Carregando...</div>
            <div class="metric-hint">Conexão do bot com o gateway</div>
          </article>
        </div>
      </section>

      <section class="details" aria-label="Sobre o HAKARI e detalhes técnicos">
        <article class="card">
          <h2>Sobre o HAKARI</h2>
          <p>Mantido com atualizações constantes e otimizado para alta disponibilidade, o HAKARI foi projetado para facilitar a administração de servidores enquanto oferece uma experiência moderna e intuitiva para administradores e membros. Mais do que um simples bot, é o resultado de dedicação, criatividade e muitas horas de desenvolvimento contínuo.</p>
          <p class="notice">O propósito é entreter e criar funcionalidades diferentes de outros bots. Algumas informações de monitoramento podem falhar ou ficar indisponíveis temporariamente.</p>
        </article>

        <article class="card">
          <h2>Desenvolvimento & hospedagem</h2>
          <div class="detail-list">
            <div class="detail-item">
              <strong>Desenvolvedor</strong>
              <span>Salvador, desenvolvedor de bastante experiência, dedicado à criação de bots e de novas funcionalidades para o HAKARI.</span>
            </div>
            <div class="detail-item">
              <strong>Infraestrutura</strong>
              <span>Bot desenvolvido em Python e mantido online 24/7 com UptimeRobot + Render.</span>
            </div>
            <div class="detail-item">
              <strong>Porta do host</strong>
              <span id="port">Carregando...</span>
            </div>
          </div>
          <p class="notice">Esta página compartilha dados técnicos básicos sem expor tokens, chaves ou credenciais.</p>
        </article>
      </section>
    </main>

    <footer class="footer">
      <span>Página de status do HAKARI · Um bot feito pelo Salvador</span>
      <span>Atualização automática a cada 5 segundos</span>
    </footer>
  </div>

  <script>
    async function updateStatus() {
      const uptime = document.getElementById("uptime");
      const ping = document.getElementById("ping");
      const port = document.getElementById("port");
      const gateway = document.getElementById("gateway");
      const lastUpdated = document.getElementById("lastUpdated");
      const status = document.getElementById("status");
      const statusDot = document.querySelector(".status-dot");

      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`API respondeu com status ${response.status}`);
        }

        const data = await response.json();
        uptime.textContent = data.uptime ?? "Indisponível";
        ping.textContent = data.ping !== null && data.ping !== undefined
          ? `${data.ping} ms`
          : "Indisponível";
        port.textContent = data.port ?? "Indisponível";

        gateway.textContent = data.gateway_status ?? "Indisponível";
        gateway.className = "metric-value small";
        if (data.gateway_class === "yellow") gateway.classList.add("value-yellow");
        if (data.gateway_class === "red") gateway.classList.add("value-red");
        if (data.gateway_class === "gray") gateway.classList.add("value-gray");

        status.textContent = "Online 24/7";
        statusDot.classList.remove("offline");
        lastUpdated.textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
      } catch (error) {
        uptime.textContent = "Indisponível";
        ping.textContent = "Indisponível";
        port.textContent = "Indisponível";
        gateway.textContent = "Falha na conexão";
        gateway.className = "metric-value small value-red";
        status.textContent = "Monitor indisponível";
        statusDot.classList.add("offline");
        lastUpdated.textContent = "Não foi possível atualizar os dados";
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
