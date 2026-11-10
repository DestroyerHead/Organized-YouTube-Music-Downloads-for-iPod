"""Monta o instalador do Organized YouTube Music Downloads for iPod.

Uso (na pasta do projeto, com o Python 3.13 64 bits):
    py instalador\\montar.py

O que faz:
  1. baixa o Python oficial "embutível" (mesma versão deste Python) e coloca o tkinter
     (a parte das janelas, que não vem nele) copiando deste Python;
  2. instala as bibliotecas (yt-dlp, mutagen, pywin32, winrt, Pillow, pip) dentro dele;
  3. copia o programa, a extensão do Chrome, o ffmpeg (versão LGPL) e o Deno;
  4. junta as licenças de tudo que vai junto;
  5. roda o Inno Setup → instalador\\saida\\…Setup-<versão>.exe
"""
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AQUI = RAIZ / "instalador"
CACHE = AQUI / "cache"
BUILD = AQUI / "build"
APP = BUILD / "app"
PY = APP / "python"

sys.path.insert(0, str(RAIZ))
from musicas.config import NOME, VERSAO  # noqa: E402

V = sys.version_info
PY_VER = f"{V.major}.{V.minor}.{V.micro}"
PY_TAG = f"python{V.major}{V.minor}"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VER}/python-{PY_VER}-embed-amd64.zip"
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-n8.1-latest-win64-lgpl-shared-8.1.zip")
PACOTES = [
    "pip", "yt-dlp[default]", "mutagen", "pywin32", "pillow",
    "winrt-runtime", "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections",
    "winrt-Windows.Media.Core", "winrt-Windows.Media.Playback", "winrt-Windows.Storage.Streams",
]
ARQUIVOS_DO_PROGRAMA = ["ipod_musicas.pyw", "README.md", "LICENSE", "musicas", "extensao",
                        "mensageiro/host.py", "mensageiro/host.bat", "mensageiro/instalar.py"]


def passo(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def baixar(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    destino = CACHE / url.rsplit("/", 1)[-1]
    if not destino.exists():
        print(f"    baixando {url}")
        tmp = destino.with_suffix(".parcial")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "montar-instalador"})) as r, \
                open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.rename(destino)
    else:
        print(f"    usando cópia já baixada: {destino.name}")
    return destino


def ignorar_lixo(_pasta, nomes):
    return [n for n in nomes if n == "__pycache__" or n.endswith(".pyc")]


def python_embutido():
    passo(f"Python {PY_VER} embutível")
    if V[:2] != (3, 13) or sys.maxsize < 2**32:
        sys.exit("Use o Python 3.13 de 64 bits pra montar (o tkinter é copiado dele).")
    with zipfile.ZipFile(baixar(EMBED_URL)) as z:
        z.extractall(PY)
    # liga o 'site' (pra achar as bibliotecas) e a pasta Lib (tkinter)
    (PY / f"{PY_TAG}._pth").write_text(
        f"{PY_TAG}.zip\n.\nLib\nLib\\site-packages\n..\nimport site\n", "utf-8")

    passo("tkinter (janelas) copiado deste Python")
    base = Path(sys.base_prefix)
    for dll in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "zlib1.dll"):  # o Tcl do 3.13 usa a zlib1
        shutil.copy2(base / "DLLs" / dll, PY / dll)
    shutil.copytree(base / "Lib" / "tkinter", PY / "Lib" / "tkinter", ignore=ignorar_lixo)
    shutil.copytree(base / "tcl", PY / "tcl",
                    ignore=shutil.ignore_patterns("*.lib", "*.sh", "nmake", "__pycache__"))


def bibliotecas():
    passo("Bibliotecas: " + ", ".join(PACOTES))
    destino = PY / "Lib" / "site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-warn-script-location", "--upgrade", "--target", str(destino), *PACOTES],
                   check=True)
    shutil.rmtree(destino / "bin", ignore_errors=True)
    for cache in destino.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def programa():
    passo("Programa e extensão do Chrome")
    for item in ARQUIVOS_DO_PROGRAMA:
        origem, alvo = RAIZ / item, APP / item
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if origem.is_dir():
            shutil.copytree(origem, alvo, ignore=ignorar_lixo)
        else:
            shutil.copy2(origem, alvo)
    icone()


def icone():
    from PIL import Image, ImageDraw
    s = 256
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((s * 0.12, 0, s * 0.88, s), radius=s * 0.14, fill=(250, 45, 72))
    d.rounded_rectangle((s * 0.22, s * 0.08, s * 0.78, s * 0.42), radius=s * 0.05, fill=(255, 255, 255))
    d.ellipse((s * 0.25, s * 0.5, s * 0.75, s * 0.95), fill=(255, 255, 255))
    d.ellipse((s * 0.41, s * 0.66, s * 0.59, s * 0.84), fill=(250, 45, 72))
    im.save(APP / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def ferramentas():
    passo("ffmpeg (LGPL) e Deno")
    pasta = APP / "ferramentas"
    pasta.mkdir(parents=True)
    licencas = APP / "licencas"
    licencas.mkdir(exist_ok=True)
    with zipfile.ZipFile(baixar(FFMPEG_URL)) as z:
        for nome in z.namelist():
            arquivo = nome.rsplit("/", 1)[-1]
            if "/bin/" in nome and arquivo.endswith((".exe", ".dll")) and arquivo != "ffplay.exe":
                (pasta / arquivo).write_bytes(z.read(nome))
            elif arquivo == "LICENSE.txt":
                (licencas / "ffmpeg-LICENSE.txt").write_bytes(z.read(nome))
    deno = shutil.which("deno") or next(
        (Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages").glob("DenoLand.Deno*/deno.exe"), None)
    if not deno:
        sys.exit("Deno não encontrado. Instale com: winget install DenoLand.Deno")
    shutil.copy2(deno, pasta / "deno.exe")


def licencas():
    passo("Licenças")
    pasta = APP / "licencas"
    pasta.mkdir(exist_ok=True)
    shutil.copy2(PY / "LICENSE.txt", pasta / "python-LICENSE.txt")
    for info in (PY / "Lib" / "site-packages").glob("*.dist-info"):
        pacote = info.name.split("-")[0]
        for lic in list(info.glob("LICEN[CS]E*")) + list(info.glob("COPYING*")) + list(info.glob("licenses/*")):
            if lic.is_file():
                shutil.copy2(lic, pasta / f"{pacote}-{lic.name}")
    (pasta / "LEIA.txt").write_text(
        f"{NOME} {VERSAO}\n"
        "Licença do programa: GPL-3.0 (arquivo LICENSE na pasta de instalação).\n\n"
        "Este programa inclui software de terceiros, cada um com a sua licença (arquivos nesta pasta):\n"
        "  - Python (PSF License)               https://www.python.org\n"
        "  - Tcl/Tk (BSD-style)                 https://www.tcl.tk\n"
        "  - yt-dlp (Unlicense)                 https://github.com/yt-dlp/yt-dlp\n"
        "  - Mutagen (GPL-2.0-or-later)         https://github.com/quodlibet/mutagen\n"
        "  - pywin32 (PSF)                      https://github.com/mhammond/pywin32\n"
        "  - Pillow (MIT-CMU)                   https://python-pillow.org\n"
        "  - PyWinRT (MIT)                      https://github.com/pywinrt/pywinrt\n"
        "  - FFmpeg, build LGPL (LGPL-2.1+)     https://ffmpeg.org  ·  build: https://github.com/BtbN/FFmpeg-Builds\n"
        "  - Deno (MIT)                         https://github.com/denoland/deno/blob/main/LICENSE.md\n"
        "O código-fonte de cada um está nos links acima.\n", "utf-8")


def instalador() -> Path:
    passo("Inno Setup")
    iscc = next((p for p in (Path(os.environ["LOCALAPPDATA"]) / "Programs/Inno Setup 6/ISCC.exe",
                             Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe")
                 if p.exists()), None)
    if not iscc:
        sys.exit("Inno Setup não encontrado. Instale com: winget install JRSoftware.InnoSetup")
    subprocess.run([str(iscc), "/Q", f"/DVersao={VERSAO}", f"/DFonte={APP}", str(AQUI / "setup.iss")], check=True)
    saida = AQUI / "saida" / f"Organized-YouTube-Music-Downloads-for-iPod-Setup-{VERSAO}.exe"
    return saida


def main():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    APP.mkdir(parents=True)
    python_embutido()
    bibliotecas()
    programa()
    ferramentas()
    licencas()
    exe = instalador()
    tamanho = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file()) / 2**20
    print(f"\nPronto: {exe}  ({exe.stat().st_size / 2**20:.0f} MB; instalado ocupa ~{tamanho:.0f} MB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
