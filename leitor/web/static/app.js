// Painel da portaria: busca o estado na API a cada 2 segundos e redesenha.
// Tudo que vem do usuário (placa, nome) entra com textContent, nunca como HTML.

const ATUALIZAR_MS = 1000;
const ALERTA_MS = 15000;
const NOMES_TIPO = { avulso: "Avulso", mensalista: "Mensalista", bloqueado: "Bloqueado" };
const NOMES_SITUACAO = { liberado: "Liberado", bloqueado: "Bloqueado", lotado: "Lotado", saida: "Saída" };

const $ = (id) => document.getElementById(id);

function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined) e.textContent = texto;
  return e;
}

function tempo(minutos) {
  const total = Math.round(minutos);
  const h = Math.floor(total / 60);
  const m = String(total % 60).padStart(2, "0");
  return `${h}h${m}`;
}

function horaDe(dataHora) {
  return dataHora.slice(11, 16); // "AAAA-MM-DD HH:MM:SS" -> "HH:MM"
}

async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.detail || `Erro ${resposta.status}`);
  return dados;
}

// ---------- abas ----------

document.querySelectorAll(".aba").forEach((botao) => {
  botao.addEventListener("click", () => {
    document.querySelectorAll(".aba").forEach((b) => b.classList.toggle("ativa", b === botao));
    document.querySelectorAll(".conteudo").forEach((s) => (s.hidden = s.id !== botao.dataset.aba));
    history.replaceState(null, "", `#${botao.dataset.aba}`); // o endereço lembra a aba (ex.: /#lotacao)
    if (botao.dataset.aba === "relatorio") carregarRelatorio();
    if (botao.dataset.aba === "cadastro") carregarVeiculos();
  });
});

// ---------- painel ----------

function desenharEstado(estado) {
  // O relógio vem do servidor: na demonstração ele corre mais rápido que o do computador.
  const [data, hora] = estado.agora.split(" ");
  $("relogio").textContent = `${data.split("-").reverse().join("/")} ${hora}`;
  $("livres").textContent = estado.livres;
  $("ocupadas").textContent = estado.ocupadas;
  $("faturamento").textContent = estado.faturamento_hoje;
  $("ocupacao").textContent = `${estado.ocupadas} de ${estado.vagas} vagas ocupadas`;

  const ocupacao = estado.vagas ? estado.ocupadas / estado.vagas : 0;
  $("barra-ocupacao").style.width = `${Math.min(ocupacao, 1) * 100}%`;
  const cartao = $("cartao-vagas");
  cartao.classList.toggle("cheio", estado.livres === 0);
  cartao.classList.toggle("quase", estado.livres > 0 && ocupacao >= 0.8);

  desenharFaseDemo(estado.demo);
  desenharCamera(estado.camera, estado.demo);
  desenharEventos(estado.eventos);
  desenharDentro(estado.dentro);
  desenharPatio(estado.patio);
  desenharAlerta(estado.eventos);
}

function desenharFaseDemo(demo) {
  const faixa = $("fase-demo");
  faixa.hidden = !demo;
  if (!demo) return;
  faixa.textContent = demo.mensagem;
  faixa.className = `fase-demo ${demo.fase}`;
}

const NOMES_FASE = { preparando: "preparando", entrada: "câmera da entrada", tempo: "pausa", saida: "câmera da saída", fim: "fim" };

function desenharCamera(camera, demo) {
  const status = $("status-camera");
  const video = $("video");
  $("sem-camera").hidden = camera.ativa;
  video.hidden = !camera.ativa;
  if (!camera.ativa) {
    status.textContent = "";
    status.className = "status";
    return;
  }
  if (!video.src) video.src = "/video";
  if (demo) {
    status.textContent = NOMES_FASE[demo.fase] || demo.fase;
    status.className = `status ${camera.conectada ? "on" : "neutro"}`;
    return;
  }
  status.textContent = camera.conectada ? "ao vivo" : "reconectando…";
  status.className = `status ${camera.conectada ? "on" : "off"}`;
}

// Placa em cada vaga no último desenho, para destacar quem acabou de chegar ou sair.
let patioAnterior = null;

function criarVaga(v) {
  const antes = patioAnterior?.[v.vaga];
  const caixa = el("div", "vaga");
  caixa.append(el("span", "numero-vaga", `VAGA ${String(v.vaga).padStart(2, "0")}`));
  if (v.placa) {
    caixa.classList.add(v.tipo === "mensalista" ? "mensalista" : "ocupada");
    caixa.append(el("span", "placa", v.placa), el("span", "info", `${tempo(v.minutos)} · ${v.valor_parcial}`));
    caixa.title = `${v.placa} (${NOMES_TIPO[v.tipo] || v.tipo}), entrou às ${horaDe(v.entrada)}`;
    if (patioAnterior && antes !== v.placa) caixa.classList.add("chegou");
  } else {
    caixa.append(el("span", "livre-texto", "Livre"));
    if (patioAnterior && antes) caixa.classList.add("saiu");
  }
  return caixa;
}

function desenharPatio(patio) {
  // O pátio aparece no Painel e na aba Pátio: desenha nos dois.
  for (const area of document.querySelectorAll("[data-patio]")) {
    area.replaceChildren(...patio.map(criarVaga));
  }
  patioAnterior = Object.fromEntries(patio.map((v) => [v.vaga, v.placa]));
}

function desenharEventos(eventos) {
  const lista = $("eventos");
  lista.replaceChildren();
  if (!eventos.length) {
    lista.append(el("li", "vazio", "Nenhum evento ainda."));
    return;
  }
  for (const ev of eventos) {
    // Mensalista liberado aparece em azul para diferenciar do avulso.
    const cor = ev.situacao === "liberado" && ev.tipo === "mensalista" ? "mensalista" : ev.situacao;
    const item = el("li", `evento ${cor}`);
    item.append(el("span", "hora", horaDe(ev.hora)), el("span", "placa", ev.placa), el("span", "msg", ev.mensagem));
    lista.append(item);
  }
}

function desenharDentro(dentro) {
  const corpo = $("dentro");
  corpo.replaceChildren();
  if (!dentro.length) {
    const linha = el("tr");
    const celula = el("td", "vazio", "Ninguém dentro.");
    celula.colSpan = 6;
    linha.append(celula);
    corpo.append(linha);
    return;
  }
  for (const a of dentro) {
    const linha = el("tr");
    const tipo = el("td");
    tipo.append(el("span", `selo ${a.tipo}`, NOMES_TIPO[a.tipo] || a.tipo));
    linha.append(
      el("td", "num", a.vaga ?? "–"),
      el("td", "placa", a.placa),
      tipo,
      el("td", "num", horaDe(a.entrada)),
      el("td", "num", tempo(a.minutos)),
      el("td", "num", a.valor_parcial),
    );
    corpo.append(linha);
  }
}

// Alertas já vistos. Os que existiam quando a página abriu não piscam de novo.
let alertasVistos = null;
let esconderAlerta = null;

function desenharAlerta(eventos) {
  const chave = (ev) => `${ev.hora}|${ev.placa}|${ev.situacao}`;
  const alertas = eventos.filter((ev) => ev.situacao === "bloqueado" || ev.situacao === "lotado");
  if (alertasVistos === null) {
    alertasVistos = new Set(alertas.map(chave));
    return;
  }
  const novo = alertas.find((ev) => !alertasVistos.has(chave(ev)));
  if (!novo) return;
  alertas.forEach((ev) => alertasVistos.add(chave(ev)));

  // Mostra o alerta novo por 15 segundos.
  const alerta = $("alerta");
  alerta.textContent = novo.mensagem;
  alerta.className = `alerta ${novo.situacao}`;
  alerta.hidden = false;
  navigator.vibrate?.(300); // celular da portaria vibra
  clearTimeout(esconderAlerta);
  esconderAlerta = setTimeout(() => (alerta.hidden = true), ALERTA_MS);
}

async function atualizar() {
  try {
    desenharEstado(await api("/api/estado"));
  } catch (erro) {
    console.error(erro);
  }
}

// ---------- entrada e saída manual ----------

let acaoManual = "entrada";
document.querySelectorAll("#form-manual button").forEach((b) =>
  b.addEventListener("click", () => (acaoManual = b.dataset.acao)),
);

$("form-manual").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const resposta = $("resposta-manual");
  const placa = $("placa-manual").value.trim();
  try {
    const dados = await api(`/api/${acaoManual}`, { method: "POST", body: JSON.stringify({ placa }) });
    resposta.textContent = dados.mensagem;
    resposta.className = "resposta";
    $("placa-manual").value = "";
    atualizar();
  } catch (erro) {
    resposta.textContent = erro.message;
    resposta.className = "resposta erro";
  }
});

// ---------- relatório ----------

const hoje = new Date().toLocaleDateString("sv-SE"); // AAAA-MM-DD no fuso local
$("rel-de").value = hoje;
$("rel-ate").value = hoje;

$("form-relatorio").addEventListener("submit", (evento) => {
  evento.preventDefault();
  carregarRelatorio();
});

async function carregarRelatorio() {
  const de = $("rel-de").value;
  const ate = $("rel-ate").value;
  const dados = await api(`/api/relatorio?de=${de}&ate=${ate}`);

  const porHora = dados.por_hora;
  const totais = Object.values(porHora);
  const maior = Math.max(0, ...totais);
  const horaPico = Object.keys(porHora).find((h) => porHora[h] === maior);
  $("rel-faturamento").textContent = dados.faturamento;
  $("rel-entradas").textContent = totais.reduce((a, b) => a + b, 0);
  $("rel-pico").textContent = maior ? `${String(horaPico).padStart(2, "0")}h` : "–";

  const grafico = $("grafico-horas");
  grafico.replaceChildren();
  for (let h = 0; h < 24; h++) {
    const total = porHora[h] || 0;
    const coluna = el("div", "coluna-hora");
    coluna.title = `${h}h: ${total} entrada(s)`;
    const barra = el("div", `barra-hora${total && total === maior ? " pico" : ""}`);
    barra.style.height = maior ? `${(total / maior) * 100}%` : "0";
    coluna.append(el("span", "valor", total || ""), barra, el("span", "hora", String(h)));
    grafico.append(coluna);
  }

  const corpo = $("frequentes");
  corpo.replaceChildren();
  for (const f of dados.frequentes) {
    const linha = el("tr");
    const tipo = el("td");
    tipo.append(el("span", `selo ${f.tipo}`, NOMES_TIPO[f.tipo] || f.tipo));
    linha.append(el("td", "placa", f.placa), tipo, el("td", "num", f.total));
    corpo.append(linha);
  }
}

// ---------- cadastro ----------

async function carregarVeiculos() {
  const corpo = $("veiculos");
  corpo.replaceChildren();
  for (const v of await api("/api/veiculos")) {
    const linha = el("tr");
    const tipo = el("td");
    tipo.append(el("span", `selo ${v.tipo}`, NOMES_TIPO[v.tipo]));
    const remover = el("button", "remover", "Remover");
    remover.addEventListener("click", async () => {
      if (!confirm(`Remover o cadastro de ${v.placa}?`)) return;
      await api(`/api/veiculos/${v.placa}`, { method: "DELETE" });
      carregarVeiculos();
    });
    const acoes = el("td");
    acoes.append(remover);
    linha.append(el("td", "placa", v.placa), el("td", "", v.proprietario), tipo, el("td", "", v.observacao || ""), acoes);
    corpo.append(linha);
  }
}

$("form-cadastro").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const resposta = $("resposta-cadastro");
  const corpo = {
    placa: $("cad-placa").value.trim(),
    proprietario: $("cad-proprietario").value.trim(),
    tipo: $("cad-tipo").value,
    observacao: $("cad-observacao").value.trim(),
  };
  try {
    const dados = await api("/api/veiculos", { method: "POST", body: JSON.stringify(corpo) });
    resposta.textContent = dados.mensagem;
    resposta.className = "resposta";
    $("form-cadastro").reset();
    carregarVeiculos();
  } catch (erro) {
    resposta.textContent = erro.message;
    resposta.className = "resposta erro";
  }
});

// ---------- atualização ----------

document.querySelector(`.aba[data-aba="${location.hash.slice(1)}"]`)?.click();
atualizar();
setInterval(atualizar, ATUALIZAR_MS);
