"""Mensageiro (Native Messaging) entre a extensão do Chrome e o programa
(Organized YouTube Music Downloads for iPod).

O Chrome abre este script a cada pedido e conversa por stdin/stdout
(4 bytes de tamanho + JSON). Se o programa estiver fechado, ele abre o programa
e espera ficar pronto antes de repassar o pedido."""
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from musicas.servidor import chamar  # noqa: E402


def ler() -> dict | None:
    cab = sys.stdin.buffer.read(4)
    if len(cab) < 4:
        return None
    n = struct.unpack("<I", cab)[0]
    return json.loads(sys.stdin.buffer.read(n).decode("utf-8"))


def escrever(obj: dict) -> None:
    dados = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(dados)))
    sys.stdout.buffer.write(dados)
    sys.stdout.buffer.flush()


def abrir_programa() -> None:
    # Abre pelo Explorer: assim o programa não fica "preso" ao Chrome
    # (se o Chrome fechar o mensageiro, o programa continua aberto).
    # Instalado: usa o atalho criado pelo instalador (Python próprio).
    # Sem instalador: abre o .pyw com o Python do PC.
    atalho = RAIZ / "Abrir.lnk"
    alvo = atalho if atalho.exists() else RAIZ / "ipod_musicas.pyw"
    subprocess.Popen(["explorer.exe", str(alvo)])


def main() -> None:
    msg = ler()
    if msg is None:
        return
    if chamar({"acao": "ping"}, timeout=2) is None:
        if msg.get("acao") == "ping" and not msg.get("abrir"):
            escrever({"ok": False, "fechado": True})
            return
        if msg.get("acao") == "verificar":
            # só consultar o que você já tem não precisa abrir o programa
            from musicas.config import DADOS
            from musicas.historico import Historico
            escrever({"ok": True, "status": Historico(DADOS / "historico.json").status(list(msg.get("ids", [])))})
            return
        abrir_programa()
        for _ in range(60):  # até 30 s
            time.sleep(0.5)
            if chamar({"acao": "ping"}, timeout=2):
                break
        else:
            escrever({"ok": False, "erro": "Não consegui abrir o Organized YouTube Music Downloads for iPod."})
            return
    resp = chamar(msg, timeout=20)
    escrever(resp or {"ok": False, "erro": "O programa não respondeu."})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        escrever({"ok": False, "erro": f"mensageiro: {e}"})
