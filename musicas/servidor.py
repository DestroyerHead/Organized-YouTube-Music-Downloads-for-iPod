"""Receptor local: a extensão do Chrome (via mensageiro) manda músicas pro programa aberto.

Só escuta em 127.0.0.1, exige um código secreto (gerado a cada abertura e guardado em
dados/servidor.json) e recusa qualquer pedido vindo de um navegador (cabeçalho Origin),
então nenhum site consegue falar com o programa."""
import json
import os
import secrets
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config

MAX_BYTES = 2_000_000


def _arquivo():
    return config.DADOS / "servidor.json"


class Servidor:
    def __init__(self, tratar):
        """tratar(dict) -> dict, chamado numa thread do servidor."""
        token = secrets.token_hex(16)

        class Pedido(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _responder(self, codigo: int, corpo: dict):
                dados = json.dumps(corpo, ensure_ascii=False).encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_POST(self):
                tamanho = int(self.headers.get("Content-Length") or 0)
                if (self.path != "/api" or self.headers.get("Origin")
                        or not secrets.compare_digest(self.headers.get("X-Token", ""), token)
                        or not 0 < tamanho <= MAX_BYTES):
                    return self._responder(403, {"ok": False})
                try:
                    msg = json.loads(self.rfile.read(tamanho))
                    resp = tratar(msg) if isinstance(msg, dict) else {"ok": False}
                except Exception as e:  # noqa: BLE001
                    resp = {"ok": False, "erro": str(e)}
                self._responder(200, resp)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Pedido)
        self.porta = self.httpd.server_address[1]
        config.DADOS.mkdir(exist_ok=True)
        _arquivo().write_text(json.dumps({"porta": self.porta, "token": token, "pid": os.getpid()}), "utf-8")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def fechar(self):
        self.httpd.shutdown()
        try:
            if json.loads(_arquivo().read_text("utf-8")).get("pid") == os.getpid():
                _arquivo().unlink()
        except (OSError, ValueError):
            pass


def chamar(msg: dict, timeout: float = 5) -> dict | None:
    """Manda um pedido pro programa aberto. None = programa fechado."""
    try:
        info = json.loads(_arquivo().read_text("utf-8"))
        req = urllib.request.Request(
            f"http://127.0.0.1:{info['porta']}/api", data=json.dumps(msg).encode(),
            headers={"X-Token": info["token"], "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return None
