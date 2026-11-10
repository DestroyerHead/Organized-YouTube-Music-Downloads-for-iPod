"""Motor do programa, em duas "esteiras":

  1. DOWNLOADS: até N músicas baixando ao mesmo tempo (N escolhido na janela, 1 a 8).
     Cada uma: já tenho esse vídeo? → lê o vídeo → baixa → entra na fila do iTunes.
  2. iTUNES (a thread principal do motor, uma música por vez, ~20 por minuto por regra
     da Apple): consulta os dados → repetida? → grava as tags → manda pro iTunes.

A thread principal também cuida dos pedidos da janela (links colados, edições,
apagar, mudar gênero) e é a única que conversa com o iTunes (COM).

Cada pedido da janela (um link, um "tentar de novo") é um *lote* numerado.
Parar = cancelar todos os lotes até o número X; downloads em andamento são interrompidos."""
import dataclasses
import queue
import random
import re
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import config, tags
from .baixar import Baixador, capa_do_youtube, consulta
from .busca import ITunesAPI, Meta, baixar_bytes
from .historico import Historico, Indice

# estados mostrados na lista
FILA, LENDO, BAIXANDO, ESPERANDO, BUSCANDO, PRONTA, REVISAR, REPETIDA, ERRO, CANCELADA, APAGADA = (
    "na fila", "lendo", "baixando", "esperando iTunes", "buscando dados", "pronta", "revisar",
    "já tenho", "erro", "cancelada", "você apagou")
MAX_PARALELOS = 8


def nome_arquivo(artista: str, titulo: str) -> str:
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", f"{artista} - {titulo}").strip(" .")
    return (nome[:150] or "musica") + ".m4a"


def limpar_erro(e: Exception) -> str:
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", str(e))


class Motor(threading.Thread):
    def __init__(self, cfg: dict, eventos: queue.Queue):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ev = eventos
        # pedidos da janela: (tipo, carga, playlist_itunes, lote)
        #   tipo "link": carga=(url, é_playlist) · tipo "itens": carga=[{id, titulo, artista, forcar}]
        self.trabalhos: queue.Queue = queue.Queue()
        self.urgente: queue.Queue = queue.Queue()     # edições/buscas/apagar/gênero (passam na frente)
        self.downloads: queue.Queue = queue.Queue()   # músicas esperando um download livre
        self.baixados: queue.Queue = queue.Queue()    # músicas baixadas esperando o iTunes
        self.cancelar_ate = 0
        self.paralelos = max(1, min(MAX_PARALELOS, int(cfg.get("downloads_simultaneos", 3))))
        self.itunes = None
        self.hist: Historico | None = None
        self.genero_forcado: dict[str, str] = {}      # id -> gênero escolhido antes de terminar
        self._em_andamento: set[str] = set()          # ids na fila/baixando/esperando iTunes
        self._trava = threading.Lock()
        self._baixando = 0
        self._lendo_link = False
        self._ultimo_status = ""

    # ------------------------------------------------------- controle
    def parar_tudo(self, ate_lote: int):
        """Cancela todos os pedidos já feitos (até ate_lote), inclusive downloads em andamento."""
        self.cancelar_ate = max(self.cancelar_ate, ate_lote)

    def _cancelado(self, lote) -> bool:
        return lote is not None and lote <= self.cancelar_ate

    def definir_paralelos(self, n: int):
        self.paralelos = max(1, min(MAX_PARALELOS, int(n)))

    @property
    def trabalhando(self) -> bool:
        return bool(self._em_andamento) or self._lendo_link or not self.trabalhos.empty()

    @property
    def ocupado(self) -> bool:  # compatibilidade
        return self.trabalhando

    # ----------------------------------------------------------- eventos
    def emit(self, *ev):
        self.ev.put(ev)

    def log(self, msg: str):
        self.emit("log", msg)
        try:
            with open(config.DADOS / "log.txt", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        except OSError:
            pass

    def linha(self, vid: str, lote, **campos):
        self.emit("linha", vid, campos, lote)

    def _terminar(self, it: dict, **campos):
        """Música saiu das esteiras (pronta, repetida, erro, cancelada…)."""
        self.linha(it["id"], it["lote"], **campos)
        with self._trava:
            self._em_andamento.discard(it["id"])

    # ------------------------------------------------------------ início
    def run(self):
        try:
            self._iniciar()
        except Exception as e:  # noqa: BLE001
            self.log(f"Erro ao iniciar: {e}\n{traceback.format_exc()}")
            self.emit("pronto_para_uso", False)
            return
        for i in range(MAX_PARALELOS):
            threading.Thread(target=self._trabalhador, args=(i,), daemon=True).start()
        self.emit("pronto_para_uso", True)
        while True:
            self._fazer_urgentes()
            self._atualizar_status()
            try:
                self._expandir(*self.trabalhos.get_nowait())
            except queue.Empty:
                pass
            try:
                pronto = self.baixados.get(timeout=0.2)
            except queue.Empty:
                continue
            self._finalizar(*pronto)

    def _iniciar(self):
        ffmpeg, deno = config.preparar_ferramentas()
        threading.Thread(target=config.atualizar_ytdlp, args=(self.log,), daemon=True).start()
        if not ffmpeg:
            self.log("⚠ ffmpeg não encontrado. Instale com: winget install Gyan.FFmpeg")
        if not deno:
            self.log("⚠ Deno não encontrado (o yt-dlp precisa dele pro YouTube). Instale com: winget install DenoLand.Deno")
        self.pasta = Path(self.cfg["pasta_musicas"])
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.pasta_tmp = config.DADOS / "baixando"
        self.hist = Historico(config.DADOS / "historico.json")
        self.indice = Indice()
        self.hist.indexar(self.indice)
        self.api = ITunesAPI(self.cfg["pais_loja"], self.log)
        self.bx = Baixador(self.pasta_tmp, self.log, int(self.cfg["max_playlist"]))  # só pra ler links
        self.bx.limpar_tmp()  # restos de downloads interrompidos da última vez

        self.emit("status", "Conectando ao iTunes…")
        try:
            from .itunes import ITunes
            self.itunes = ITunes()
            ok, faltando = self.itunes.indexar(self.indice)
            self.log(f"iTunes {self.itunes.versao} conectado: {ok} músicas com arquivo na biblioteca.")
            if faltando:
                self.log(f"⚠ {faltando} músicas da biblioteca do iTunes estão sem o arquivo no PC "
                         "(aparecem com '!' no iTunes). Elas não contam como 'já tenho'.")
        except Exception as e:  # noqa: BLE001
            self.itunes = None
            self.log(f"⚠ Não consegui controlar o iTunes ({e}). As músicas ficam em {self.pasta}.")
        self.emit("status", "Pronto. Cole um link do YouTube ou YouTube Music.")

    def _atualizar_status(self):
        if self.trabalhando:
            partes = []
            if self._lendo_link:
                partes.append("lendo o link")
            if self._baixando:
                partes.append(f"baixando {self._baixando}")
            if self.baixados.qsize():
                partes.append(f"esperando iTunes {self.baixados.qsize()}")
            if self.downloads.qsize():
                partes.append(f"na fila {self.downloads.qsize()}")
            texto = "Trabalhando: " + " · ".join(partes) if partes else "Trabalhando…"
        else:
            texto = "Pronto. Cole outro link."
        if texto != self._ultimo_status:
            self._ultimo_status = texto
            self.emit("status", texto)

    # ------------------------------------------------- pedidos → esteira
    def _expandir(self, tipo, carga, nome_pl, lote):
        """Transforma um pedido (link ou lista) em músicas na esteira de downloads."""
        if tipo == "link":
            if self._cancelado(lote):
                return
            self._lendo_link = True
            self.emit("status", "Lendo o link…")
            try:
                nome, itens = self.bx.listar(*carga)
            except Exception as e:  # noqa: BLE001
                self.log(f"Erro ao ler o link: {limpar_erro(e)}")
                return
            finally:
                self._lendo_link = False
            if nome:
                self.log(f"Playlist “{nome}”: {len(itens)} músicas.")
        else:
            itens = carga
        for it in itens:
            vid = it["id"]
            with self._trava:
                if vid in self._em_andamento:
                    continue
                self._em_andamento.add(vid)
            item = {"id": vid, "titulo": it.get("titulo", ""), "artista": it.get("artista", ""),
                    "forcar": bool(it.get("forcar")), "nome_pl": nome_pl, "lote": lote}
            self.linha(vid, lote, status=FILA, titulo=item["titulo"], artista=item["artista"],
                       genero=self.genero_forcado.get(vid, ""), ano="", info="")
            self.downloads.put(item)

    # -------------------------------------------- esteira 1: downloads
    def _trabalhador(self, numero: int):
        lote_atual = [None]
        bx = Baixador(self.pasta_tmp, self.log, cancelado=lambda: self._cancelado(lote_atual[0]))
        while True:
            if numero >= self.paralelos:
                time.sleep(0.5)
                continue
            try:
                it = self.downloads.get(timeout=0.5)
            except queue.Empty:
                continue
            lote_atual[0] = it["lote"]
            if self._baixar(bx, it):
                self._pausa(it["lote"])

    def _baixar(self, bx: Baixador, it: dict) -> bool:
        """Baixa uma música e passa pra esteira do iTunes. True se baixou (pra fazer a pausa)."""
        vid, lote = it["id"], it["lote"]
        if self._cancelado(lote):
            self._terminar(it, status=CANCELADA, info="")
            return False
        # repetida pelo mesmo vídeo: nem baixa
        if not it["forcar"] and self.hist.apagado(vid=vid):
            r = self.hist.d["apagados"].get(vid, {})
            self._terminar(it, status=APAGADA, titulo=r.get("titulo", ""), artista=r.get("artista", ""),
                           info="botão direito → Baixar mesmo assim")
            return False
        reg = self.hist.video(vid)
        if reg:
            self._terminar(it, status=REPETIDA, titulo=reg["titulo"], artista=reg["artista"],
                           genero=reg.get("genero", ""), ano=reg.get("ano", ""), info="já baixada antes")
            return False
        motivo = self.hist.pulado(vid)
        if motivo:
            self._terminar(it, status=REPETIDA, info=motivo)
            return False

        with self._trava:
            self._baixando += 1
        try:
            self.linha(vid, lote, status=LENDO)
            info = bx.info(vid)
            artista, titulo = consulta(info)
            self.linha(vid, lote, status=BAIXANDO, titulo=titulo, artista=artista)
            tmp = bx.baixar(info)
            if self._cancelado(lote):
                raise RuntimeError("cancelado")
        except Exception as e:  # noqa: BLE001
            self._limpar_restos(vid)
            if self._cancelado(lote):
                self._terminar(it, status=CANCELADA, info="")
            else:
                msg = limpar_erro(e)
                self._terminar(it, status=ERRO, info=msg[:200])
                self.log(f"Erro em {it.get('titulo') or vid}: {msg}")
            return False
        finally:
            with self._trava:
                self._baixando -= 1
        self.linha(vid, lote, status=ESPERANDO)
        self.baixados.put((it, info, tmp, artista, titulo))
        return True

    def _pausa(self, lote):
        fim = time.time() + random.uniform(self.cfg["pausa_min"], self.cfg["pausa_max"])
        while time.time() < fim and not self._cancelado(lote):
            time.sleep(0.25)

    def _limpar_restos(self, vid: str):
        for f in self.pasta_tmp.glob(f"{vid}.*"):
            try:
                f.unlink()
            except OSError:
                pass

    # ---------------------------------------- esteira 2: iTunes e tags
    def _finalizar(self, it: dict, info: dict, tmp: Path, artista: str, titulo: str):
        vid, lote = it["id"], it["lote"]
        try:
            if self._cancelado(lote):
                raise RuntimeError("cancelado")
            self.linha(vid, lote, status=BUSCANDO)
            candidatos = self.api.buscar(artista, titulo, info.get("title") or "", info.get("duration"))
            melhor = candidatos[0] if candidatos else None
            confiavel = bool(melhor and melhor.nota >= self.cfg["confianca_minima"])
            meta = melhor if confiavel else Meta(titulo=titulo, artista=artista, fonte="YouTube")

            # apagada antes (mesma música vinda de outro vídeo)
            if not it["forcar"] and self.hist.apagado(itunes_id=meta.itunes_id if confiavel else None,
                                                      artista=meta.artista, titulo=meta.titulo):
                Path(tmp).unlink(missing_ok=True)
                self._terminar(it, status=APAGADA, titulo=meta.titulo, artista=meta.artista,
                               info="botão direito → Baixar mesmo assim")
                return
            # repetida: mesma música de outro vídeo, ou já estava no iTunes
            motivo = None
            if confiavel and self.hist.por_itunes(meta.itunes_id):
                motivo = f"mesma música de outro vídeo ({Path(self.hist.por_itunes(meta.itunes_id)['arquivo']).name})"
            elif self.indice.tem(meta.artista, meta.titulo):
                motivo = "já está no iTunes"
            if motivo:
                Path(tmp).unlink(missing_ok=True)
                self.hist.pular(vid, motivo)
                self._terminar(it, status=REPETIDA, titulo=meta.titulo, artista=meta.artista,
                               genero=meta.genero, ano=meta.ano, info=motivo)
                return

            capa = None
            if meta.capa_url:
                try:
                    capa = baixar_bytes(meta.capa_url)
                except OSError:
                    capa = None
            if capa is None:
                capa = capa_do_youtube(info)
            if vid in self.genero_forcado:  # você escolheu o gênero antes de terminar
                meta = dataclasses.replace(meta, genero=self.genero_forcado.pop(vid))
            tags.gravar(str(tmp), meta, capa, vid)

            destino = self.pasta / nome_arquivo(meta.artista, meta.titulo)
            i = 2
            while destino.exists():
                destino = self.pasta / nome_arquivo(meta.artista, f"{meta.titulo} ({i})")
                i += 1
            shutil.move(str(tmp), destino)

            pid, local = None, str(destino)
            if self.itunes:
                pid, local = self.itunes.adicionar(str(destino), it["nome_pl"])
                if pid and Path(local).resolve() != destino.resolve() and Path(local).exists():
                    destino.unlink(missing_ok=True)  # o iTunes fez a própria cópia

            self.hist.salvar(vid, {
                "arquivo": local, "titulo": meta.titulo, "artista": meta.artista,
                "genero": meta.genero, "ano": meta.ano, "itunes_id": meta.itunes_id if confiavel else None,
                "pid": pid, "fonte": meta.fonte, "nota": meta.nota if melhor else 0,
                "revisar": not confiavel, "data": datetime.now().isoformat(timespec="seconds"),
            })
            self.indice.adicionar(meta.artista, meta.titulo)
            self.emit("baixada", vid)
            campos = dict(titulo=meta.titulo, artista=meta.artista, genero=meta.genero, ano=meta.ano)
            if confiavel:
                self._terminar(it, status=PRONTA, info="", **campos)
            else:
                dica = f"melhor no iTunes: {melhor.resumo()} ({melhor.nota:.0%})" if melhor else "não achei no iTunes"
                self._terminar(it, status=REVISAR, info=dica, **campos)
        except Exception as e:  # noqa: BLE001
            Path(tmp).unlink(missing_ok=True)
            if self._cancelado(lote):
                self._terminar(it, status=CANCELADA, info="")
            else:
                msg = limpar_erro(e)
                self._terminar(it, status=ERRO, info=msg[:200])
                self.log(f"Erro em {titulo or vid}: {msg}")

    # ----------------------------------------------- pedidos da janela
    def _fazer_urgentes(self):
        while True:
            try:
                tipo, *args = self.urgente.get_nowait()
            except queue.Empty:
                return
            try:
                if tipo == "buscar":
                    vid, termo = args
                    self.emit("candidatos", vid, self.api.buscar_livre(termo))
                elif tipo == "editar":
                    self._editar(*args)
                elif tipo == "remover_sumidas":
                    self._remover_sumidas()
                elif tipo == "apagar":
                    self._apagar(*args)
                elif tipo == "mudar_genero":
                    self._mudar_genero(*args)
            except Exception as e:  # noqa: BLE001
                self.log(f"Erro: {e}")
                if tipo == "buscar":
                    self.emit("candidatos", args[0], [])

    def _mudar_genero(self, vids: list[str], genero: str):
        """Baixadas: muda no arquivo e no iTunes. Ainda na fila: guarda pra aplicar ao terminar."""
        feitas, pendentes, falhas = 0, 0, []
        for vid in vids:
            reg = self.hist.d["videos"].get(vid)
            if reg is None:
                self.genero_forcado[vid] = genero
                pendentes += 1
                self.emit("linha", vid, {"genero": genero, "info": "gênero será aplicado ao terminar"}, None)
                continue
            if not Path(reg.get("arquivo", "")).is_file():
                falhas.append(f"{reg.get('titulo', vid)} (arquivo não encontrado)")
                continue
            meta = Meta(titulo=reg.get("titulo", ""), artista=reg.get("artista", ""), genero=genero,
                        ano=reg.get("ano", ""), itunes_id=reg.get("itunes_id"))
            try:
                tags.gravar(reg["arquivo"], meta, None, vid)  # None = mantém a capa
            except OSError as e:
                falhas.append(f"{reg.get('titulo', vid)} ({e})")
                continue
            if self.itunes and reg.get("pid"):
                self.itunes.atualizar(reg["pid"])
            reg["genero"] = genero
            self.hist.salvar(vid, reg)
            self.emit("linha", vid, {"genero": genero}, None)
            feitas += 1
        self.emit("baixada", None)
        partes = []
        if feitas:
            partes.append(f"{feitas} mudada(s) no arquivo e no iTunes")
        if pendentes:
            partes.append(f"{pendentes} ainda na fila (o gênero entra quando terminar)")
        self.log(f"Gênero “{genero}”: " + (", ".join(partes) or "nenhuma música mudada") + ".")
        if falhas:
            self.log("⚠ Não consegui mudar: " + "; ".join(falhas[:10]))

    def _apagar(self, vids: list[str]):
        """Apaga de vez: arquivo + iTunes + histórico (e lembra que foi apagada)."""
        apagadas, falhas, fora_itunes = 0, [], 0
        for vid in vids:
            r = self.hist.d["videos"].get(vid)
            if not r:
                continue
            arq = Path(r.get("arquivo", ""))
            if arq.is_file():
                for _ in range(15):  # o player pode demorar um pouco pra soltar o arquivo
                    try:
                        arq.unlink()
                        break
                    except PermissionError:
                        time.sleep(0.3)
                else:
                    falhas.append(arq.name)
                    continue
            if r.get("pid") and not (self.itunes and self.itunes.remover(r["pid"])):
                fora_itunes += 1
            self.indice.remover(r.get("artista", ""), r.get("titulo", ""))
            self.hist.apagar(vid)
            apagadas += 1
        self.emit("baixada", None)
        self.log(f"Apagada(s) {apagadas} música(s).")
        if falhas:
            self.log("⚠ Não consegui apagar (arquivo em uso): " + ", ".join(falhas))
        if fora_itunes:
            self.log(f"⚠ {fora_itunes} não foram encontradas no iTunes pra tirar de lá "
                     "(se aparecerem com '!' no iTunes, apague por lá).")

    def _remover_sumidas(self):
        sumidas = [(vid, r) for vid, r in self.hist.todos() if not r["existe"]]
        no_itunes = 0
        for _vid, r in sumidas:
            self.indice.remover(r.get("artista", ""), r.get("titulo", ""))
            if self.itunes and r.get("pid") and self.itunes.remover_se_sem_arquivo(r["pid"]):
                no_itunes += 1
        self.hist.remover([vid for vid, _ in sumidas])
        self.emit("baixada", None)
        self.log(f"Removidas {len(sumidas)} música(s) sem arquivo do histórico"
                 + (f" e {no_itunes} do iTunes." if no_itunes else "."))

    def _editar(self, vid: str, meta: Meta):
        reg = self.hist.video(vid)
        if not reg:
            self.log("Não achei o arquivo dessa música pra editar.")
            return
        capa = None
        if meta.capa_url:
            try:
                capa = baixar_bytes(meta.capa_url)
            except OSError:
                pass
        tags.gravar(reg["arquivo"], meta, capa, vid)
        if self.itunes and reg.get("pid"):
            self.itunes.atualizar(reg["pid"])
        reg.update(titulo=meta.titulo, artista=meta.artista, genero=meta.genero, ano=meta.ano,
                   revisar=False, fonte="editado")
        if meta.itunes_id:
            reg["itunes_id"] = meta.itunes_id
        self.hist.salvar(vid, reg)
        self.indice.adicionar(meta.artista, meta.titulo)
        self.emit("linha", vid, dict(status=PRONTA, titulo=meta.titulo, artista=meta.artista,
                                     genero=meta.genero, ano=meta.ano, info="editada"), None)
        self.emit("baixada", vid)
        self.log(f"Atualizada: {meta.resumo()}")
