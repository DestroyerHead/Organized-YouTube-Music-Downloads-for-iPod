"""Organized YouTube Music Downloads for iPod — baixa do YouTube / YouTube Music,
arruma os dados e manda pro iTunes.
Abra com dois cliques (ou pelo atalho na área de trabalho)."""
import io
import os
import queue
import re
import subprocess
import sys
import tkinter as tk
import webbrowser
from collections import Counter
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

from musicas import config  # noqa: E402
from musicas.baixar import eh_playlist, link_video, tem_video_e_playlist  # noqa: E402
from musicas.busca import Meta, norm  # noqa: E402
from musicas.historico import Historico  # noqa: E402
from musicas import servidor  # noqa: E402
from musicas.motor import (APAGADA, BAIXANDO, CANCELADA, ERRO, FILA, MAX_PARALELOS,  # noqa: E402
                           PRONTA, REPETIDA, REVISAR, Motor)

COLUNAS_FILA = (("sel", "☐", 34), ("status", "Situação", 110), ("titulo", "Música", 260), ("artista", "Artista", 200),
                ("genero", "Gênero", 120), ("ano", "Ano", 50), ("info", "Detalhes", 320))
COLUNAS_BAIXADAS = (("sel", "☐", 34), ("titulo", "Música", 270), ("artista", "Artista", 210),
                    ("genero", "Gênero", 140), ("ano", "Ano", 55), ("data", "Baixada em", 125),
                    ("situacao", "Situação", 150))
CORES = {PRONTA: "#1b7f3b", REVISAR: "#b85c00", REPETIDA: "#777777", ERRO: "#c0262d",
         CANCELADA: "#777777", APAGADA: "#777777", "sumiu": "#c0262d"}
REPETIVEIS = (ERRO, CANCELADA)
SEM_GENERO = "(sem gênero)"


def nova_lista(pai, colunas) -> ttk.Treeview:
    quadro = ttk.Frame(pai)
    quadro.pack(fill="both", expand=True)
    arvore = ttk.Treeview(quadro, columns=[c[0] for c in colunas], show="headings")
    for chave, nome, larg in colunas:
        arvore.heading(chave, text=nome)
        arvore.column(chave, width=larg, minwidth=larg if chave == "sel" else 40,
                      stretch=chave in ("titulo", "artista", "info"),
                      anchor="center" if chave in ("sel", "ano") else "w")
    for st, cor in CORES.items():
        arvore.tag_configure(st, foreground=cor)
    arvore.tag_configure("tocando", background="#dbe8fb")
    barra = ttk.Scrollbar(quadro, orient="vertical", command=arvore.yview)
    arvore.configure(yscrollcommand=barra.set)
    arvore.pack(side="left", fill="both", expand=True)
    barra.pack(side="left", fill="y")
    return arvore


def tempo(seg: float) -> str:
    seg = int(max(0, seg))
    return f"{seg // 60}:{seg % 60:02d}"


def situacao(r: dict) -> tuple[str, str]:
    """(texto, tag de cor) da música na aba Baixadas."""
    if not r["existe"]:
        return "arquivo não encontrado", "sumiu"
    if r.get("revisar"):
        return ("não achou no iTunes" if nao_achou(r) else "revisar"), REVISAR
    return "ok" + (" (editada)" if r.get("fonte") == "editado" else ""), ""


def nao_achou(r: dict) -> bool:
    return bool(r.get("revisar")) and not r.get("nota")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(config.NOME)
        self.geometry("1180x780")
        self.minsize(900, 560)
        self.cfg = config.carregar()
        self.ev: queue.Queue = queue.Queue()
        self.motor = Motor(self.cfg, self.ev)
        self.linhas: dict[str, dict] = {}
        self.dialogo: "Editor | None" = None
        self.prox_lote = 1      # número do próximo pedido
        self.lote_minimo = 1    # eventos de lotes abaixo disso são ignorados (lista limpa)
        self._atualizar_agendado = False
        # aba Baixadas
        self.marcadas: set[str] = set()       # caixinhas da aba Baixadas
        self.marcadas_fila: set[str] = set()  # caixinhas da aba Fila
        self.filtro_atual = "todas"
        self._filtros: list[str] = []
        self.ordem_col, self.ordem_desc = "data", True
        self._tags_base: dict[str, tuple] = {}
        # player
        self.player = None
        self.tocando_vid: str | None = None
        self._lista_tocar: list[str] = []
        self._arrastando = False
        self._capa_img = None
        self._montar()
        self._iniciar_player()
        self.receptor = None
        try:
            self.receptor = servidor.Servidor(self._pedido_extensao)
        except OSError as e:
            self._log(f"⚠ Não consegui ligar o receptor da extensão do Chrome: {e}")
        self.motor.start()
        self.after(100, self._eventos)
        self.after(250, self._tick_player)
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        # atalhos do player (só na aba Baixadas e fora de campos de texto)
        self.bind_all("<Left>", self._atalho(self._anterior))
        self.bind_all("<Right>", self._atalho(lambda: self._proxima(1)))
        self.bind_all("<Delete>", self._atalho(self._apagar_tocando))
        self.bind_all("<space>", self._atalho(self._pular_pro_meio))

    # ============================================================ tela
    def _montar(self):
        estilo = ttk.Style(self)
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
        estilo.configure("Treeview", rowheight=24)
        estilo.configure("Player.TButton", font=("Segoe UI Symbol", 12), width=3)

        topo = ttk.Frame(self, padding=(12, 12, 12, 4))
        topo.pack(fill="x")
        ttk.Label(topo, text="Link do YouTube ou YouTube Music (música ou playlist):").pack(anchor="w")
        linha = ttk.Frame(topo)
        linha.pack(fill="x", pady=(4, 0))
        self.link = ttk.Entry(linha, font=("Segoe UI", 11))
        self.link.pack(side="left", fill="x", expand=True, ipady=3)
        self.link.bind("<Return>", lambda e: self._baixar())
        self.btn_colar = ttk.Button(linha, text="Colar e baixar", command=self._colar)
        self.btn_colar.pack(side="left", padx=(8, 0))
        self.btn_baixar = ttk.Button(linha, text="Baixar", command=self._baixar)
        self.btn_baixar.pack(side="left", padx=(8, 0))

        opc = ttk.Frame(self, padding=(12, 4, 12, 4))
        opc.pack(fill="x")
        ttk.Label(opc, text="Playlist no iTunes:").pack(side="left")
        self.playlist = tk.StringVar(value=self.cfg["playlist_itunes"])
        ttk.Entry(opc, textvariable=self.playlist, width=28).pack(side="left", padx=(6, 16))
        ttk.Label(opc, text="Downloads ao mesmo tempo:").pack(side="left")
        self.paralelos = tk.StringVar(value=str(self.motor.paralelos))
        caixa = ttk.Spinbox(opc, from_=1, to=MAX_PARALELOS, width=4, textvariable=self.paralelos,
                            state="readonly", command=self._mudar_paralelos)
        caixa.pack(side="left", padx=(6, 4))
        ttk.Label(opc, text="(recomendado: 3)", foreground="#666").pack(side="left")
        ttk.Button(opc, text="Abrir pasta das músicas", command=self._abrir_pasta).pack(side="right")

        # registro e status ficam embaixo de tudo (empacotados antes das abas)
        self.status = tk.StringVar(value="Iniciando…")
        ttk.Label(self, textvariable=self.status, padding=(12, 2, 12, 8)).pack(side="bottom", fill="x")
        baixo = ttk.Frame(self, padding=(12, 4, 12, 0))
        baixo.pack(side="bottom", fill="x")
        self.registro = tk.Text(baixo, height=4, wrap="word", font=("Consolas", 9),
                                state="disabled", background="#f6f6f6", relief="flat")
        self.registro.pack(fill="x")

        self.abas = ttk.Notebook(self, padding=(12, 4, 12, 4))
        self.abas.pack(fill="both", expand=True)
        self._montar_fila()
        self._montar_baixadas()
        self._habilitar(False)

    def _montar_fila(self):
        aba = ttk.Frame(self.abas, padding=6)
        self.abas.add(aba, text="Fila")
        barra = ttk.Frame(aba)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Button(barra, text="↻ Tentar de novo (erros)", command=self._tentar_de_novo).pack(side="left")
        ttk.Button(barra, text="■ Parar", command=self._parar).pack(side="left", padx=6)
        ttk.Button(barra, text="✕ Limpar lista", command=self._limpar).pack(side="left")
        self.btn_genero_fila = ttk.Button(barra, text="🎵 Mudar gênero (0)…", state="disabled",
                                          command=lambda: self._mudar_genero(sorted(self.marcadas_fila), self.fila))
        self.btn_genero_fila.pack(side="left", padx=(16, 0))
        ttk.Label(barra, text="Dois cliques numa música pra corrigir os dados · botão direito pra mais opções",
                  foreground="#666").pack(side="right")
        self.fila = nova_lista(aba, COLUNAS_FILA)
        self.fila.heading("sel", command=lambda: self._marcar_visiveis(self.fila))
        self.fila.bind("<Button-1>", lambda e: self._clique_caixa(self.fila, e))
        self.fila.bind("<Double-1>", self._duplo_fila)
        self.fila.bind("<Button-3>", self._menu_fila)

    def _montar_baixadas(self):
        aba = ttk.Frame(self.abas, padding=6)
        self.abas.add(aba, text="Baixadas")
        self.aba_bx = aba

        b1 = ttk.Frame(aba)
        b1.pack(fill="x", pady=(0, 4))
        ttk.Label(b1, text="Mostrar:").pack(side="left")
        self.combo = ttk.Combobox(b1, state="readonly", width=34)
        self.combo.pack(side="left", padx=(6, 16))
        self.combo.bind("<<ComboboxSelected>>", self._trocar_filtro)
        ttk.Label(b1, text="Procurar:").pack(side="left")
        self.busca = tk.StringVar()
        self.busca.trace_add("write", lambda *_: self._mostrar_baixadas())
        ttk.Entry(b1, textvariable=self.busca, width=32).pack(side="left", padx=6)
        self.contagem = ttk.Label(b1, foreground="#666")
        self.contagem.pack(side="right")

        b2 = ttk.Frame(aba)
        b2.pack(fill="x", pady=(0, 6))
        ttk.Button(b2, text="▶ Tocar", command=self._tocar_selecionada).pack(side="left")
        ttk.Button(b2, text="✎ Corrigir dados…",
                   command=lambda: self._editar_selecionada(self.baixadas)).pack(side="left", padx=6)
        self.btn_apagar = ttk.Button(b2, text="🗑 Apagar marcadas (0)", state="disabled",
                                     command=lambda: self._apagar(sorted(self.marcadas)))
        self.btn_apagar.pack(side="left")
        self.btn_genero_bx = ttk.Button(b2, text="🎵 Mudar gênero (0)…", state="disabled",
                                        command=lambda: self._mudar_genero(sorted(self.marcadas), self.baixadas))
        self.btn_genero_bx.pack(side="left", padx=6)
        ttk.Button(b2, text="Limpar não encontradas", command=self._limpar_sumidas).pack(side="right")
        ttk.Label(b2, text="Dois cliques: tocar · ← →: anterior/próxima · Espaço: meio · Delete: apaga a que toca",
                  foreground="#666").pack(side="right", padx=12)

        # player embaixo da lista
        self._montar_player(aba)

        self.baixadas = nova_lista(aba, COLUNAS_BAIXADAS)
        for chave, _nome, _l in COLUNAS_BAIXADAS:
            cmd = (lambda: self._marcar_visiveis(self.baixadas)) if chave == "sel" else (lambda c=chave: self._ordenar(c))
            self.baixadas.heading(chave, command=cmd)
        self.baixadas.bind("<Button-1>", lambda e: self._clique_caixa(self.baixadas, e))
        self.baixadas.bind("<Double-1>", self._duplo_baixadas)
        self.baixadas.bind("<Button-3>", self._menu_baixadas)
        self._cabecalhos()

    def _montar_player(self, pai):
        p = ttk.Frame(pai, padding=(0, 8, 0, 0))
        p.pack(side="bottom", fill="x")
        caixa = tk.Frame(p, width=64, height=64, bg="#e8e8e8")
        caixa.pack(side="left")
        caixa.pack_propagate(False)  # tamanho fixo, com ou sem imagem
        self.capa = tk.Label(caixa, bg="#e8e8e8", bd=0)
        self.capa.pack(fill="both", expand=True)
        info = ttk.Frame(p)
        info.pack(side="left", fill="x", expand=True, padx=10)
        self.lbl_musica = ttk.Label(info, text="Nada tocando", font=("Segoe UI", 10, "bold"))
        self.lbl_musica.pack(anchor="w")
        self.lbl_artista = ttk.Label(info, text="Dois cliques numa música pra tocar", foreground="#666")
        self.lbl_artista.pack(anchor="w")
        linha = ttk.Frame(info)
        linha.pack(fill="x", pady=(4, 0))
        self.barra_tempo = ttk.Scale(linha, from_=0, to=1000, orient="horizontal")
        self.barra_tempo.pack(side="left", fill="x", expand=True)
        self.barra_tempo.bind("<ButtonPress-1>", lambda e: setattr(self, "_arrastando", True))
        self.barra_tempo.bind("<ButtonRelease-1>", self._soltar_barra)
        self.lbl_tempo = ttk.Label(linha, text="0:00 / 0:00", width=12, anchor="e")
        self.lbl_tempo.pack(side="left", padx=(8, 0))

        bts = ttk.Frame(p)
        bts.pack(side="left", padx=8)
        # takefocus=False: assim o Espaço (atalho) nunca "clica" num botão do player, como o 🗑
        ttk.Button(bts, text="⏮", style="Player.TButton", takefocus=False,
                   command=lambda: self._anterior()).pack(side="left")
        self.btn_play = ttk.Button(bts, text="▶", style="Player.TButton", takefocus=False, command=self._play_pause)
        self.btn_play.pack(side="left", padx=4)
        ttk.Button(bts, text="⏭", style="Player.TButton", takefocus=False,
                   command=lambda: self._proxima(1)).pack(side="left")
        ttk.Button(bts, text="🗑", style="Player.TButton", takefocus=False,
                   command=self._apagar_tocando).pack(side="left", padx=(12, 0))

        vol = ttk.Frame(p)
        vol.pack(side="left", padx=(8, 0))
        ttk.Label(vol, text="🔊", font=("Segoe UI Symbol", 11)).pack(side="left")
        self.volume = ttk.Scale(vol, from_=0, to=100, orient="horizontal", length=100,
                                command=self._mudar_volume)
        self.volume.set(float(self.cfg.get("volume", 0.8)) * 100)
        self.volume.pack(side="left")
        self.player_frame = p

    def _habilitar(self, sim: bool):
        estado = "normal" if sim else "disabled"
        self.btn_baixar.configure(state=estado)
        self.btn_colar.configure(state=estado)

    # ======================================================== pedidos
    def _enfileirar(self, tipo: str, carga):
        nome_pl = self.playlist.get().strip()
        if nome_pl != self.cfg["playlist_itunes"]:
            self.cfg["playlist_itunes"] = nome_pl
            config.salvar(self.cfg)
        ocupado = self.motor.trabalhando
        self.motor.trabalhos.put((tipo, carga, nome_pl, self.prox_lote))
        self.prox_lote += 1
        if ocupado:
            self._log("Colocado na fila: começa quando o anterior terminar.")
        self.abas.select(0)

    def _mudar_paralelos(self):
        n = int(self.paralelos.get())
        self.motor.definir_paralelos(n)
        self.cfg["downloads_simultaneos"] = n
        config.salvar(self.cfg)
        aviso = "  (mais que 4 aumenta a chance do YouTube bloquear por um tempo)" if n > 4 else ""
        self._log(f"Downloads ao mesmo tempo: {n}{aviso}")

    def _colar(self):
        try:
            texto = self.clipboard_get().strip()
        except tk.TclError:
            texto = ""
        self.link.delete(0, "end")
        self.link.insert(0, texto)
        self._baixar()

    def _baixar(self):
        url = self.link.get().strip()
        if not url:
            return
        if not url.startswith("http") or ("youtu" not in url):
            messagebox.showwarning("Link", "Cole um link do YouTube ou do YouTube Music.")
            return
        playlist = eh_playlist(url)
        if tem_video_e_playlist(url):
            r = messagebox.askyesnocancel(
                "Música ou playlist?",
                "Esse link é de uma música que está dentro de uma playlist/mix.\n\n"
                "Sim = baixar a playlist inteira\nNão = baixar só esta música")
            if r is None:
                return
            playlist = r
        self._enfileirar("link", (url, playlist))
        self.link.delete(0, "end")

    def _tentar_de_novo(self, vids: list[str] | None = None, forcar: bool = False):
        validos = (APAGADA,) if forcar else REPETIVEIS
        if vids is None:
            vids = [v for v, d in self.linhas.items() if d["status"] in validos]
        else:
            vids = [v for v in vids if self.linhas.get(v, {}).get("status") in validos]
        if not vids:
            self._log("Nenhuma música com erro ou cancelada pra tentar de novo.")
            return
        itens = [{"id": v, "titulo": self.linhas[v]["titulo"], "artista": self.linhas[v]["artista"],
                  "forcar": forcar} for v in vids]
        for v in vids:
            self._linha(v, {"status": FILA, "info": ""})
        self._log(("Baixando de novo" if forcar else "Tentando de novo") + f" {len(itens)} música(s).")
        self._enfileirar("itens", itens)

    def _parar(self):
        if not self.motor.trabalhando:
            return
        self.motor.parar_tudo(self.prox_lote - 1)
        self.status.set("Parando…")
        self._log("Parando… (o que faltava fica como 'cancelada'; dá pra usar 'Tentar de novo')")

    def _limpar(self):
        pendentes = [v for v, d in self.linhas.items() if d["status"] not in (PRONTA, REVISAR, REPETIDA)]
        if pendentes and self.motor.trabalhando and not messagebox.askyesno(
                "Limpar lista", f"{len(pendentes)} música(s) ainda não foram baixadas.\n"
                "Elas vão ser paradas e tiradas da lista. Continuar?"):
            return
        self.motor.parar_tudo(self.prox_lote - 1)
        self.lote_minimo = self.prox_lote
        self.fila.delete(*self.fila.get_children())
        self.linhas.clear()
        self.marcadas_fila.clear()
        self._cabecalhos()
        self.status.set("Lista limpa. As músicas já baixadas continuam na aba Baixadas.")

    # ========================================================== ações
    def _abrir_pasta(self):
        pasta = Path(self.cfg["pasta_musicas"])
        pasta.mkdir(parents=True, exist_ok=True)
        os.startfile(pasta)

    def _editar_selecionada(self, arvore: ttk.Treeview):
        sel = arvore.selection()
        if sel:
            self._editar(sel[0])

    def _editar(self, vid: str):
        reg = self.motor.hist.video(vid) if self.motor.hist else None
        if not reg:
            messagebox.showinfo("Corrigir dados", "Só dá pra corrigir músicas que já foram baixadas "
                                                  "(e cujo arquivo ainda existe).")
            return
        if self.dialogo:
            self.dialogo.destroy()
        self.dialogo = Editor(self, vid, reg)

    def _mostrar_arquivo(self, vid: str):
        reg = self.motor.hist.video(vid) if self.motor.hist else None
        if reg:
            subprocess.Popen(f'explorer /select,"{reg["arquivo"]}"')
        else:
            messagebox.showinfo("Arquivo", "O arquivo dessa música não foi encontrado.")

    def _apagar(self, vids: list[str]):
        if not vids or not self.motor.hist:
            return
        regs = [(v, self.motor.hist.d["videos"].get(v)) for v in vids]
        regs = [(v, r) for v, r in regs if r]
        if not regs:
            return
        nomes = "\n".join(f"• {r['artista']} - {r['titulo']}" for _, r in regs[:12])
        if len(regs) > 12:
            nomes += f"\n… e mais {len(regs) - 12}"
        if not messagebox.askyesno(
                "Apagar de vez",
                f"Apagar {len(regs)} música(s)?\n\n{nomes}\n\n"
                "O arquivo é apagado de vez (sem Lixeira) e a música sai do iTunes.\n"
                "Do iPod ela sai na próxima sincronização.\n\nIsso não pode ser desfeito.",
                icon="warning"):
            return
        apagar = [v for v, _ in regs]
        if self.tocando_vid in apagar and self.player:
            self.player.parar()
            self._mostrar_tocando(None)
        self.marcadas -= set(apagar)
        self.motor.urgente.put(("apagar", apagar))
        self._log(f"Apagando {len(apagar)} música(s)…")

    def _limpar_sumidas(self):
        if not self.motor.hist:
            return
        sumidas = [r for _, r in self.motor.hist.todos() if not r["existe"]]
        if not sumidas:
            messagebox.showinfo("Limpar", "Nenhuma música com arquivo não encontrado.")
            return
        nomes = "\n".join(f"• {r['artista']} - {r['titulo']}" for r in sumidas[:10])
        if len(sumidas) > 10:
            nomes += f"\n… e mais {len(sumidas) - 10}"
        if messagebox.askyesno(
                "Limpar não encontradas",
                f"{len(sumidas)} música(s) estão sem o arquivo no PC:\n\n{nomes}\n\n"
                "Elas vão sair desta lista e do iTunes (onde estão com '!'), "
                "e poderão ser baixadas de novo. Continuar?"):
            self.motor.urgente.put(("remover_sumidas",))

    def _menu(self, evento, arvore: ttk.Treeview, opcoes):
        iid = arvore.identify_row(evento.y)
        if not iid:
            return
        if iid not in arvore.selection():
            arvore.selection_set(iid)
        sel = list(arvore.selection())
        menu = tk.Menu(self, tearoff=0)
        for item in opcoes(sel):
            if item is None:
                menu.add_separator()
                continue
            texto, acao, ativo = item
            menu.add_command(label=texto, command=acao, state="normal" if ativo else "disabled")
        menu.tk_popup(evento.x_root, evento.y_root)

    def _menu_fila(self, evento):
        def opcoes(sel):
            um = sel[0]
            status = [self.linhas.get(v, {}).get("status") for v in sel]
            itens = [
                ("↻ Tentar de novo", lambda: self._tentar_de_novo(sel), any(s in REPETIVEIS for s in status)),
            ]
            if APAGADA in status:
                itens.append(("⬇ Baixar mesmo assim", lambda: self._tentar_de_novo(sel, forcar=True), True))
            return itens + [
                (f"🎵 Mudar gênero ({len(sel)})…", lambda: self._mudar_genero(sel, self.fila), True),
                ("Corrigir dados…", lambda: self._editar(um), len(sel) == 1),
                ("Mostrar o arquivo na pasta", lambda: self._mostrar_arquivo(um), len(sel) == 1),
                ("Abrir no YouTube", lambda: webbrowser.open(link_video(um)), len(sel) == 1),
            ]
        self._menu(evento, self.fila, opcoes)

    def _menu_baixadas(self, evento):
        def opcoes(sel):
            um = sel[0]
            return [
                ("▶ Tocar", lambda: self._tocar(um), len(sel) == 1),
                (f"🎵 Mudar gênero ({len(sel)})…", lambda: self._mudar_genero(sel, self.baixadas), True),
                ("Corrigir dados…", lambda: self._editar(um), len(sel) == 1),
                ("Mostrar o arquivo na pasta", lambda: self._mostrar_arquivo(um), len(sel) == 1),
                ("Abrir no YouTube", lambda: webbrowser.open(link_video(um)), len(sel) == 1),
                None,
                (f"🗑 Apagar ({len(sel)})…", lambda: self._apagar(sel), True),
            ]
        self._menu(evento, self.baixadas, opcoes)

    def _fechar(self):
        if self.motor.trabalhando and not messagebox.askyesno(
                "Sair", "Ainda tem música baixando. Sair mesmo assim?\n"
                "(o que já terminou fica salvo; o resto você manda de novo depois)"):
            return
        if self.player:
            self.player.parar()
        if self.receptor:
            self.receptor.fechar()
        self.cfg["volume"] = round(self.volume.get() / 100, 2)
        config.salvar(self.cfg)
        self.destroy()

    # ======================================================= baixadas
    def _agendar_baixadas(self):
        if not self._atualizar_agendado:
            self._atualizar_agendado = True
            self.after(600, self._mostrar_baixadas)

    def _trocar_filtro(self, _e=None):
        i = self.combo.current()
        if 0 <= i < len(self._filtros):
            self.filtro_atual = self._filtros[i]
        self._mostrar_baixadas()

    def _ordenar(self, coluna: str):
        if self.ordem_col == coluna:
            self.ordem_desc = not self.ordem_desc
        else:
            self.ordem_col, self.ordem_desc = coluna, coluna == "data"
        self._mostrar_baixadas()

    def _cabecalhos(self):
        for chave, nome, _l in COLUNAS_BAIXADAS:
            if chave != "sel":
                seta = (" ▼" if self.ordem_desc else " ▲") if chave == self.ordem_col else ""
                self.baixadas.heading(chave, text=nome + seta)
        for arvore in (self.baixadas, self.fila):
            marcas, visiveis = self._marcas(arvore), arvore.get_children()
            tudo = bool(visiveis) and all(v in marcas for v in visiveis)
            arvore.heading("sel", text="☑" if tudo else "☐")
        n, nf = len(self.marcadas), len(self.marcadas_fila)
        self.btn_apagar.configure(text=f"🗑 Apagar marcadas ({n})", state="normal" if n else "disabled")
        self.btn_genero_bx.configure(text=f"🎵 Mudar gênero ({n})…", state="normal" if n else "disabled")
        self.btn_genero_fila.configure(text=f"🎵 Mudar gênero ({nf})…", state="normal" if nf else "disabled")

    def _passa_filtro(self, r: dict) -> bool:
        f = self.filtro_atual
        if f == "nao_achou":
            return nao_achou(r)
        if f == "revisar":
            return bool(r.get("revisar"))
        if f.startswith("g:"):
            return (r.get("genero") or SEM_GENERO) == f[2:]
        return True

    def _mostrar_baixadas(self):
        self._atualizar_agendado = False
        if not self.motor.hist:
            return
        todos = self.motor.hist.todos()
        existentes = {v for v, _ in todos}
        self.marcadas &= existentes

        # ---- opções do menu "Mostrar" com contagens
        generos = Counter(r.get("genero") or SEM_GENERO for _, r in todos)
        opcoes = [("todas", f"Todas ({len(todos)})"),
                  ("nao_achou", f"Não achou no iTunes ({sum(nao_achou(r) for _, r in todos)})"),
                  ("revisar", f"Precisa revisar ({sum(bool(r.get('revisar')) for _, r in todos)})")]
        opcoes += [(f"g:{g}", f"{g} ({n})") for g, n in sorted(generos.items(), key=lambda x: (-x[1], x[0]))]
        self._filtros = [k for k, _ in opcoes]
        if self.filtro_atual not in self._filtros:
            self.filtro_atual = "todas"
        self.combo.configure(values=[t for _, t in opcoes])
        self.combo.current(self._filtros.index(self.filtro_atual))

        # ---- filtro, busca e ordem
        busca = norm(self.busca.get())
        lista = [(v, r) for v, r in todos if self._passa_filtro(r) and (
            not busca or busca in norm(" ".join(str(r.get(k, "")) for k in ("titulo", "artista", "genero", "ano"))))]
        lista.sort(key=lambda x: x[1].get("data", ""), reverse=True)  # desempate: mais recentes
        col = self.ordem_col
        if col != "data":
            def chave(item):
                r = item[1]
                if col == "ano":
                    return int(r.get("ano") or 0) if str(r.get("ano") or "").isdigit() else 0
                if col == "situacao":
                    return situacao(r)[0]
                return norm(str(r.get(col, "")))
            lista.sort(key=chave, reverse=self.ordem_desc)
        elif not self.ordem_desc:
            lista.reverse()

        # ---- redesenha mantendo seleção e rolagem
        selecao = set(self.baixadas.selection())
        topo = self.baixadas.yview()[0]
        self.baixadas.delete(*self.baixadas.get_children())
        self._tags_base.clear()
        for vid, r in lista:
            texto, tag = situacao(r)
            base = (tag,) if tag else ()
            self._tags_base[vid] = base
            tags = base + (("tocando",) if vid == self.tocando_vid else ())
            self.baixadas.insert("", "end", iid=vid, tags=tags, values=(
                "☑" if vid in self.marcadas else "☐", r.get("titulo", ""), r.get("artista", ""),
                r.get("genero", ""), r.get("ano", ""), r.get("data", "").replace("T", " ")[:16], texto))
        manter = [v for v in selecao if self.baixadas.exists(v)]
        if manter:
            self.baixadas.selection_set(manter)
        self.baixadas.yview_moveto(topo)

        self.abas.tab(self.aba_bx, text=f"Baixadas ({len(todos)})")
        self.contagem.configure(text=f"{len(lista)} de {len(todos)} músicas")
        self._cabecalhos()
        if self.tocando_vid:
            self._mostrar_tocando(self.tocando_vid, recarregar_capa=False)

    # ---------------------------------------------- caixinhas (as duas abas)
    def _marcas(self, arvore) -> set[str]:
        return self.marcadas_fila if arvore is self.fila else self.marcadas

    def _clique_caixa(self, arvore, e):
        if arvore.identify_region(e.x, e.y) == "cell" and arvore.identify_column(e.x) == "#1":
            vid = arvore.identify_row(e.y)
            if vid:
                marcas = self._marcas(arvore)
                marcas.symmetric_difference_update({vid})
                arvore.set(vid, "sel", "☑" if vid in marcas else "☐")
                self._cabecalhos()
            return "break"
        return None

    def _marcar_visiveis(self, arvore):
        marcas, visiveis = self._marcas(arvore), arvore.get_children()
        if visiveis and all(v in marcas for v in visiveis):
            marcas -= set(visiveis)
        else:
            marcas |= set(visiveis)
        for v in visiveis:
            arvore.set(v, "sel", "☑" if v in marcas else "☐")
        self._cabecalhos()

    def _desmarcar(self, arvore, vids):
        marcas = self._marcas(arvore)
        for v in vids:
            marcas.discard(v)
            if arvore.exists(v):
                arvore.set(v, "sel", "☐")
        self._cabecalhos()

    def _duplo_fila(self, e):
        if self.fila.identify_column(e.x) != "#1":
            self._editar_selecionada(self.fila)
        return "break"

    # -------------------------------------------------- mudar gênero
    def _generos_conhecidos(self) -> list[str]:
        cont = Counter()
        if self.motor.hist:
            cont.update(r.get("genero") for _, r in self.motor.hist.todos() if r.get("genero"))
        cont.update(d.get("genero") for d in self.linhas.values() if d.get("genero"))
        return [g for g, _ in cont.most_common()]

    def _mudar_genero(self, vids: list[str], arvore):
        if not vids or not self.motor.hist:
            return
        musicas = []
        for v in vids:
            r = self.motor.hist.d["videos"].get(v) or self.linhas.get(v) or {}
            musicas.append((v, r.get("titulo") or v, r.get("artista", ""), r.get("genero", ""),
                            v in self.motor.hist.d["videos"]))
        MudarGenero(self, musicas, arvore)

    def _aplicar_genero(self, vids: list[str], genero: str, arvore):
        if self.tocando_vid in vids and self.player:  # o arquivo tocando fica bloqueado
            self.player.parar()
            self._mostrar_tocando(None)
        for v in vids:
            if v in self.linhas:
                self._linha(v, {"genero": genero})
        self._desmarcar(arvore, vids)
        self.motor.urgente.put(("mudar_genero", list(vids), genero))
        self._log(f"Mudando o gênero de {len(vids)} música(s) para “{genero}”…")

    def _duplo_baixadas(self, e):
        if self.baixadas.identify_column(e.x) == "#1":
            return "break"
        vid = self.baixadas.identify_row(e.y)
        if vid:
            self._tocar(vid)
        return "break"

    # ========================================================= player
    def _iniciar_player(self):
        try:
            from musicas.player import Player
            self.player = Player(volume=float(self.cfg.get("volume", 0.8)))
        except Exception as e:  # noqa: BLE001
            self.player = None
            self.lbl_musica.configure(text="Player indisponível")
            self.lbl_artista.configure(text=str(e)[:120])
            self._log(f"⚠ Player indisponível: {e}")

    def _tocar_selecionada(self):
        sel = self.baixadas.selection()
        vid = sel[0] if sel else (self.baixadas.get_children() or [None])[0]
        if vid:
            self._tocar(vid)

    def _tocar(self, vid: str):
        if not self.player:
            return
        reg = self.motor.hist.video(vid) if self.motor.hist else None
        if not reg:
            messagebox.showinfo("Tocar", "O arquivo dessa música não foi encontrado.")
            return
        try:
            self.player.tocar(reg["arquivo"])
        except Exception as e:  # noqa: BLE001
            self._log(f"Não consegui tocar: {e}")
            return
        self._lista_tocar = list(self.baixadas.get_children())
        self._mostrar_tocando(vid)

    def _mostrar_tocando(self, vid: str | None, recarregar_capa: bool = True):
        antigo, self.tocando_vid = self.tocando_vid, vid
        for v in (antigo, vid):
            if v and self.baixadas.exists(v):
                extra = ("tocando",) if v == vid else ()
                self.baixadas.item(v, tags=self._tags_base.get(v, ()) + extra)
        if not vid:
            self.lbl_musica.configure(text="Nada tocando")
            self.lbl_artista.configure(text="Dois cliques numa música pra tocar")
            self.capa.configure(image="")
            self._capa_img = None
            self.lbl_tempo.configure(text="0:00 / 0:00")
            self.barra_tempo.set(0)
            return
        reg = self.motor.hist.d["videos"].get(vid, {})
        self.lbl_musica.configure(text=reg.get("titulo", ""))
        extra = " · ".join(x for x in (reg.get("genero"), reg.get("ano")) if x)
        self.lbl_artista.configure(text=reg.get("artista", "") + (f"   ({extra})" if extra else ""))
        if recarregar_capa:
            self._carregar_capa(reg.get("arquivo", ""))

    def _carregar_capa(self, arquivo: str):
        self._capa_img = None
        try:
            from mutagen.mp4 import MP4
            from PIL import Image, ImageTk
            tags = MP4(arquivo).tags
            if tags and "covr" in tags:
                img = Image.open(io.BytesIO(bytes(tags["covr"][0]))).convert("RGB")
                img.thumbnail((64, 64))
                self._capa_img = ImageTk.PhotoImage(img)
        except Exception:  # noqa: BLE001
            self._capa_img = None
        self.capa.configure(image=self._capa_img or "")

    def _vizinha(self, passo: int) -> str | None:
        lista = list(self.baixadas.get_children())
        if self.tocando_vid not in lista:
            lista = self._lista_tocar
        if not lista:
            return None
        i = lista.index(self.tocando_vid) if self.tocando_vid in lista else -1
        for j in range(1, len(lista) + 1):
            k = i + passo * j
            if not 0 <= k < len(lista):
                return None
            if self.motor.hist.video(lista[k]):
                return lista[k]
        return None

    def _proxima(self, passo: int = 1):
        if not self.player:
            return
        vid = self._vizinha(passo)
        if vid:
            self._tocar(vid)
        elif passo > 0:
            self.player.parar()
            self._mostrar_tocando(None)

    def _atalho(self, acao):
        def tecla(e):
            w = e.widget
            try:
                if w.winfo_toplevel() is not self:  # janelas de editar/mudar gênero
                    return None
            except (AttributeError, tk.TclError):
                return None
            # digitando, ou mexendo no volume/barra de tempo: a tecla é do campo
            if isinstance(w, (tk.Entry, ttk.Entry, tk.Text, tk.Listbox, ttk.Scale, tk.Scale)):
                return None
            if self.abas.index(self.abas.select()) != 1:  # só na aba Baixadas
                return None
            acao()
            return "break"
        return tecla

    def _pular_pro_meio(self):
        if self.player and self.player.arquivo:
            dur = self.player.duracao()
            if dur:
                self.player.pular_para(dur / 2)

    def _apagar_tocando(self):
        """Apaga de vez a música que está tocando (sem perguntar) e já toca a próxima."""
        vid = self.tocando_vid
        if not vid or not self.player or not self.motor.hist:
            return
        reg = self.motor.hist.d["videos"].get(vid, {})
        proxima = self._vizinha(1)
        self.player.parar()  # solta o arquivo antes de apagar
        self.marcadas.discard(vid)
        self.motor.urgente.put(("apagar", [vid]))
        self._log(f"🗑 Apagando: {reg.get('artista', '')} - {reg.get('titulo', '')}")
        if proxima:
            self._tocar(proxima)
        else:
            self._mostrar_tocando(None)

    def _anterior(self):
        if self.player and self.player.arquivo and self.player.posicao() > 3:
            self.player.pular_para(0)
        else:
            self._proxima(-1)

    def _play_pause(self):
        if not self.player:
            return
        if self.player.arquivo:
            self.player.alternar()
        else:
            self._tocar_selecionada()

    def _soltar_barra(self, _e):
        self._arrastando = False
        if self.player and self.player.arquivo:
            dur = self.player.duracao()
            if dur:
                self.player.pular_para(self.barra_tempo.get() / 1000 * dur)

    def _mudar_volume(self, valor):
        if self.player:
            self.player.volume = float(valor) / 100

    def _tick_player(self):
        try:
            if self.player:
                if self.player.terminou():
                    self._proxima(1)
                tocando = self.player.tocando()
                self.btn_play.configure(text="⏸" if tocando else "▶")
                if self.player.arquivo:
                    pos, dur = self.player.posicao(), self.player.duracao()
                    self.lbl_tempo.configure(text=f"{tempo(pos)} / {tempo(dur)}")
                    if dur and not self._arrastando:
                        self.barra_tempo.set(pos / dur * 1000)
        except Exception:  # noqa: BLE001
            pass
        self.after(250, self._tick_player)

    # ============================================ extensão do Chrome
    _ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

    def _pedido_extensao(self, msg: dict) -> dict:
        """Roda na thread do receptor; o que mexe na tela vai pela fila de eventos."""
        acao = msg.get("acao")
        if acao == "ping":
            return {"ok": True}
        if acao == "mostrar":
            self.ev.put(("mostrar",))
            return {"ok": True}
        if acao == "verificar":
            hist = self.motor.hist or Historico(config.DADOS / "historico.json")
            return {"ok": True, "status": hist.status(list(msg.get("ids", [])))}
        if acao == "enviar":
            itens, vistos = [], set()
            for it in msg.get("itens", [])[:1000]:
                vid = str(it.get("id", ""))
                if self._ID.match(vid) and vid not in vistos:
                    vistos.add(vid)
                    itens.append({"id": vid, "titulo": str(it.get("titulo", ""))[:300],
                                  "artista": str(it.get("artista", ""))[:200]})
            if not itens:
                return {"ok": False, "erro": "nenhuma música válida"}
            self.ev.put(("receber", itens, str(msg.get("origem", ""))[:200]))
            return {"ok": True, "n": len(itens)}
        return {"ok": False, "erro": "ação desconhecida"}

    def _trazer_pra_frente(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # ======================================================== eventos
    def _log(self, msg: str):
        self.registro.configure(state="normal")
        self.registro.insert("end", msg + "\n")
        self.registro.see("end")
        self.registro.configure(state="disabled")

    def _eventos(self):
        try:
            for _ in range(200):
                tipo, *args = self.ev.get_nowait()
                if tipo == "log":
                    self._log(args[0])
                elif tipo == "status":
                    self.status.set(args[0])
                elif tipo == "pronto_para_uso":
                    self._habilitar(args[0])
                    self._mostrar_baixadas()
                elif tipo == "linha":
                    vid, campos, lote = args
                    if lote is None:  # edição: só atualiza se a música está na lista
                        if vid in self.linhas:
                            self._linha(vid, campos)
                    elif lote >= self.lote_minimo:
                        self._linha(vid, campos)
                elif tipo == "baixada":
                    self._agendar_baixadas()
                elif tipo == "mostrar":
                    self._trazer_pra_frente()
                elif tipo == "receber":
                    itens, origem = args
                    self._log(f"Recebidas {len(itens)} música(s) do Chrome" + (f" ({origem})" if origem else "") + ".")
                    self._enfileirar("itens", itens)
                    self._trazer_pra_frente()
                elif tipo == "candidatos" and self.dialogo and self.dialogo.vid == args[0]:
                    self.dialogo.mostrar_candidatos(args[1])
        except queue.Empty:
            pass
        self.after(100, self._eventos)

    def _linha(self, vid: str, campos: dict):
        dados = self.linhas.setdefault(vid, {c[0]: "" for c in COLUNAS_FILA})
        dados.update({k: v for k, v in campos.items() if v is not None})
        dados["sel"] = "☑" if vid in self.marcadas_fila else "☐"
        valores = [dados[c[0]] for c in COLUNAS_FILA]
        tag = (dados["status"],) if dados["status"] in CORES else ()
        if self.fila.exists(vid):
            self.fila.item(vid, values=valores, tags=tag)
        else:
            self.fila.insert("", "end", iid=vid, values=valores, tags=tag)
        if campos.get("status") == BAIXANDO:
            self.fila.see(vid)


class MudarGenero(tk.Toplevel):
    """Escolhe um gênero e aplica em várias músicas de uma vez."""

    def __init__(self, app: App, musicas: list[tuple], arvore):
        super().__init__(app)
        self.app, self.arvore = app, arvore
        self.vids = [m[0] for m in musicas]
        self.title("Mudar gênero")
        self.geometry("560x460")
        self.transient(app)
        self.grab_set()

        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"Mudar o gênero de {len(musicas)} música(s) para:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.genero = ttk.Combobox(f, values=app._generos_conhecidos(), font=("Segoe UI", 11))
        self.genero.pack(fill="x", pady=(6, 2), ipady=2)
        atuais = {m[3] for m in musicas if m[3]}
        if len(atuais) == 1:
            self.genero.set(next(iter(atuais)))
            self.genero.select_range(0, "end")
        self.genero.focus_set()
        self.genero.bind("<Return>", lambda _: self._aplicar())
        ttk.Label(f, text="Escolha um da lista ou digite um novo.", foreground="#666").pack(anchor="w")

        lista = tk.Listbox(f, height=12, activestyle="none")
        lista.pack(fill="both", expand=True, pady=10)
        pendentes = 0
        for _v, titulo, artista, genero, baixada in musicas:
            if not baixada:
                pendentes += 1
            extra = f"  [{genero}]" if genero else ""
            lista.insert("end", f"{titulo} — {artista}{extra}" + ("" if baixada else "   (ainda na fila)"))
        if pendentes:
            ttk.Label(f, text=f"{pendentes} ainda não terminaram de baixar: o gênero entra quando terminarem.",
                      foreground="#b85c00").pack(anchor="w")

        bts = ttk.Frame(f)
        bts.pack(fill="x", pady=(10, 0))
        ttk.Button(bts, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(bts, text="Aplicar", command=self._aplicar).pack(side="right", padx=6)

    def _aplicar(self):
        genero = self.genero.get().strip()
        if not genero:
            messagebox.showwarning("Mudar gênero", "Escolha ou digite um gênero.", parent=self)
            return
        self.app._aplicar_genero(self.vids, genero, self.arvore)
        self.destroy()


class Editor(tk.Toplevel):
    """Janela pra corrigir título/artista/gênero/ano ou escolher outro resultado do iTunes."""

    def __init__(self, app: App, vid: str, dados: dict):
        super().__init__(app)
        self.app, self.vid = app, vid
        self.title("Corrigir dados")
        self.geometry("640x470")
        self.transient(app)
        self.candidatos: list[Meta] = []
        self.capa_url = ""
        self.itunes_id = None

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.vars = {}
        for i, (chave, nome) in enumerate((("titulo", "Música"), ("artista", "Artista"),
                                            ("genero", "Gênero"), ("ano", "Ano"))):
            ttk.Label(f, text=nome + ":").grid(row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=dados.get(chave, ""))
            ttk.Entry(f, textvariable=v, width=60).grid(row=i, column=1, sticky="we", pady=3)
            self.vars[chave] = v
        f.columnconfigure(1, weight=1)

        ttk.Separator(f).grid(row=4, column=0, columnspan=2, sticky="we", pady=10)
        ttk.Label(f, text="Procurar no iTunes:").grid(row=5, column=0, sticky="w")
        busca = ttk.Frame(f)
        busca.grid(row=5, column=1, sticky="we")
        self.termo = tk.StringVar(value=f"{dados.get('artista', '')} {dados.get('titulo', '')}".strip())
        e = ttk.Entry(busca, textvariable=self.termo)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _: self._buscar())
        ttk.Button(busca, text="Buscar", command=self._buscar).pack(side="left", padx=(6, 0))

        self.res = tk.Listbox(f, height=9, activestyle="none")
        self.res.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=6)
        self.res.bind("<<ListboxSelect>>", self._escolher)
        f.rowconfigure(6, weight=1)
        self.aviso = ttk.Label(f, text="Clique num resultado pra usar os dados e a capa dele.", foreground="#666")
        self.aviso.grid(row=7, column=0, columnspan=2, sticky="w")

        bts = ttk.Frame(f)
        bts.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(bts, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(bts, text="Salvar", command=self._salvar).pack(side="right", padx=6)

    def destroy(self):
        if self.app.dialogo is self:
            self.app.dialogo = None
        super().destroy()

    def _buscar(self):
        termo = self.termo.get().strip()
        if termo:
            self.res.delete(0, "end")
            self.res.insert("end", "Buscando…")
            self.app.motor.urgente.put(("buscar", self.vid, termo))

    def mostrar_candidatos(self, metas: list[Meta]):
        self.candidatos = metas
        self.res.delete(0, "end")
        for m in metas:
            self.res.insert("end", m.resumo())
        if not metas:
            self.res.insert("end", "Nada encontrado. Tente outro termo ou preencha na mão.")

    def _escolher(self, _e=None):
        sel = self.res.curselection()
        if not sel or sel[0] >= len(self.candidatos):
            return
        m = self.candidatos[sel[0]]
        for chave in ("titulo", "artista", "genero", "ano"):
            self.vars[chave].set(getattr(m, chave))
        self.capa_url, self.itunes_id = m.capa_url, m.itunes_id
        self.aviso.configure(text="Capa do iTunes será usada.")

    def _salvar(self):
        v = {k: x.get().strip() for k, x in self.vars.items()}
        if not v["titulo"] or not v["artista"]:
            messagebox.showwarning("Corrigir", "Preencha pelo menos música e artista.", parent=self)
            return
        meta = Meta(titulo=v["titulo"], artista=v["artista"], genero=v["genero"], ano=v["ano"],
                    capa_url=self.capa_url, itunes_id=self.itunes_id, fonte="editado")
        self.app.motor.urgente.put(("editar", self.vid, meta))
        self.destroy()


if __name__ == "__main__":
    # já está aberto? só traz a janela pra frente
    if (servidor.chamar({"acao": "mostrar"}, timeout=2) or {}).get("ok"):
        sys.exit(0)
    App().mainloop()
