"""Categorias padrão, regras personalizadas e classificação por extensão."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Dict, List

OTHER = "Outros"

DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "Imagens": (
        "jpg jpeg jpe jfif png gif bmp tif tiff webp heic heif avif jxl svg ico icns "
        "psd xcf ai eps raw cr2 cr3 nef arw dng orf rw2 raf"
    ).split(),
    "Vídeos": (
        "mp4 m4v mkv avi mov wmv flv f4v webm mpg mpeg m2v 3gp 3g2 vob ogv mts m2ts rm rmvb divx"
    ).split(),
    "Áudios": (
        "mp3 wav flac aac m4a m4b ogg oga opus wma aif aiff amr ape mid midi caf wv"
    ).split(),
    "PDFs": ["pdf"],
    "Documentos": (
        "doc docx docm dot dotx odt ott rtf txt md tex pages epub mobi azw azw3 djvu xps oxps "
        "wpd xml html htm mht mhtml webarchive"
    ).split(),
    "Planilhas": "xls xlsx xlsm xlsb xltx ods ots csv tsv numbers".split(),
    "Apresentações": "ppt pptx pptm pps ppsx pot potx odp otp key".split(),
    "Compactados": "zip rar 7z tar gz tgz bz2 tbz2 xz txz zst lz lzma z cab arj".split(),
    "Instaladores": (
        "exe msi msix msixbundle appx appxbundle dmg pkg mpkg deb rpm apk xapk aab "
        "appimage flatpakref snap iso img jar"
    ).split(),
    "Código": (
        "py ipynb js mjs cjs ts tsx jsx java kt kts c h cpp cc cxx hpp hh cs go rs rb php "
        "swift dart lua pl r scala sh bash zsh ps1 bat cmd sql css scss sass less json "
        "yaml yml toml ini vue svelte"
    ).split(),
    "Fontes": "ttf otf woff woff2 eot fon ttc pfb pfm".split(),
}

_FORBIDDEN_IN_NAMES = set('/\\:*?"<>|')


class ConfigError(Exception):
    """Problema no arquivo de regras, com mensagem pronta para o usuário."""


def name_key(name: str) -> str:
    """Chave para comparar nomes como o macOS e o Windows fazem (sem caixa, NFC)."""
    return unicodedata.normalize("NFC", name).casefold()


def sort_key(name: str) -> str:
    """Ordem alfabética sem considerar acentos ("Áudios" fica perto de "Arquivos")."""
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_extension(ext: str) -> str:
    return ext.strip().lstrip(".").lower()


def category_names(categories: Dict[str, List[str]]) -> List[str]:
    return list(categories) + ([OTHER] if OTHER not in categories else [])


def build_extension_map(categories: Dict[str, List[str]]) -> Dict[str, str]:
    mapping = {}
    for category, extensions in categories.items():
        for ext in extensions:
            mapping[normalize_extension(ext)] = category
    return mapping


def classify(name: str, extension_map: Dict[str, str]) -> str:
    """Categoria do arquivo pela extensão, sem diferenciar maiúsculas.

    Extensões compostas como "tar.gz" têm prioridade sobre a última ("gz").
    """
    parts = name.lower().split(".")
    for i in range(1, len(parts)):
        candidate = ".".join(parts[i:])
        if candidate in extension_map:
            return extension_map[candidate]
    return OTHER


def _validate_category(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("há uma categoria sem nome")
    name = name.strip()
    if name in (".", "..") or name.startswith(".") or _FORBIDDEN_IN_NAMES & set(name):
        raise ConfigError(f'nome de categoria inválido: "{name}" (não use / \\ : * ? " < > | nem ponto no início)')
    return name


def _validate_extensions(category: str, extensions: object) -> List[str]:
    example = f'"{category}": ["stl", "obj"]'
    if not isinstance(extensions, list) or not extensions:
        raise ConfigError(f'a categoria "{category}" precisa de uma lista de extensões, por exemplo {example}')
    result = []
    for ext in extensions:
        if not isinstance(ext, str) or not normalize_extension(ext):
            raise ConfigError(f'extensão inválida na categoria "{category}": {json.dumps(ext, ensure_ascii=False)}')
        normalized = normalize_extension(ext)
        if any(c.isspace() or c in _FORBIDDEN_IN_NAMES for c in normalized):
            raise ConfigError(f'extensão inválida na categoria "{category}": "{ext}"')
        result.append(normalized)
    return result


def load_rules(path) -> Dict[str, List[str]]:
    """Lê um JSON no formato {"Categoria": ["ext1", "ext2"]}."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ConfigError(f"arquivo de regras não encontrado: {path}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"{path}: o arquivo de regras precisa estar em UTF-8") from None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: JSON inválido na linha {exc.lineno}, coluna {exc.colno}") from None
    except OSError as exc:
        raise ConfigError(f"não foi possível ler {path}: {exc.strerror}") from None
    if not isinstance(data, dict) or not data:
        raise ConfigError(f'{path}: use um objeto JSON como {{"Livros": ["epub", "mobi"]}}')
    rules: Dict[str, List[str]] = {}
    owner: Dict[str, str] = {}
    for raw_name, extensions in data.items():
        category = _validate_category(raw_name)
        for ext in _validate_extensions(category, extensions):
            if ext in owner and owner[ext] != category:
                raise ConfigError(f'a extensão "{ext}" aparece em "{owner[ext]}" e em "{category}"')
            owner[ext] = category
            rules.setdefault(category, [])
            if ext not in rules[category]:
                rules[category].append(ext)
    return rules


def merge_rules(custom: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Regras personalizadas vencem: as extensões delas saem das categorias padrão."""
    taken = {ext for exts in custom.values() for ext in exts}
    merged = {cat: [e for e in exts if e not in taken] for cat, exts in DEFAULT_CATEGORIES.items()}
    by_key = {name_key(cat): cat for cat in merged}
    for category, extensions in custom.items():
        target = by_key.get(name_key(category), category)  # "imagens" vira "Imagens"
        merged.setdefault(target, [])
        merged[target] += [e for e in extensions if e not in merged[target]]
    return merged
