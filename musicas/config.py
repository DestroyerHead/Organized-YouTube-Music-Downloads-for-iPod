"""Configurações do programa e localização das ferramentas (ffmpeg, deno)."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

NOME = "Organized YouTube Music Downloads for iPod"
VERSAO = "1.0.0"
RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
# Instalado pelo Setup: tem Python próprio e as ferramentas na pasta do programa
PYTHON_PROPRIO = RAIZ / "python" / "python.exe"
FERRAMENTAS = RAIZ / "ferramentas"
INSTALADO = PYTHON_PROPRIO.exists()

PADRAO = {
    # Pasta onde as músicas ficam antes de irem pro iTunes.
    # Se o iTunes estiver configurado pra copiar os arquivos pra pasta dele,
    # o programa apaga a cópia daqui depois de adicionar.
    "pasta_musicas": str(Path.home() / "Music" / "Musicas iPod"),
    # Playlist do iTunes onde as músicas novas entram ("" = só biblioteca).
    "playlist_itunes": "Baixadas do YouTube",
    # Loja do iTunes usada na busca (BR dá gêneros como Sertanejo, Funk, MPB).
    "pais_loja": "BR",
    # Máximo de músicas lidas de uma playlist/mix.
    "max_playlist": 500,
    # Quantas músicas baixam ao mesmo tempo (1 a 8).
    "downloads_simultaneos": 3,
    # Pausa (segundos) de cada download depois de terminar uma música, pra não irritar o YouTube.
    "pausa_min": 2,
    "pausa_max": 4,
    # Abaixo dessa nota (0 a 1) o resultado do iTunes não é usado automaticamente
    # e a música fica marcada como "revisar".
    "confianca_minima": 0.72,
    # Volume do player da aba Baixadas (0 a 1).
    "volume": 0.8,
}


def carregar() -> dict:
    DADOS.mkdir(exist_ok=True)
    arq = DADOS / "config.json"
    cfg = dict(PADRAO)
    if arq.exists():
        try:
            cfg.update(json.loads(arq.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    if cfg.get("versao_config", 1) < 2:
        # v2: downloads simultâneos → pausa menor (a antiga era 4 a 9 s com 1 por vez)
        if (cfg.get("pausa_min"), cfg.get("pausa_max")) == (4, 9):
            cfg["pausa_min"], cfg["pausa_max"] = 2, 4
        cfg["versao_config"] = 2
    salvar(cfg)
    return cfg


def salvar(cfg: dict) -> None:
    DADOS.mkdir(exist_ok=True)
    (DADOS / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


def preparar_ferramentas() -> tuple[str | None, str | None]:
    """Coloca ffmpeg e deno no PATH deste processo. Prioridade: os que vêm com o
    instalador (pasta 'ferramentas'); senão, os do winget (o PATH do winget só
    atualiza depois de reiniciar o Windows/terminal). Retorna os caminhos."""
    pacotes = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    extra = []
    if (FERRAMENTAS / "ffmpeg.exe").exists() or (FERRAMENTAS / "deno.exe").exists():
        os.environ["PATH"] = os.pathsep.join([str(FERRAMENTAS), os.environ.get("PATH", "")])
    if not shutil.which("ffmpeg"):
        for f in pacotes.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
            extra.append(str(f.parent))
            break
    if not shutil.which("deno"):
        for f in pacotes.glob("DenoLand.Deno*/deno.exe"):
            extra.append(str(f.parent))
            break
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])
    return shutil.which("ffmpeg"), shutil.which("deno")


def atualizar_ytdlp(log) -> None:
    """Só na versão instalada: atualiza o yt-dlp (no máximo 1 vez por dia).
    O YouTube muda com frequência e o yt-dlp corrige rápido. A versão nova vale
    a partir da próxima vez que o programa abrir."""
    if not INSTALADO:
        return
    marca = DADOS / "ultima_atualizacao.txt"
    try:
        if time.time() - float(marca.read_text()) < 24 * 3600:
            return
    except (OSError, ValueError):
        pass
    try:
        from importlib.metadata import version
        antes = version("yt-dlp")
        r = subprocess.run(
            [str(PYTHON_PROPRIO), "-m", "pip", "install", "-U", "--disable-pip-version-check",
             "--no-warn-script-location", "yt-dlp[default]"],
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        marca.write_text(str(time.time()))
        depois = r.stdout.split("Successfully installed")[-1] if "Successfully installed" in r.stdout else ""
        if "yt-dlp-" in depois or "yt_dlp-" in depois:
            log(f"yt-dlp atualizado (era {antes}). A versão nova vale quando você abrir o programa de novo.")
        elif r.returncode != 0:
            log("⚠ Não consegui atualizar o yt-dlp agora (sem internet?). Tento de novo amanhã.")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"⚠ Não consegui atualizar o yt-dlp: {e}")
