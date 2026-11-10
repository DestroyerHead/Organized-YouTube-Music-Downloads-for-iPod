"""Download pelo yt-dlp, sempre em M4A (AAC) sem conversão."""
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

import yt_dlp

from .busca import limpar_canal, limpar_titulo, separar_artista_titulo

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class _Logger:
    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if any(x in msg for x in ("Falling back", "nsig", "YouTube Music is not directly supported")):
            return
        self.log("yt-dlp: " + msg)

    def error(self, msg):
        self.log("yt-dlp: " + msg)


def link_video(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def tem_video_e_playlist(url: str) -> bool:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return "v" in q and "list" in q


def so_video(url: str) -> str:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return link_video(q["v"][0]) if "v" in q else url


def eh_playlist(url: str) -> bool:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return "list" in q and "v" not in q


class Baixador:
    def __init__(self, pasta_tmp: Path, log, max_playlist: int = 500, cancelado=lambda: False):
        self.cancelado = cancelado
        self.pasta_tmp = Path(pasta_tmp)
        self.pasta_tmp.mkdir(parents=True, exist_ok=True)
        base = dict(quiet=True, no_warnings=False, noprogress=True, logger=_Logger(log),
                    retries=5, fragment_retries=5, socket_timeout=30)
        self._lista = yt_dlp.YoutubeDL({**base, "extract_flat": "in_playlist",
                                        "playlistend": max_playlist, "noplaylist": False})
        self._ydl = yt_dlp.YoutubeDL({
            **base,
            "noplaylist": True,
            "format": "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio",
            "outtmpl": str(self.pasta_tmp / "%(id)s.%(ext)s"),
            # se já for m4a/AAC (quase sempre) não reconverte; só arruma o contêiner
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
            "overwrites": True,
            "progress_hooks": [self._progresso],
        })

    def _progresso(self, _d):
        if self.cancelado():
            raise yt_dlp.utils.DownloadCancelled("cancelado")

    def limpar_tmp(self):
        """Apaga restos de downloads interrompidos."""
        for f in self.pasta_tmp.iterdir():
            try:
                f.unlink()
            except OSError:
                pass

    def listar(self, url: str, playlist: bool) -> tuple[str | None, list[dict]]:
        """Devolve (nome da playlist, [{id, titulo, artista}])."""
        if not playlist:
            url = so_video(url)
        info = self._lista.extract_info(url, download=False)
        if info.get("_type") in ("playlist", "multi_video"):
            itens, vistos = [], set()
            for e in info.get("entries") or []:
                if e and e.get("id") and len(e["id"]) == 11 and e["id"] not in vistos:
                    vistos.add(e["id"])
                    itens.append({"id": e["id"], "titulo": e.get("title") or "",
                                  "artista": limpar_canal(e.get("channel") or e.get("uploader") or "")})
            return info.get("title"), itens
        return None, [{"id": info["id"], "titulo": info.get("title") or "", "artista": ""}]

    def info(self, video_id: str) -> dict:
        return self._ydl.extract_info(link_video(video_id), download=False)

    def baixar(self, info: dict) -> Path:
        res = self._ydl.process_ie_result(info, download=True)
        caminho = res["requested_downloads"][0]["filepath"]
        return Path(caminho)


def consulta(info: dict) -> tuple[str, str]:
    """Melhor palpite de (artista, título) a partir dos dados do YouTube."""
    artistas = info.get("artists") or ([info["artist"]] if info.get("artist") else [])
    if info.get("track") and artistas:
        return ", ".join(artistas), info["track"]
    titulo = limpar_titulo(info.get("title") or "")
    a, t = separar_artista_titulo(titulo)
    if a:
        return a, t
    return limpar_canal(info.get("channel") or info.get("uploader") or ""), titulo


def capa_do_youtube(info: dict) -> bytes | None:
    """Pega a miniatura do vídeo e corta no meio pra ficar quadrada (via ffmpeg)."""
    url = info.get("thumbnail")
    if not url:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "capa.jpg"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", url, "-vf",
               "crop='min(iw,ih)':'min(iw,ih)',scale=600:600", "-frames:v", "1", str(saida)]
        try:
            subprocess.run(cmd, check=True, timeout=60, capture_output=True, creationflags=SEM_JANELA)
            return saida.read_bytes()
        except (subprocess.SubprocessError, OSError):
            return None
