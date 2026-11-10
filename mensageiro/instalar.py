"""Registra o mensageiro no Chrome (só pro seu usuário do Windows, sem administrador).

Cria mensageiro/com.ipodmusicas.app.json e a chave de registro
HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.ipodmusicas.app
apontando pra ele. Rodar de novo não faz mal (só atualiza os caminhos)."""
import json
import sys
import winreg
from pathlib import Path

NOME = "com.ipodmusicas.app"
# ID fixo da extensão (vem da "key" do extensao/manifest.json)
ID_EXTENSAO = "hjkmnlbkhlpifkbiifdnkfjciodeomab"
NAVEGADORES = {
    "Chrome": r"Software\Google\Chrome\NativeMessagingHosts",
}


def main() -> int:
    pasta = Path(__file__).resolve().parent
    manifesto = pasta / f"{NOME}.json"
    manifesto.write_text(json.dumps({
        "name": NOME,
        "description": "Organized YouTube Music Downloads for iPod - recebe músicas da extensão do Chrome",
        "path": str(pasta / "host.bat"),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ID_EXTENSAO}/"],
    }, indent=2, ensure_ascii=False), "utf-8")

    for nav, base in NAVEGADORES.items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{base}\\{NOME}") as chave:
            winreg.SetValueEx(chave, "", 0, winreg.REG_SZ, str(manifesto))
        print(f"  ✓ Registrado no {nav}")
    print(f"\nPronto! Agora carregue a pasta '{pasta.parent / 'extensao'}' no Chrome")
    print("(chrome://extensions → Modo do desenvolvedor → Carregar sem compactação).")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
