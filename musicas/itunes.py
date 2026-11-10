"""Controle do iTunes pra Windows via COM (adicionar, playlist, ler biblioteca)."""
import os
import time

import pythoncom
import win32com.client

from .historico import Indice

FAIXA_ARQUIVO = 1  # ITTrackKindFile


class ITunes:
    def __init__(self):
        pythoncom.CoInitialize()
        self.app = win32com.client.gencache.EnsureDispatch("iTunes.Application")

    @property
    def versao(self) -> str:
        return self.app.Version

    def indexar(self, indice: Indice) -> tuple[int, int]:
        """Coloca no índice as músicas da biblioteca que têm arquivo.
        Retorna (com arquivo, sem arquivo)."""
        faixas = self.app.LibraryPlaylist.Tracks
        ok = faltando = 0
        for i in range(1, faixas.Count + 1):
            t = faixas.Item(i)
            if t.Kind != FAIXA_ARQUIVO:
                continue
            local = win32com.client.CastTo(t, "IITFileOrCDTrack").Location
            if not local or not os.path.exists(local):
                faltando += 1
                continue
            indice.adicionar(t.Artist or "", t.Name or "")
            ok += 1
        return ok, faltando

    def _playlist(self, nome: str):
        pl = self.app.LibrarySource.Playlists.ItemByName(nome)
        if pl is None:
            pl = self.app.CreatePlaylist(nome)
        return win32com.client.CastTo(pl, "IITUserPlaylist")

    def adicionar(self, caminho: str, playlist: str = "") -> tuple[list[int] | None, str]:
        """Adiciona o arquivo (e coloca na playlist). Retorna (id_persistente, local final).
        Se o iTunes copiar o arquivo pra pasta dele, o local final é a cópia."""
        destino = self._playlist(playlist) if playlist else self.app.LibraryPlaylist
        status = destino.AddFile(caminho)
        inicio = time.time()
        while status is not None and status.InProgress and time.time() - inicio < 120:
            time.sleep(0.2)
        if status is None or not status.Tracks or status.Tracks.Count == 0:
            return None, caminho
        faixa = status.Tracks.Item(1)
        pid = [self.app.ITObjectPersistentIDHigh(faixa), self.app.ITObjectPersistentIDLow(faixa)]
        local = win32com.client.CastTo(faixa, "IITFileOrCDTrack").Location or caminho
        return pid, local

    def _faixa(self, pid: list[int]):
        return self.app.LibraryPlaylist.Tracks.ItemByPersistentID(pid[0], pid[1])

    def remover(self, pid: list[int]) -> bool:
        """Tira a música da biblioteca do iTunes (e de todas as playlists)."""
        try:
            faixa = self._faixa(pid)
            if faixa is None:
                return False
            faixa.Delete()
            return True
        except pythoncom.com_error:
            return False

    def remover_se_sem_arquivo(self, pid: list[int]) -> bool:
        """Tira da biblioteca a música cujo arquivo sumiu (a que fica com '!').
        Se o arquivo ainda existir, não mexe."""
        try:
            faixa = self._faixa(pid)
            if faixa is None:
                return False
            local = win32com.client.CastTo(faixa, "IITFileOrCDTrack").Location
            if local and os.path.exists(local):
                return False
            faixa.Delete()
            return True
        except pythoncom.com_error:
            return False

    def atualizar(self, pid: list[int]) -> bool:
        """Faz o iTunes reler as tags do arquivo depois de uma edição."""
        try:
            faixa = self.app.LibraryPlaylist.Tracks.ItemByPersistentID(pid[0], pid[1])
            if faixa is None:
                return False
            win32com.client.CastTo(faixa, "IITFileOrCDTrack").UpdateInfoFromFile()
            return True
        except pythoncom.com_error:
            return False
