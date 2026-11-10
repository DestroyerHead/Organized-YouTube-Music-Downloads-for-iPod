"""Memória do que já foi baixado, pra não baixar repetido."""
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from .busca import chave_artista, chave_titulo, mesmo_artista


class Indice:
    """Artista + título normalizados de todas as músicas que você já tem."""

    def __init__(self):
        self._por_titulo: dict[str, list[str]] = {}

    def adicionar(self, artista: str, titulo: str) -> None:
        t = chave_titulo(titulo)
        if t:
            self._por_titulo.setdefault(t, []).append(chave_artista(artista))

    def tem(self, artista: str, titulo: str) -> bool:
        a = chave_artista(artista)
        return any(mesmo_artista(a, x) for x in self._por_titulo.get(chave_titulo(titulo), []))

    def remover(self, artista: str, titulo: str) -> None:
        lista = self._por_titulo.get(chave_titulo(titulo), [])
        a = chave_artista(artista)
        if a in lista:
            lista.remove(a)

    def __len__(self):
        return sum(len(v) for v in self._por_titulo.values())


class Historico:
    """dados/historico.json
    videos:  id do YouTube -> música baixada (arquivo, dados, id no iTunes)
    itunes:  id da música na loja do iTunes -> id do YouTube
    pulados: id do YouTube -> motivo (repetida), pra não precisar checar de novo
    apagados: id do YouTube -> música que você apagou (não baixa de novo sozinho)
    """

    def __init__(self, arquivo: Path):
        self.arquivo = Path(arquivo)
        self._trava = threading.Lock()
        self.d = {"videos": {}, "itunes": {}, "pulados": {}, "apagados": {}}
        if self.arquivo.exists():
            try:
                self.d.update(json.loads(self.arquivo.read_text("utf-8")))
            except (OSError, ValueError):
                pass

    def _gravar(self):
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, indent=1, ensure_ascii=False), "utf-8")
        os.replace(tmp, self.arquivo)

    def video(self, vid: str) -> dict | None:
        r = self.d["videos"].get(vid)
        return r if r and Path(r.get("arquivo", "")).exists() else None

    def por_itunes(self, itunes_id) -> dict | None:
        vid = self.d["itunes"].get(str(itunes_id)) if itunes_id else None
        return self.video(vid) if vid else None

    def todos(self) -> list[tuple[str, dict]]:
        """Cópia de todas as músicas baixadas (com 'existe' = arquivo ainda está lá)."""
        with self._trava:
            itens = [(vid, dict(r)) for vid, r in self.d["videos"].items()]
        for _, r in itens:
            r["existe"] = Path(r.get("arquivo", "")).exists()
        return itens

    def status(self, ids: list) -> dict[str, str]:
        """Pra extensão: 'tenho', 'apagada' ou '' pra cada id do YouTube."""
        out = {}
        for vid in ids[:2000]:
            if not isinstance(vid, str):
                continue
            if self.video(vid) or vid in self.d["pulados"]:
                out[vid] = "tenho"
            elif self.apagado(vid=vid):
                out[vid] = "apagada"
            else:
                out[vid] = ""
        return out

    def pulado(self, vid: str) -> str | None:
        return self.d["pulados"].get(vid)

    # ---------------------------------------------------------- apagadas
    @staticmethod
    def _mesma_musica(r: dict, itunes_id, artista: str, titulo: str) -> bool:
        if itunes_id and r.get("itunes_id") == itunes_id:
            return True
        return bool(titulo) and chave_titulo(r.get("titulo", "")) == chave_titulo(titulo) and \
            mesmo_artista(chave_artista(r.get("artista", "")), chave_artista(artista))

    def apagado(self, vid: str = "", itunes_id=None, artista: str = "", titulo: str = "") -> bool:
        """Você apagou esse vídeo, ou essa mesma música vinda de outro vídeo?"""
        ap = self.d["apagados"]
        if vid and vid in ap:
            return True
        return any(self._mesma_musica(r, itunes_id, artista, titulo) for r in list(ap.values()))

    def apagar(self, vid: str) -> dict | None:
        with self._trava:
            r = self.d["videos"].pop(vid, None)
            if not r:
                return None
            self.d["itunes"] = {k: v for k, v in self.d["itunes"].items() if v != vid}
            self.d["apagados"][vid] = {"titulo": r.get("titulo", ""), "artista": r.get("artista", ""),
                                       "itunes_id": r.get("itunes_id"),
                                       "data": datetime.now().isoformat(timespec="seconds")}
            self.d["pulados"] = {}  # quem foi pulado por causa dela é checado de novo
            self._gravar()
            return r

    def salvar(self, vid: str, registro: dict) -> None:
        with self._trava:
            self.d["videos"][vid] = registro
            self.d["pulados"].pop(vid, None)
            # baixou de novo ("baixar mesmo assim"): deixa de contar como apagada
            self.d["apagados"] = {
                k: r for k, r in self.d["apagados"].items()
                if k != vid and not self._mesma_musica(r, registro.get("itunes_id"),
                                                       registro.get("artista", ""), registro.get("titulo", ""))}
            if registro.get("itunes_id"):
                self.d["itunes"][str(registro["itunes_id"])] = vid
            self._gravar()

    def remover(self, vids: list[str]) -> None:
        """Esquece essas músicas (pra poderem ser baixadas de novo)."""
        with self._trava:
            for vid in vids:
                self.d["videos"].pop(vid, None)
            self.d["itunes"] = {k: v for k, v in self.d["itunes"].items() if v in self.d["videos"]}
            # os "pulados" podem ter sido pulados por causa de uma dessas; checa tudo de novo
            self.d["pulados"] = {}
            self._gravar()

    def pular(self, vid: str, motivo: str) -> None:
        with self._trava:
            self.d["pulados"][vid] = motivo
            self._gravar()

    def indexar(self, indice: Indice) -> None:
        for vid in list(self.d["videos"]):
            r = self.video(vid)
            if r:
                indice.adicionar(r["artista"], r["titulo"])
