"""Tocador usando o player do próprio Windows (toca M4A/AAC sem instalar codec)."""
from datetime import timedelta
from pathlib import Path

from winrt.windows.foundation import Uri
from winrt.windows.media.core import MediaSource
from winrt.windows.media.playback import MediaPlaybackState, MediaPlayer


class Player:
    def __init__(self, volume: float = 0.8):
        self._p = MediaPlayer()
        self._p.volume = volume
        self._terminou = False
        self._p.add_media_ended(self._fim)
        self.arquivo: str | None = None

    def _fim(self, _sender, _args):  # chamado por outra thread do Windows
        self._terminou = True

    def tocar(self, arquivo: str):
        self._terminou = False
        self.arquivo = arquivo
        self._p.source = MediaSource.create_from_uri(Uri(Path(arquivo).resolve().as_uri()))
        self._p.play()

    def alternar(self):
        """Tocar/pausar."""
        if self.tocando():
            self._p.pause()
        elif self.arquivo:
            self._p.play()

    def parar(self):
        """Para e solta o arquivo (necessário antes de apagar)."""
        self._p.pause()
        self._p.source = None
        self.arquivo = None
        self._terminou = False

    def tocando(self) -> bool:
        return self._p.playback_session.playback_state == MediaPlaybackState.PLAYING

    def terminou(self) -> bool:
        """True uma única vez quando a música chega ao fim."""
        if self._terminou:
            self._terminou = False
            return True
        return False

    def posicao(self) -> float:
        return self._p.playback_session.position.total_seconds() if self.arquivo else 0.0

    def duracao(self) -> float:
        return self._p.playback_session.natural_duration.total_seconds() if self.arquivo else 0.0

    def pular_para(self, segundos: float):
        if self.arquivo:
            self._p.playback_session.position = timedelta(seconds=max(0.0, segundos))

    @property
    def volume(self) -> float:
        return self._p.volume

    @volume.setter
    def volume(self, v: float):
        self._p.volume = min(1.0, max(0.0, v))
