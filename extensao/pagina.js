// Roda "dentro" da página do YouTube Music (mundo principal), onde dá pra ler os dados
// do player e da fila "A seguir", que não aparecem como links na página.
// Só responde a pedidos do conteudo.js (via window.postMessage).
(() => {
  if (window.__ipodPagina) return;
  window.__ipodPagina = true;

  const texto = (el, sel) => (el.querySelector(sel)?.textContent || "").trim();

  function atual() {
    const d = document.querySelector("#movie_player")?.getVideoData?.();
    return d && d.video_id ? { id: d.video_id, titulo: d.title || "", artista: d.author || "" } : null;
  }

  function fila() {
    const vistos = new Set();
    const itens = [];
    for (const el of document.querySelectorAll("ytmusic-player-queue-item")) {
      const d = el.data || el.__data?.data || el.polymerController?.data;
      const id = d?.videoId;
      if (!id || vistos.has(id)) continue;
      vistos.add(id);
      itens.push({ id, titulo: texto(el, ".song-title"), artista: texto(el, ".byline") });
    }
    return itens;
  }

  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || e.data.__ipod !== "pedido") return;
    let resp = null;
    try {
      if (e.data.tipo === "atual") resp = atual();
      else if (e.data.tipo === "fila") resp = fila();
    } catch (_) {
      resp = null;
    }
    window.postMessage({ __ipod: "resposta", id: e.data.id, resp }, "*");
  });
})();
