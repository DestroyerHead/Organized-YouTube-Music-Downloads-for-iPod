// Ponte entre a página (conteudo.js) e o programa no PC (mensageiro via Native Messaging).
const HOST = "com.ipodmusicas.app";

chrome.runtime.onMessage.addListener((pedido, _remetente, responder) => {
  if (!pedido || pedido.tipo !== "nativo") return false;
  chrome.runtime.sendNativeMessage(HOST, pedido.msg, (resp) => {
    if (chrome.runtime.lastError) {
      responder({ ok: false, erro: chrome.runtime.lastError.message });
    } else {
      responder(resp || { ok: false, erro: "O mensageiro não respondeu." });
    }
  });
  return true; // resposta assíncrona
});
