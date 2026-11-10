# Organized YouTube Music Downloads for iPod

🇺🇸 [English](#english) · 🇧🇷 [Português](#português)

---

## English

### What it is
A Windows desktop app (plus a Chrome extension) that downloads music from **YouTube** and **YouTube Music** and drops it into **iTunes** fully organized, ready to sync to a classic **iPod** — or an **iPhone**, synced through iTunes (see [Using with iPhone](#using-with-iphone)).

### Why it exists
Songs downloaded from YouTube usually come with messy data: titles like *"Artist - Song (Official Music Video) [4K]"*, no real artist, no genre, no year, and a wide video thumbnail as the cover. On an iPod that turns into an unsorted pile that's hard to browse by artist or genre.

This app fixes that automatically. It downloads, looks the song up in Apple's iTunes catalog, writes the right metadata into the file and adds it to your iTunes library. So your iPod library stays clean without editing tags by hand.

### What it does
- **Downloads** a single song, a whole playlist or a mix (up to 500 songs), several at the same time, in **M4A/AAC** with no re-encoding (plays natively on the iPod).
- **Fixes the metadata** through the iTunes catalog: title, artist, **genre**, year and a square high-res **cover**. Album is left blank on purpose, since most current artists release singles.
- **Adds the songs to iTunes** automatically (into a playlist of your choice), so you just sync the iPod.
- **Avoids duplicates**: the same video, the same song from a different video (official clip × lyric video), or a song already in your library.
- **Remembers what you deleted**, so it isn't downloaded again the next time it shows up in a mix.
- **Library view** with a built-in player, filters by genre or by "not found in iTunes", quick fixes, bulk genre changes and deletion (from disk and iTunes).
- **Chrome extension**: a "→ iPod" button inside YouTube and YouTube Music that sends a song, a playlist or your personal mixes straight to the app, with a checklist to review before sending.

### Requirements
- **Windows 10 or 11** (64-bit)
- **[iTunes](https://apps.microsoft.com/detail/9pb2mz1zmb1s)** — required. The app puts the songs into iTunes and the iPod is synced through it. (The Microsoft Store version or Apple's classic installer both work.)
- Google Chrome — only for the optional extension

Everything else (Python, yt-dlp, FFmpeg, Deno) comes inside the installer.

### Installation
1. Download **`Organized-YouTube-Music-Downloads-for-iPod-Setup-x.y.z.exe`** from the [Releases](../../releases/latest) page and run it (no admin rights needed).
2. *(Optional)* Chrome extension: open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the `extensao` folder inside the install folder (Start Menu → *Chrome extension folder*).

### Using with iPhone
The songs are standard M4A/AAC files with full tags, so they play on the iPhone too. You sync them through **iTunes**, just like an iPod: connect the iPhone (cable or Wi-Fi sync), open its page in iTunes → **Music** → sync the library or the chosen playlist.

- On the iPhone, **Settings → Music → Sync Library** must be **off**. With it on (common with an Apple Music subscription), iTunes doesn't allow syncing music by cable. If you subscribe to Apple Music and prefer keeping it on, iTunes uploads your library to iCloud instead and the songs show up on the iPhone without a cable.
- **Don't install the "Apple Music" app for Windows.** It takes over the music library from iTunes, and this app (and iPod syncing) stops working.
- In the iPhone's Music app, browsing by genre is under Library → **Edit** → **Genres**. Since the album is left blank, the songs show up under "Songs" and on each artist's page.

### Built with
Python · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [FFmpeg](https://ffmpeg.org/) · iTunes Search API · iTunes for Windows (COM) · [Mutagen](https://github.com/quodlibet/mutagen) · Chrome Extension (Manifest V3 + Native Messaging)

### License
[GPL-3.0](LICENSE). The installer also bundles third-party software under their own licenses (see the `licencas` folder after installing).

> Personal project. Respect the YouTube Terms of Service and the rights of the artists. Download only what you are allowed to.
> Not affiliated with Apple, Google or YouTube. "iPod", "iPhone" and "iTunes" are trademarks of Apple Inc.

---

## Português

### O que é
Um programa para Windows (com uma extensão do Chrome) que baixa músicas do **YouTube** e do **YouTube Music** e coloca no **iTunes** já organizadas, prontas pra sincronizar com um **iPod** clássico, ou com um **iPhone**, sincronizado pelo iTunes (veja [Usando no iPhone](#usando-no-iphone)).

### Por que existe
Música baixada do YouTube costuma vir com os dados bagunçados. O título vem como *"Artista - Música (Clipe Oficial) [4K]"*, sem artista de verdade, sem gênero, sem ano, e a capa é a miniatura retangular do vídeo. No iPod isso vira uma lista sem ordem, difícil de navegar por artista ou gênero.

O programa resolve isso sozinho. Ele baixa, procura a música no catálogo do iTunes da Apple, grava os dados certos no arquivo e adiciona na biblioteca do iTunes. Assim a biblioteca do iPod fica organizada sem ninguém precisar editar tag por tag.

### O que ele faz
- **Baixa** uma música, uma playlist inteira ou um mix (até 500 músicas), várias ao mesmo tempo, em **M4A/AAC** sem converter (o iPod toca direto).
- **Arruma os dados** pelo catálogo do iTunes: título, artista, **gênero**, ano e **capa** quadrada em alta resolução. O álbum fica em branco de propósito, porque a maioria dos artistas atuais lança singles.
- **Adiciona no iTunes** sozinho (numa playlist que você escolhe). Aí é só sincronizar o iPod.
- **Evita repetidas**: o mesmo vídeo, a mesma música em outro vídeo (clipe × lyric video) ou uma música que já está na biblioteca.
- **Lembra o que você apagou**, pra não baixar de novo quando a música aparecer em outro mix.
- **Tela da biblioteca** com player próprio, filtro por gênero ou por "não achou no iTunes", correção rápida, troca de gênero em várias músicas e apagar (do PC e do iTunes).
- **Extensão do Chrome**: um botão "→ iPod" dentro do YouTube e do YouTube Music que manda uma música, uma playlist ou os seus mixes pessoais direto pro programa, com uma lista pra revisar antes de enviar.

### Requisitos
- **Windows 10 ou 11** (64 bits)
- **[iTunes](https://apps.microsoft.com/detail/9pb2mz1zmb1s)**: obrigatório. O programa coloca as músicas no iTunes e o iPod é sincronizado por ele. (Serve a versão da Microsoft Store ou o instalador clássico da Apple.)
- Google Chrome: só pra extensão, que é opcional

O resto (Python, yt-dlp, FFmpeg, Deno) já vem dentro do instalador.

### Instalação
1. Baixe o **`Organized-YouTube-Music-Downloads-for-iPod-Setup-x.y.z.exe`** na página de [Releases](../../releases/latest) e execute (não precisa de administrador).
2. *(Opcional)* Extensão do Chrome: abra `chrome://extensions`, ligue o **Modo do desenvolvedor**, clique em **Carregar sem compactação** e escolha a pasta `extensao`, que fica dentro da pasta de instalação (Menu Iniciar → *Pasta da extensão do Chrome*).

### Usando no iPhone
As músicas são arquivos M4A/AAC comuns, com todos os dados, então tocam no iPhone também. A sincronização é feita pelo **iTunes**, igual ao iPod: conecte o iPhone (por cabo ou sincronização por Wi-Fi), abra a página dele no iTunes → **Música** → sincronize a biblioteca ou a playlist que quiser.

- No iPhone, **Ajustes → Música → Sincronizar Biblioteca** precisa estar **desligado**. Ligado (comum pra quem assina o Apple Music), o iTunes não deixa passar músicas pelo cabo. Se você assina o Apple Music e prefere deixar ligado, o iTunes envia a sua biblioteca pro iCloud e as músicas aparecem no iPhone sem cabo.
- **Não instale o app "Apple Music" para Windows.** Ele tira a biblioteca de músicas do iTunes, e aí este programa (e a sincronização do iPod) para de funcionar.
- No app Música do iPhone, a lista por gênero fica em Biblioteca → **Editar** → **Gêneros**. Como o álbum fica em branco, as músicas aparecem em "Músicas" e na página de cada artista.

### Feito com
Python · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [FFmpeg](https://ffmpeg.org/) · iTunes Search API · iTunes para Windows (COM) · [Mutagen](https://github.com/quodlibet/mutagen) · Extensão do Chrome (Manifest V3 + Native Messaging)

### Licença
[GPL-3.0](LICENSE). O instalador também traz programas de terceiros, cada um com a sua licença (veja a pasta `licencas` depois de instalar).

> Projeto pessoal. Respeite os Termos de Serviço do YouTube e os direitos dos artistas. Baixe só o que você tem direito.
> Sem vínculo com Apple, Google ou YouTube. "iPod", "iPhone" e "iTunes" são marcas da Apple Inc.
