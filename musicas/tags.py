"""Gravação das tags no arquivo M4A (formato que o iTunes e o iPod leem)."""
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from .busca import Meta

PREFIXO = "----:com.ipodmusicas:"


def gravar(caminho: str, meta: Meta, capa: bytes | None, video_id: str = "") -> None:
    """Apaga as tags antigas e grava título, artista, gênero, ano e capa. Sem álbum."""
    audio = MP4(caminho)
    if capa is None and audio.tags and "covr" in audio.tags:
        capa = bytes(audio.tags["covr"][0])  # mantém a capa que já tinha
    if audio.tags is None:
        audio.add_tags()
    audio.tags.clear()

    audio.tags["\xa9nam"] = [meta.titulo]
    audio.tags["\xa9ART"] = [meta.artista]
    audio.tags["aART"] = [meta.artista]
    if meta.genero:
        audio.tags["\xa9gen"] = [meta.genero]
    if meta.ano:
        audio.tags["\xa9day"] = [str(meta.ano)]
    if capa:
        formato = MP4Cover.FORMAT_PNG if capa[:4] == b"\x89PNG" else MP4Cover.FORMAT_JPEG
        audio.tags["covr"] = [MP4Cover(capa, imageformat=formato)]
    if video_id:
        audio.tags[PREFIXO + "youtube"] = [MP4FreeForm(video_id.encode())]
    if meta.itunes_id:
        audio.tags[PREFIXO + "itunes"] = [MP4FreeForm(str(meta.itunes_id).encode())]
    audio.save()
