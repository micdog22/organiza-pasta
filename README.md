# Organiza Pasta: arrume sua pasta de Downloads em segundos (Python)

A pasta de Downloads de todo mundo vira bagunça: boleto, foto, instalador, planilha, PDF de nota fiscal, tudo misturado. O **organiza-pasta** separa os arquivos em subpastas como `Imagens`, `PDFs`, `Vídeos` e `Planilhas` (ou por ano e mês), mostra o plano antes, nunca sobrescreve nada e deixa desfazer tudo com um comando.

Funciona no Windows, macOS e Linux, roda offline e não tem dependências além do Python.

## Recursos

- Doze categorias prontas: Imagens, Vídeos, Áudios, Documentos, PDFs, Planilhas, Apresentações, Compactados, Instaladores, Código, Fontes e Outros, com um mapa completo de extensões (sem diferenciar maiúsculas).
- Organização por tipo (padrão), por data (`AAAA/MM`, pela data de modificação) ou pelos dois (`Imagens/AAAA/MM`).
- **Segura por padrão:** mostra um resumo e pede confirmação; `--simular` mostra o plano completo sem mexer em nada.
- **Nunca sobrescreve:** se já existe `foto.jpg` no destino, o arquivo vira `foto (1).jpg`, como no navegador.
- Ignora arquivos ocultos, downloads em andamento (`.crdownload`, `.part`, `.download`, `.tmp`), temporários do Office (`~$...`), `Thumbs.db`, `desktop.ini` e as próprias pastas de categoria.
- `--desfazer` devolve os arquivos da última organização aos lugares de origem, mesmo que alguns tenham sido apagados ou renomeados depois.
- Regras personalizadas com um JSON simples (`--config`).
- `--recursivo` para organizar também as subpastas, sem entrar nas pastas de destino (categorias e anos, como `2024`), em apps do macOS (`.app`) nem em projetos com `.git`.

## Instalação

```bash
pipx install git+https://github.com/micdog22/organiza-pasta
# ou
pip install git+https://github.com/micdog22/organiza-pasta
```

Requer Python 3.9 ou mais novo.

## Como usar

Veja primeiro o que vai acontecer:

```console
$ organiza-pasta ~/Downloads --simular
Pasta: ~/Downloads  (organização por tipo)
Ignorados: 2 (download incompleto ou temporário: 1, oculto: 1)

  Apresentações      1 arquivo      4,6 MB
  Áudios             1 arquivo     29,6 MB
  Compactados        1 arquivo     49,6 MB
  Documentos        2 arquivos    255,9 KB
  Fontes             1 arquivo    156,2 KB
  Imagens           3 arquivos      6,6 MB
  Instaladores       1 arquivo     93,5 MB
  Outros             1 arquivo  1.000 bytes
  PDFs              2 arquivos    200,2 KB
  Planilhas          1 arquivo      8,8 KB
  Vídeos             1 arquivo    171,7 MB

Total: 15 arquivos (356,1 MB) em 11 pastas.

  apresentacao-cliente.pptx -> Apresentações/apresentacao-cliente.pptx
  boleto-condominio.pdf -> PDFs/boleto-condominio.pdf
  extrato-maio.csv -> Planilhas/extrato-maio.csv
  IMG_20240512_101500.jpg -> Imagens/IMG_20240512_101500.jpg
  ...
  .DS_Store (ignorado: oculto)
  filme.mkv.crdownload (ignorado: download incompleto ou temporário)

Simulação: nenhum arquivo foi movido.
```

Gostou? Rode sem o `--simular` e confirme:

```console
$ organiza-pasta ~/Downloads
...
Mover 15 arquivos? [s/N] s
Pronto: 15 arquivos movidos.
Para desfazer: organiza-pasta ~/Downloads --desfazer
```

Mudou de ideia? Desfaça:

```console
$ organiza-pasta ~/Downloads --desfazer
Última organização em ~/Downloads: 08/10/2026 às 14:30 (15 arquivos, por tipo)
Devolver os arquivos aos lugares de origem? [s/N] s
15 arquivos devolvidos ao lugar de origem.
```

Outros exemplos:

```bash
organiza-pasta ~/Downloads --por data            # 2024/05, 2024/06...
organiza-pasta ~/Downloads --por tipo-e-data     # Imagens/2024/05...
organiza-pasta ~/Downloads -s                    # sem pedir confirmação
organiza-pasta ~/Downloads --recursivo --simular # inclui as subpastas
```

No Windows o `~` também funciona: `organiza-pasta ~\Downloads --simular`. Caminhos com espaço vão entre aspas.

### Opções

| Opção | O que faz |
|---|---|
| `--por tipo\|data\|tipo-e-data` | como agrupar (padrão: `tipo`) |
| `-n`, `--simular` | mostra o plano completo sem mover nada |
| `-s`, `--sim` | não pede confirmação |
| `-r`, `--recursivo` | também organiza os arquivos das subpastas (elas ficam vazias, não são apagadas) |
| `--config REGRAS` | arquivo JSON com categorias personalizadas |
| `--desfazer` | desfaz a última organização (combina com `--simular` e `-s`) |

Códigos de saída: `0` deu certo (ou não havia nada a fazer), `1` operação cancelada, nada para desfazer ou algum arquivo não pôde ser movido, `2` uso incorreto (pasta inexistente, regras inválidas).

## Regras personalizadas

Crie um JSON com o nome da categoria (a pasta) e a lista de extensões, com ou sem ponto:

```json
{
  "Livros": ["epub", "mobi", "azw3"],
  "Notas Fiscais": ["xml"],
  "Modelos 3D": ["stl", "obj", "3mf", "blend"],
  "Torrents": [".torrent"]
}
```

```bash
organiza-pasta ~/Downloads --config regras.json --simular
```

- As regras personalizadas vencem as padrão: no exemplo acima, `.xml` deixa de ir para `Documentos` e vai para `Notas Fiscais`.
- Usar o nome de uma categoria existente (como `"Imagens": ["cbz"]`) acrescenta extensões a ela.
- Extensões compostas funcionam: `"Backups": ["tar.gz"]`.
- O arquivo de exemplo está em [`exemplos/regras.json`](exemplos/regras.json). Se ele estiver dentro da pasta organizada, não é movido.

## Categorias padrão

| Pasta | Extensões |
|---|---|
| Imagens | `jpg`, `jpeg`, `jpe`, `jfif`, `png`, `gif`, `bmp`, `tif`, `tiff`, `webp`, `heic`, `heif`, `avif`, `jxl`, `svg`, `ico`, `icns`, `psd`, `xcf`, `ai`, `eps`, `raw`, `cr2`, `cr3`, `nef`, `arw`, `dng`, `orf`, `rw2`, `raf` |
| Vídeos | `mp4`, `m4v`, `mkv`, `avi`, `mov`, `wmv`, `flv`, `f4v`, `webm`, `mpg`, `mpeg`, `m2v`, `3gp`, `3g2`, `vob`, `ogv`, `mts`, `m2ts`, `rm`, `rmvb`, `divx` |
| Áudios | `mp3`, `wav`, `flac`, `aac`, `m4a`, `m4b`, `ogg`, `oga`, `opus`, `wma`, `aif`, `aiff`, `amr`, `ape`, `mid`, `midi`, `caf`, `wv` |
| PDFs | `pdf` |
| Documentos | `doc`, `docx`, `docm`, `dot`, `dotx`, `odt`, `ott`, `rtf`, `txt`, `md`, `tex`, `pages`, `epub`, `mobi`, `azw`, `azw3`, `djvu`, `xps`, `oxps`, `wpd`, `xml`, `html`, `htm`, `mht`, `mhtml`, `webarchive` |
| Planilhas | `xls`, `xlsx`, `xlsm`, `xlsb`, `xltx`, `ods`, `ots`, `csv`, `tsv`, `numbers` |
| Apresentações | `ppt`, `pptx`, `pptm`, `pps`, `ppsx`, `pot`, `potx`, `odp`, `otp`, `key` |
| Compactados | `zip`, `rar`, `7z`, `tar`, `gz`, `tgz`, `bz2`, `tbz2`, `xz`, `txz`, `zst`, `lz`, `lzma`, `z`, `cab`, `arj` |
| Instaladores | `exe`, `msi`, `msix`, `msixbundle`, `appx`, `appxbundle`, `dmg`, `pkg`, `mpkg`, `deb`, `rpm`, `apk`, `xapk`, `aab`, `appimage`, `flatpakref`, `snap`, `iso`, `img`, `jar` |
| Código | `py`, `ipynb`, `js`, `mjs`, `cjs`, `ts`, `tsx`, `jsx`, `java`, `kt`, `kts`, `c`, `h`, `cpp`, `cc`, `cxx`, `hpp`, `hh`, `cs`, `go`, `rs`, `rb`, `php`, `swift`, `dart`, `lua`, `pl`, `r`, `scala`, `sh`, `bash`, `zsh`, `ps1`, `bat`, `cmd`, `sql`, `css`, `scss`, `sass`, `less`, `json`, `yaml`, `yml`, `toml`, `ini`, `vue`, `svelte` |
| Fontes | `ttf`, `otf`, `woff`, `woff2`, `eot`, `fon`, `ttc`, `pfb`, `pfm` |
| Outros | todo o resto, inclusive arquivos sem extensão |

O `.xml` fica em Documentos porque, para a maioria das pessoas, ele é uma nota fiscal eletrônica baixada do e-mail ou do site da loja.

## Como funciona

1. Lista os arquivos da pasta (e das subpastas com `--recursivo`), pulando links simbólicos, ocultos, temporários e downloads em andamento.
2. Monta um plano: para onde cada arquivo vai. Nomes já existentes no destino, e nomes repetidos dentro do próprio plano, ganham `(1)`, `(2)`... A comparação ignora maiúsculas e a forma de acentuação, como fazem o Windows e o macOS.
3. Depois da confirmação, move os arquivos (é só uma renomeação dentro do mesmo disco, então é instantâneo) e grava o histórico em `.organiza-pasta-historico.json`, dentro da própria pasta.
4. O `--desfazer` lê esse histórico, devolve cada arquivo ao lugar de origem e apaga só as pastas que ele mesmo criou e que ficaram vazias. Se um nome original já estiver em uso, o arquivo volta com `(1)` no nome; arquivos que sumiram são apenas listados.

## Rodando a partir do código-fonte

```bash
git clone https://github.com/micdog22/organiza-pasta
cd organiza-pasta
PYTHONPATH=src python3 -m organiza_pasta ~/Downloads --simular
```

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes criam pastas temporárias e nunca tocam nos seus arquivos.

## Contribuindo

Issues e pull requests são bem-vindos, principalmente sugestões de extensões que faltam no mapa.

## Licença

MIT. Veja [LICENSE](LICENSE).
