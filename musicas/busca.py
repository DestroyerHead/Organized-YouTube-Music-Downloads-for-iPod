"""Limpeza de títulos do YouTube e busca de dados na iTunes Search API."""
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher

API = "https://itunes.apple.com/search"
CABECALHO = {"User-Agent": "ipod-musicas/1.0"}
INTERVALO = 3.1  # a API aceita ~20 buscas por minuto


@dataclass
class Meta:
    titulo: str
    artista: str
    genero: str = ""
    ano: str = ""
    capa_url: str = ""
    itunes_id: int | None = None
    nota: float = 0.0
    fonte: str = ""

    def resumo(self) -> str:
        extra = " · ".join(x for x in (self.genero, self.ano) if x)
        return f"{self.titulo} — {self.artista}" + (f"  ({extra})" if extra else "")


# ---------------------------------------------------------------- texto

def norm(s: str) -> str:
    """minúsculas, sem acento, só letras/números."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(w for w in s.split() if w not in ("e", "and"))


def artista_para_busca(a: str) -> str:
    """'Henrique e Juliano' -> 'Henrique Juliano'; vários artistas -> só o primeiro."""
    a = tirar_feat(a)
    partes = re.split(r"\s*(?:,|&|\bx\b|\bvs\.?)\s*", a, flags=re.I)
    if len(norm(a).split()) > 4 and partes:
        a = partes[0]
    return " ".join(w for w in re.split(r"[\s,&]+", a) if w.lower() not in ("e", "and", "x"))


# palavras que indicam lixo de título de vídeo
LIXO = {
    "official", "oficial", "video", "videoclipe", "clipe", "clip", "lyric", "lyrics",
    "letra", "audio", "visualizer", "visualiser", "hd", "hq", "4k", "8k", "mv",
    "legendado", "legenda", "traducao", "prod", "music",
}
# versões que contam como música diferente (valor = forma canônica)
VERSOES = {
    "ao vivo": "live", "live": "live", "acustico": "acoustic", "acoustic": "acoustic",
    "remix": "remix", "instrumental": "instrumental", "karaoke": "karaoke",
    "sped up": "speed", "speed up": "speed", "acelerada": "speed",
    "slowed": "slowed", "reverb": "slowed", "cover": "cover",
}
_FEAT = r"(?:feat|ft|featuring|part|participacao|participação|com|with)\b\.?"
_COLCHETES = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")


def versoes(s: str) -> set[str]:
    n = f" {norm(s)} "
    return {v for k, v in VERSOES.items() if f" {k} " in n}


def palavras_versao(s: str) -> list[str]:
    n = f" {norm(s)} "
    return [k for k in VERSOES if f" {k} " in n]


def tirar_feat(s: str) -> str:
    s = re.sub(r"\s*[\(\[]\s*" + _FEAT + r"[^\)\]]*[\)\]]", "", s or "", flags=re.I)
    s = re.sub(r"\s+(?:feat|ft|featuring)\.?\s.*$", "", s, flags=re.I)
    return s.strip()


def tirar_parenteses(s: str) -> str:
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", s or "").strip()


def limpar_titulo(t: str) -> str:
    """Tira '(Official Video)', '[Lyrics]', '| Clipe Oficial' etc.
    Mantém '(Ao Vivo)', '(Remix)', '(feat. X)'."""
    t = re.sub(r"\s+(?:\||｜|//)\s+.*$", "", t or "")

    def troca(m):
        dentro = m.group(1)
        if versoes(dentro) or re.match(r"\s*" + _FEAT, dentro, re.I):
            return m.group(0)
        if not norm(dentro) or set(norm(dentro).split()) & LIXO:
            return ""
        return m.group(0)

    t = _COLCHETES.sub(troca, t)
    t = re.sub(r"\s+(?:official|oficial)(?:\s+music)?\s+(?:video|audio|clipe|lyric video)\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+(?:clipe|video)\s+oficial\s*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" -–—_")


def limpar_canal(c: str) -> str:
    c = re.sub(r"\s*-\s*Topic$", "", c or "", flags=re.I)
    c = re.sub(r"VEVO$", "", c, flags=re.I)
    c = re.sub(r"\b(?:Official|Oficial|Canal)\b", "", c, flags=re.I)
    return re.sub(r"\s+", " ", c).strip(" -")


def separar_artista_titulo(t: str) -> tuple[str, str]:
    for sep in (" - ", " – ", " — ", " -- ", " ~ "):
        if sep in t:
            a, b = t.split(sep, 1)
            return a.strip(), b.strip()
    return "", t.strip()


def parecido(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    r = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    comum = len(ta & tb)
    return max(r, 0.6 * comum / len(ta) + 0.4 * comum / len(tb))


# ------------------------------------------------- chaves p/ repetidas

def chave_titulo(t: str) -> str:
    return norm(limpar_titulo(tirar_feat(t)))


def chave_artista(a: str) -> str:
    return norm(tirar_feat(a))


def mesmo_artista(a: str, b: str) -> bool:
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    return bool(ta and tb) and (ta <= tb or tb <= ta)


# ---------------------------------------------------------------- nota

ARTISTA_SUSPEITO = ("karaoke", "tribute", "made famous", "sound alike", "in the style", "cover band")


def nota(q_artista: str, q_titulo: str, q_completo: str, duracao, r: dict) -> float:
    rt, ra = r.get("trackName", ""), r.get("artistName", "")
    rt_sem_feat = tirar_feat(rt)
    rt_base = tirar_parenteses(rt_sem_feat)

    def tit(q):
        return max(parecido(q, rt_sem_feat), parecido(q, rt_base))

    qt = tirar_feat(q_titulo)
    if q_artista:
        s = max(0.45 * parecido(q_artista, ra) + 0.55 * tit(qt),
                0.45 * parecido(qt, ra) + 0.55 * tit(q_artista))  # ordem invertida
    else:
        s = max(0.8 * tit(qt), parecido(q_completo, f"{ra} {rt_base}"))

    qv, rv = versoes(q_completo + " " + q_titulo), versoes(rt)
    if rv != qv:  # versão diferente (ao vivo, remix...): nunca aceita sozinho
        s = min(s - 0.05 * len(rv ^ qv), 0.7)
    if any(w in norm(ra) for w in ARTISTA_SUSPEITO):
        s -= 0.3
    if duracao and r.get("trackTimeMillis"):
        dif = abs(duracao - r["trackTimeMillis"] / 1000)
        if dif <= 4:
            s += 0.08
        elif dif > 45:
            s -= 0.1
    return max(0.0, min(s, 1.0))


def para_meta(r: dict, n: float) -> Meta:
    return Meta(
        titulo=r.get("trackName", ""),
        artista=r.get("artistName", ""),
        genero=r.get("primaryGenreName", ""),
        ano=(r.get("releaseDate") or "")[:4],
        capa_url=(r.get("artworkUrl100") or "").replace("100x100bb", "600x600bb"),
        itunes_id=r.get("trackId"),
        nota=round(n, 3),
        fonte="iTunes",
    )


# ----------------------------------------------------------------- API

class ITunesAPI:
    def __init__(self, pais: str = "BR", log=print):
        self.pais = pais.upper()
        self.log = log
        self._ultima = 0.0

    def _get(self, params: dict) -> list[dict]:
        url = API + "?" + urllib.parse.urlencode(params)
        for i, espera in enumerate((0, 20, 60)):
            if espera:
                self.log(f"A busca do iTunes pediu uma pausa, esperando {espera}s…")
                time.sleep(espera)
            falta = self._ultima + INTERVALO - time.time()
            if falta > 0:
                time.sleep(falta)
            try:
                req = urllib.request.Request(url, headers=CABECALHO)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    dados = json.loads(resp.read().decode("utf-8"))
                self._ultima = time.time()
                return dados.get("results", [])
            except urllib.error.HTTPError as e:
                self._ultima = time.time()
                if e.code not in (403, 429, 500, 502, 503) or i == 2:
                    raise
            except (urllib.error.URLError, TimeoutError):
                self._ultima = time.time()
                if i == 2:
                    raise
        return []

    def buscar(self, artista: str, titulo: str, completo: str = "", duracao=None) -> list[Meta]:
        """Busca a música e devolve candidatos ordenados pela nota."""
        base = tirar_parenteses(tirar_feat(titulo))
        extra = " ".join(palavras_versao(completo + " " + titulo))
        termos = []
        if artista:
            termos.append(f"{artista_para_busca(artista)} {base} {extra}".strip())
        termos.append(f"{base} {extra}".strip() if artista else completo or titulo)

        paises = [self.pais] + (["US"] if self.pais != "US" else [])
        vistos: dict[int, tuple[float, dict]] = {}
        for pais in paises:
            for termo in dict.fromkeys(termos):
                for r in self._get({"term": termo, "media": "music", "entity": "song",
                                    "limit": 15, "country": pais}):
                    tid = r.get("trackId")
                    if r.get("kind") != "song" or tid in vistos:
                        continue
                    vistos[tid] = (nota(artista, titulo, completo, duracao, r), r)
                if max((n for n, _ in vistos.values()), default=0) >= 0.85:
                    break
            if max((n for n, _ in vistos.values()), default=0) >= 0.6:
                break
        ordem = sorted(vistos.values(), key=lambda x: -x[0])
        return [para_meta(r, n) for n, r in ordem[:8]]

    def buscar_livre(self, termo: str) -> list[Meta]:
        """Busca pelo que a pessoa digitou (tela de edição)."""
        res = self._get({"term": termo, "media": "music", "entity": "song", "limit": 15,
                         "country": self.pais})
        res = [r for r in res if r.get("kind") == "song"]
        notas = [(parecido(termo, f"{r.get('artistName', '')} {r.get('trackName', '')}"), r) for r in res]
        return [para_meta(r, n) for n, r in sorted(notas, key=lambda x: -x[0])]


def baixar_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=CABECALHO)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()
