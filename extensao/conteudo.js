// Botões "→ iPod" no YouTube e no YouTube Music, leitura das listas e janela de revisão.
(() => {
  if (window.__ipodMusicas) return;
  window.__ipodMusicas = true;

  const NOME = "Organized YouTube Music Downloads for iPod";
  const YTM = location.hostname === "music.youtube.com";
  const LIMITE = 500;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const visivel = (el) => !!el && el.getClientRects().length > 0;

  // =========================================================== comunicação
  function nativo(msg) {
    return new Promise((res) => {
      try {
        chrome.runtime.sendMessage({ tipo: "nativo", msg }, (r) => {
          if (chrome.runtime.lastError) res({ ok: false, erro: chrome.runtime.lastError.message });
          else res(r || { ok: false, erro: "sem resposta" });
        });
      } catch (_) {
        res({ ok: false, erro: "A extensão foi atualizada. Recarregue a página (F5)." });
      }
    });
  }

  function explicarErro(r) {
    const e = (r && r.erro) || "";
    if (/not found/i.test(e)) return `O ${NOME} não está registrado no Chrome. Rode o instalar_extensao.bat (uma vez só) e reinicie o Chrome.`;
    if (/forbidden/i.test(e)) return `O Chrome bloqueou a conexão com o ${NOME}. Rode de novo o instalar_extensao.bat.`;
    if (/exited|disconnected/i.test(e)) return "O mensageiro fechou com erro. Confira se o Python está instalado.";
    return e || `Não consegui falar com o ${NOME}.`;
  }

  // pede dados ao pagina.js (só no YouTube Music)
  function pedirPagina(tipo) {
    return new Promise((res) => {
      const id = Math.random().toString(36).slice(2);
      const ouvir = (e) => {
        if (e.source === window && e.data && e.data.__ipod === "resposta" && e.data.id === id) {
          window.removeEventListener("message", ouvir);
          res(e.data.resp);
        }
      };
      window.addEventListener("message", ouvir);
      window.postMessage({ __ipod: "pedido", id, tipo }, "*");
      setTimeout(() => { window.removeEventListener("message", ouvir); res(null); }, 2000);
    });
  }

  // ===================================================================== UI
  const CSS_UI = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: Roboto, "Segoe UI", Arial, sans-serif; }
    .avisos { position: fixed; left: 24px; bottom: 96px; display: flex; flex-direction: column; gap: 8px; z-index: 2147483647; }
    .aviso { background: #212121; color: #fff; padding: 12px 16px; border-radius: 8px; font-size: 14px;
             box-shadow: 0 4px 16px rgba(0,0,0,.4); max-width: 420px; line-height: 1.4; border-left: 4px solid #888; }
    .aviso.ok { border-left-color: #2ecc71; } .aviso.erro { border-left-color: #fa2d48; } .aviso.info { border-left-color: #3ea6ff; }
    .fundo { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center;
             justify-content: center; z-index: 2147483647; }
    .caixa { background: #212121; color: #f1f1f1; width: min(720px, calc(100vw - 32px)); max-height: calc(100vh - 64px);
             border-radius: 12px; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,.5); }
    .cab { padding: 18px 20px 10px; }
    h2 { margin: 0; font-size: 18px; font-weight: 600; }
    .sub { color: #aaa; font-size: 13px; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .resumo { color: #ddd; font-size: 13px; margin-top: 10px; }
    .barra { display: flex; gap: 8px; padding: 0 20px 10px; flex-wrap: wrap; }
    .lista { overflow-y: auto; border-top: 1px solid #333; border-bottom: 1px solid #333; flex: 1; min-height: 120px; }
    .linha { display: flex; align-items: center; gap: 12px; padding: 7px 20px; cursor: pointer; }
    .linha:hover { background: #2c2c2c; }
    .linha.fraca .textos { opacity: .55; }
    .linha input { width: 17px; height: 17px; accent-color: #fa2d48; flex: none; cursor: pointer; }
    .num { color: #888; font-size: 12px; width: 28px; text-align: right; flex: none; }
    .textos { flex: 1; min-width: 0; }
    .t { font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .a { font-size: 12px; color: #aaa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .selo { font-size: 11px; padding: 3px 8px; border-radius: 10px; background: #3a3a3a; color: #ccc; flex: none; }
    .selo.apagada { background: #4a2228; color: #ff9aa8; }
    .rodape { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; }
    button { font-size: 14px; border-radius: 18px; padding: 8px 16px; border: 0; cursor: pointer; background: #3a3a3a; color: #fff; }
    button:hover { background: #4a4a4a; }
    button.principal { background: #fa2d48; font-weight: 600; }
    button.principal:hover { background: #e0213b; }
    button.principal:disabled { background: #5a5a5a; cursor: default; }
    button.peq { font-size: 12px; padding: 6px 12px; }
    .menu { position: fixed; background: #282828; border-radius: 8px; padding: 6px 0; min-width: 220px;
            box-shadow: 0 6px 24px rgba(0,0,0,.5); z-index: 2147483647; }
    .menu div { padding: 10px 16px; color: #f1f1f1; font-size: 14px; cursor: pointer; }
    .menu div:hover { background: #3a3a3a; }
    .menu div.off { color: #777; cursor: default; background: none; }
    .carregando { background: #212121; color: #f1f1f1; padding: 22px 26px; border-radius: 12px; min-width: 320px; text-align: center; }
    .carregando .n { font-size: 30px; font-weight: 600; margin: 10px 0 16px; }
  `;

  let raiz = null;
  function ui() {
    if (raiz && raiz.host.isConnected) return raiz;
    const host = document.createElement("div");
    host.id = "ipod-musicas-ui";
    document.documentElement.appendChild(host);
    raiz = host.attachShadow({ mode: "open" });
    const st = document.createElement("style");
    st.textContent = CSS_UI;
    raiz.appendChild(st);
    return raiz;
  }

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto != null) e.textContent = texto;
    return e;
  }

  function aviso(texto, tipo = "info", ms = 6000) {
    const r = ui();
    let pilha = r.querySelector(".avisos");
    if (!pilha) { pilha = el("div", "avisos"); r.appendChild(pilha); }
    const a = el("div", "aviso " + tipo, texto);
    pilha.appendChild(a);
    if (ms) setTimeout(() => a.remove(), ms);
    return a;
  }

  function menu(botao, opcoes) {
    const r = ui();
    r.querySelector(".menu")?.remove();
    const m = el("div", "menu");
    for (const o of opcoes) {
      const item = el("div", o.desativado ? "off" : "", o.texto);
      if (!o.desativado) item.addEventListener("click", () => { fechar(); o.acao(); });
      m.appendChild(item);
    }
    r.appendChild(m);
    const b = botao.getBoundingClientRect();
    const altura = m.offsetHeight, largura = m.offsetWidth;
    const embaixo = b.bottom + altura + 8 < innerHeight;
    m.style.top = (embaixo ? b.bottom + 6 : b.top - altura - 6) + "px";
    m.style.left = Math.max(8, Math.min(b.left, innerWidth - largura - 8)) + "px";
    const fora = (e) => { if (!e.composedPath().includes(m) && e.target !== botao) fechar(); };
    function fechar() { m.remove(); document.removeEventListener("mousedown", fora, true); }
    setTimeout(() => document.addEventListener("mousedown", fora, true), 0);
  }

  // janela "carregando… N" enquanto rola a página
  function telaCarregando(origem) {
    const r = ui();
    const fundo = el("div", "fundo");
    const c = el("div", "carregando");
    c.append(el("div", "sub", origem), el("div", "", "Carregando as músicas da lista…"));
    const n = el("div", "n", "0");
    const parar = el("button", "", "Parar e usar as carregadas");
    c.append(n, parar);
    fundo.appendChild(c);
    r.appendChild(fundo);
    const estado = { parado: false, mostrar: (x) => { n.textContent = String(x); }, fechar: () => fundo.remove() };
    parar.addEventListener("click", () => { estado.parado = true; });
    return estado;
  }

  // rola até não aparecer mais nada novo (ou até o limite)
  async function carregarTudo(coletar, origem) {
    const y0 = window.scrollY;
    const tela = telaCarregando(origem);
    let itens = coletar(), ultimo = itens.length, iguais = 0;
    tela.mostrar(itens.length);
    while (!tela.parado && iguais < 3 && itens.length < LIMITE) {
      const linhas = coletar.ultimaLinha?.();
      if (linhas) linhas.scrollIntoView({ block: "center" });
      else window.scrollTo(0, document.documentElement.scrollHeight);
      await sleep(1300);
      itens = coletar();
      tela.mostrar(itens.length);
      if (itens.length === ultimo) iguais++;
      else { iguais = 0; ultimo = itens.length; }
    }
    tela.fechar();
    window.scrollTo(0, y0);
    return itens.slice(0, LIMITE);
  }

  // janela de revisão com caixinhas; devolve as escolhidas (ou null)
  function revisar(itens, origem) {
    const r = ui();
    const fundo = el("div", "fundo");
    const caixa = el("div", "caixa");
    const cab = el("div", "cab");
    const resumo = el("div", "resumo", `${itens.length} músicas · verificando o que você já tem…`);
    cab.append(el("h2", "", `Enviar pro ${NOME}`), el("div", "sub", origem), resumo);
    const barra = el("div", "barra");
    const bTodas = el("button", "peq", "Marcar todas");
    const bNenhuma = el("button", "peq", "Desmarcar todas");
    const bNovas = el("button", "peq", "Só as novas");
    barra.append(bTodas, bNenhuma, bNovas);
    const lista = el("div", "lista");
    const caixas = [], selos = [];
    itens.forEach((it, i) => {
      const linha = el("label", "linha");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = true;
      const textos = el("div", "textos");
      textos.append(el("div", "t", it.titulo || it.id), el("div", "a", it.artista || ""));
      const selo = el("span", "selo");
      selo.style.display = "none";
      linha.append(cb, el("span", "num", String(i + 1)), textos, selo);
      lista.appendChild(linha);
      caixas.push(cb);
      selos.push(selo);
      cb.addEventListener("change", contar);
    });
    const rodape = el("div", "rodape");
    const bCancelar = el("button", "", "Cancelar");
    const bEnviar = el("button", "principal", "Enviar");
    rodape.append(bCancelar, bEnviar);
    caixa.append(cab, barra, lista, rodape);
    fundo.appendChild(caixa);
    r.appendChild(fundo);

    let status = {};
    function contar() {
      const n = caixas.filter((c) => c.checked).length;
      bEnviar.textContent = `Enviar (${n})`;
      bEnviar.disabled = n === 0;
      caixas.forEach((c) => c.closest(".linha").classList.toggle("fraca", !c.checked));
    }
    contar();
    bTodas.onclick = () => { caixas.forEach((c) => (c.checked = true)); contar(); };
    bNenhuma.onclick = () => { caixas.forEach((c) => (c.checked = false)); contar(); };
    bNovas.onclick = () => { itens.forEach((it, i) => (caixas[i].checked = !status[it.id])); contar(); };

    nativo({ acao: "verificar", ids: itens.map((i) => i.id) }).then((resp) => {
      if (!resp || !resp.ok) {
        resumo.textContent = `${itens.length} músicas · não consegui verificar: ${explicarErro(resp)}`;
        return;
      }
      status = resp.status || {};
      let tenho = 0, apagadas = 0;
      itens.forEach((it, i) => {
        const s = status[it.id];
        if (!s) return;
        selos[i].style.display = "";
        if (s === "apagada") { apagadas++; selos[i].textContent = "você apagou"; selos[i].classList.add("apagada"); }
        else { tenho++; selos[i].textContent = "já tenho"; }
        caixas[i].checked = false;
      });
      const novas = itens.length - tenho - apagadas;
      resumo.textContent = `${itens.length} músicas · ${novas} novas` +
        (tenho ? ` · ${tenho} você já tem` : "") + (apagadas ? ` · ${apagadas} você apagou` : "");
      contar();
    });

    return new Promise((res) => {
      const fim = (valor) => { document.removeEventListener("keydown", esc, true); fundo.remove(); res(valor); };
      const esc = (e) => { if (e.key === "Escape") fim(null); };
      document.addEventListener("keydown", esc, true);
      bCancelar.onclick = () => fim(null);
      bEnviar.onclick = () => fim(itens.filter((_, i) => caixas[i].checked));
    });
  }

  async function enviar(itens, origem) {
    if (!itens || !itens.length) { aviso("Nenhuma música pra enviar.", "erro"); return; }
    const espera = aviso(`Enviando ${itens.length} música(s)… (se o programa estiver fechado, ele vai abrir)`, "info", 0);
    const r = await nativo({ acao: "enviar", itens, origem });
    espera.remove();
    if (r && r.ok) aviso(`✓ ${r.n} música(s) enviada(s) pro ${NOME}`, "ok");
    else aviso(explicarErro(r), "erro", 12000);
  }

  async function enviarLista(itens, origem) {
    if (!itens || !itens.length) { aviso("Não achei músicas nesta página.", "erro"); return; }
    const escolhidas = await revisar(itens, origem);
    if (escolhidas) await enviar(escolhidas, origem);
  }

  // ======================================================== leitura de listas
  const idDe = (href) => {
    try {
      const v = new URL(href, location.href).searchParams.get("v");
      return v && /^[\w-]{11}$/.test(v) ? v : null;
    } catch (_) { return null; }
  };
  const listaDe = (href) => {
    try { return new URL(href, location.href).searchParams.get("list"); } catch (_) { return null; }
  };
  const txt = (raizEl, sel) => (raizEl?.querySelector(sel)?.textContent || "").trim().replace(/\s+/g, " ");

  // monta um coletor: lê as linhas (seletor) dentro da área visível; reserva: links com list=
  function coletor(area, seletorLinha, extrair, listId) {
    let ultima = null;
    const f = () => {
      const raizEl = area() || document;
      const mapa = new Map();
      const linhas = [...raizEl.querySelectorAll(seletorLinha)];
      for (const linha of linhas) {
        const it = extrair(linha);
        if (it && it.id && !mapa.has(it.id)) mapa.set(it.id, it);
      }
      // o próximo bloco só carrega quando o marcador "carregar mais" aparece na tela
      const continua = raizEl.querySelector("ytmusic-continuation-item-renderer, ytd-continuation-item-renderer");
      ultima = continua || linhas[linhas.length - 1] || null;
      if (!mapa.size && listId) { // layout diferente: usa qualquer link da lista
        const links = [...raizEl.querySelectorAll('a[href*="watch?v="]')].filter((a) => listaDe(a.href) === listId);
        for (const a of links) {
          const id = idDe(a.href);
          const titulo = (a.getAttribute("title") || a.textContent || "").trim().replace(/\s+/g, " ");
          if (id && !mapa.has(id)) mapa.set(id, { id, titulo, artista: "" });
        }
        ultima = links[links.length - 1] || null;
      }
      return [...mapa.values()];
    };
    f.ultimaLinha = () => ultima;
    return f;
  }

  // ---- YouTube Music
  function tituloPaginaYTM() {
    const h = [...document.querySelectorAll("ytmusic-responsive-header-renderer, ytmusic-detail-header-renderer, ytmusic-immersive-header-renderer")].find(visivel);
    return txt(h, "h1, h2, .title") || document.title.replace(/ - YouTube Music$/, "");
  }

  async function mandarListaYTM() {
    const origem = tituloPaginaYTM() || "YouTube Music";
    const listId = new URLSearchParams(location.search).get("list");
    // Só a lista principal da playlist/álbum. Embaixo das suas playlists o YouTube Music
    // mostra "Sugestões" (músicas que NÃO estão na playlist), que ficam em outra seção.
    const area = () => {
      const pag = [...document.querySelectorAll("ytmusic-browse-response")].find(visivel);
      if (!pag) return null;
      return pag.querySelector("ytmusic-playlist-shelf-renderer") || pag.querySelector("ytmusic-shelf-renderer") || pag;
    };
    const ler = (linha, exigirLista) => {
      const a = linha.querySelector('a[href*="watch?v="]');
      const id = a && idDe(a.href);
      if (!id) return null;
      // o link de cada música da playlist leva "list=<id da playlist>"; o das sugestões não
      if (exigirLista && listaDe(a.href) !== listId) return null;
      return { id, titulo: txt(linha, ".title") || a.textContent.trim(),
               artista: txt(linha, ".secondary-flex-columns yt-formatted-string") };
    };
    const comFiltro = coletor(area, "ytmusic-responsive-list-item-renderer", (l) => ler(l, !!listId), null);
    const semFiltro = coletor(area, "ytmusic-responsive-list-item-renderer", (l) => ler(l, false), null);
    // se nenhum link trouxer o list= (layout diferente), usa só a restrição da seção principal
    const f = () => { const itens = comFiltro(); return itens.length || !listId ? itens : semFiltro(); };
    f.ultimaLinha = () => comFiltro.ultimaLinha();
    await enviarLista(await carregarTudo(f, origem), origem);
  }

  async function mandarAtualYTM() {
    let d = await pedirPagina("atual");
    if (!d) {
      const id = idDe(location.href);
      if (id) d = { id, titulo: txt(document, "ytmusic-player-bar .title"), artista: txt(document, "ytmusic-player-bar .byline").split("•")[0].trim() };
    }
    if (!d) { aviso("Não achei a música que está tocando.", "erro"); return; }
    await enviar([d], "YouTube Music");
  }

  async function mandarFilaYTM() {
    const itens = await pedirPagina("fila");
    if (!itens || !itens.length) { aviso("A fila \"A seguir\" está vazia (ou não carregou). Abra o player e tente de novo.", "erro"); return; }
    await enviarLista(itens, "Fila do YouTube Music (A seguir)");
  }

  function menuPlayerYTM(botao) {
    menu(botao, [
      { texto: "♪  Esta música", acao: mandarAtualYTM },
      { texto: "☰  Fila inteira (A seguir)", acao: mandarFilaYTM },
    ]);
  }

  // ---- YouTube
  function atualYT() {
    const id = idDe(location.href);
    if (!id) return null;
    const meta = [...document.querySelectorAll("ytd-watch-metadata")].find(visivel);
    const titulo = txt(meta, "h1") || document.title.replace(/ - YouTube$/, "").replace(/^\(\d+\)\s*/, "");
    const artista = txt(meta, "ytd-channel-name a") || txt(document, "#owner ytd-channel-name a");
    return { id, titulo, artista };
  }

  async function mandarAtualYT() {
    const d = atualYT();
    if (!d) { aviso("Não achei o vídeo desta página.", "erro"); return; }
    await enviar([d], "YouTube");
  }

  async function mandarPainelYT() {
    const listId = listaDe(location.href);
    const painel = () => [...document.querySelectorAll("ytd-playlist-panel-renderer")].find(visivel);
    const origem = txt(painel(), "#header-description h3, .title") || "Lista do YouTube";
    const f = coletor(painel, "ytd-playlist-panel-video-renderer", (linha) => {
      const a = linha.querySelector("a#wc-endpoint, a[href*='watch?v=']");
      const id = a && idDe(a.href);
      return id ? { id, titulo: txt(linha, "#video-title"), artista: txt(linha, "#byline") } : null;
    }, listId);
    await enviarLista(await carregarTudo(f, origem), origem);
  }

  async function mandarListaYT() {
    const listId = listaDe(location.href);
    const origem = document.title.replace(/ - YouTube$/, "").replace(/^\(\d+\)\s*/, "") || "Playlist do YouTube";
    const f = coletor(
      () => [...document.querySelectorAll("ytd-browse")].find(visivel),
      "ytd-playlist-video-renderer",
      (linha) => {
        const a = linha.querySelector("a#video-title, a[href*='watch?v=']");
        const id = a && idDe(a.href);
        if (listId && listaDe(a.href) && listaDe(a.href) !== listId) return null; // recomendados
        return id ? { id, titulo: (a.getAttribute("title") || a.textContent).trim(),
                      artista: txt(linha, "ytd-channel-name a, #channel-name a") } : null;
      }, listId);
    await enviarLista(await carregarTudo(f, origem), origem);
  }

  function menuVideoYT(botao) {
    const temLista = !!listaDe(location.href);
    menu(botao, [
      { texto: "♪  Só esta música", acao: mandarAtualYT },
      { texto: temLista ? "☰  A lista inteira" : "☰  A lista inteira (este vídeo não está numa lista)",
        acao: mandarPainelYT, desativado: !temLista },
    ]);
  }

  // ========================================================= colocar botões
  function botao(id, classe, acao) {
    const b = document.createElement("button");
    b.id = id;
    b.type = "button";
    b.className = "ipod-botao " + classe;
    b.textContent = "→ iPod";
    b.title = `Mandar pro ${NOME}`;
    b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); acao(b); });
    return b;
  }

  const pagina = { url: "", desde: 0 };

  function garantirBotoes() {
    if (location.href !== pagina.url) { pagina.url = location.href; pagina.desde = Date.now(); }
    const caminho = location.pathname;
    const ehLista = YTM ? (caminho === "/playlist" || caminho.startsWith("/browse/")) : caminho === "/playlist";
    const ehVideo = !YTM && caminho === "/watch";
    let colocado = false;

    if (YTM) {
      const barra = document.querySelector("ytmusic-player-bar .right-controls-buttons");
      if (barra && !barra.querySelector("#ipod-btn-player")) barra.prepend(botao("ipod-btn-player", "ipod-botao-player", menuPlayerYTM));
      if (ehLista) {
        const acoes = [...document.querySelectorAll("ytmusic-responsive-header-renderer #action-buttons, ytmusic-detail-header-renderer .action-buttons")].find(visivel);
        if (acoes) {
          if (!acoes.querySelector("#ipod-btn-lista")) acoes.append(botao("ipod-btn-lista", "", () => mandarListaYTM()));
          colocado = true;
        }
      }
    } else if (ehVideo) {
      const acoes = [...document.querySelectorAll("ytd-watch-metadata #top-level-buttons-computed")].find(visivel);
      const menuR = acoes?.closest("ytd-menu-renderer");
      if (menuR && menuR.parentElement) {
        const atual = document.getElementById("ipod-btn-video");
        if (!atual || !visivel(atual)) {
          atual?.remove();
          menuR.parentElement.insertBefore(botao("ipod-btn-video", "", menuVideoYT), menuR);
        }
        colocado = true;
      }
    } else if (ehLista) {
      const acoes = [...document.querySelectorAll(
        "yt-page-header-renderer yt-flexible-actions-view-model, ytd-playlist-header-renderer #top-level-buttons-computed, ytd-playlist-header-renderer .metadata-action-bar"
      )].find(visivel);
      if (acoes) {
        if (!acoes.querySelector("#ipod-btn-lista")) acoes.append(botao("ipod-btn-lista", "", () => mandarListaYT()));
        colocado = true;
      }
    }

    // plano B: não achou onde colocar → botão flutuante no canto
    const precisa = (ehLista || ehVideo) && !colocado && Date.now() - pagina.desde > 4000;
    const flutuante = document.getElementById("ipod-btn-flutuante");
    if (precisa && !flutuante) {
      document.body.appendChild(botao("ipod-btn-flutuante", "ipod-botao-flutuante", (b) => {
        if (ehVideo) menuVideoYT(b);
        else if (YTM) mandarListaYTM();
        else mandarListaYT();
      }));
    } else if (!precisa && flutuante) {
      flutuante.remove();
    }
  }

  setInterval(garantirBotoes, 1000);
  garantirBotoes();
})();
