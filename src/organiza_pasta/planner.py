"""Varredura da pasta e geração do plano de movimentação (sem mexer em nada)."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePath
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from .categories import classify, name_key

MODES = ("tipo", "data", "tipo-e-data")
HISTORY_NAME = ".organiza-pasta-historico.json"

# Downloads em andamento e arquivos temporários: mexer neles pode corromper o download.
TEMPORARY_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".opdownload", ".tmp", ".temp")
SYSTEM_FILES = {"desktop.ini", "thumbs.db", "ehthumbs.db", "icon\r"}
# Pastas que são "um arquivo só" para o usuário (apps do macOS, pacotes etc.).
BUNDLE_SUFFIXES = (".app", ".bundle", ".framework", ".photoslibrary", ".pkg", ".download", ".xcodeproj")
COMPOUND_EXTENSIONS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst")
_YEAR_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class Entry:
    path: PurePath  # relativo à pasta organizada
    mtime: float
    size: int


@dataclass(frozen=True)
class Move:
    source: PurePath
    target: PurePath
    size: int = 0


def ignore_reason(name: str) -> Optional[str]:
    lower = name.lower()
    if name.startswith("."):
        return "oculto"
    if name.startswith("~$"):
        return "temporário do Office"
    if lower in SYSTEM_FILES:
        return "arquivo do sistema"
    if lower.endswith(TEMPORARY_SUFFIXES):
        return "download incompleto ou temporário"
    return None


def _hidden_on_windows(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & (getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)))


def scan(
    root: Path,
    recursive: bool = False,
    skip_folders: Iterable[str] = (),
    skip_files: Iterable[Path] = (),
) -> Tuple[List[Entry], List[Tuple[PurePath, str]]]:
    """Lista os arquivos a organizar e os ignorados (com o motivo).

    No modo recursivo, não entra nas pastas de destino (categorias e anos), em
    pastas ocultas, em pacotes como .app nem em projetos com .git.
    """
    skip_keys = {name_key(n) for n in skip_folders}
    skip_paths = {Path(p).resolve() for p in skip_files}
    entries: List[Entry] = []
    ignored: List[Tuple[PurePath, str]] = []

    def walk(directory: Path, relative: PurePath) -> None:
        try:
            with os.scandir(directory) as iterator:
                items = sorted(iterator, key=lambda e: name_key(e.name))
        except PermissionError:
            if relative == PurePath():
                raise
            ignored.append((relative, "sem permissão de leitura"))
            return
        for item in items:
            rel = relative / item.name
            if item.is_symlink():
                ignored.append((rel, "link simbólico"))
                continue
            if item.is_dir():
                top_level_target = relative == PurePath() and (
                    name_key(item.name) in skip_keys or _YEAR_RE.match(item.name)
                )
                if (
                    recursive
                    and not top_level_target
                    and ignore_reason(item.name) is None
                    and not item.name.lower().endswith(BUNDLE_SUFFIXES)
                    and not os.path.isdir(os.path.join(item.path, ".git"))
                ):
                    walk(Path(item.path), rel)
                continue
            if not item.is_file():
                continue
            st = item.stat()
            reason = ignore_reason(item.name) or ("oculto" if _hidden_on_windows(st) else None)
            if reason is None and Path(item.path).resolve() in skip_paths:
                reason = "arquivo de regras"
            if reason:
                ignored.append((rel, reason))
                continue
            entries.append(Entry(rel, st.st_mtime, st.st_size))

    walk(Path(root), PurePath())
    return entries, ignored


def split_name(name: str) -> Tuple[str, str]:
    """Separa nome e extensão: "foto.jpg" -> ("foto", ".jpg"), "a.tar.gz" -> ("a", ".tar.gz")."""
    lower = name.lower()
    for compound in COMPOUND_EXTENSIONS:
        if lower.endswith(compound) and len(name) > len(compound):
            return name[: -len(compound)], name[-len(compound):]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return name, ""
    return stem, "." + ext


def free_name(name: str, taken: Set[str]) -> str:
    """Primeiro nome livre no estilo do navegador: "nome (1).ext", "nome (2).ext"..."""
    if name_key(name) not in taken:
        return name
    stem, ext = split_name(name)
    number = 1
    while name_key(f"{stem} ({number}){ext}") in taken:
        number += 1
    return f"{stem} ({number}){ext}"


def destination_folder(entry: Entry, mode: str, extension_map: Dict[str, str]) -> PurePath:
    category = classify(entry.path.name, extension_map)
    if mode == "tipo":
        return PurePath(category)
    when = datetime.fromtimestamp(entry.mtime)
    by_date = PurePath(f"{when.year:04d}", f"{when.month:02d}")
    return by_date if mode == "data" else PurePath(category) / by_date


def build_plan(
    entries: Iterable[Entry],
    mode: str,
    extension_map: Dict[str, str],
    existing: Optional[Callable[[PurePath], Iterable[str]]] = None,
) -> List[Move]:
    """Plano puro: para onde cada arquivo vai, sem sobrescrever nada.

    `existing(pasta)` devolve os nomes que já existem numa pasta de destino.
    """
    if mode not in MODES:
        raise ValueError(f"modo desconhecido: {mode}")
    taken: Dict[PurePath, Set[str]] = {}
    plan: List[Move] = []
    for entry in entries:
        folder = destination_folder(entry, mode, extension_map)
        if entry.path.parent == folder:
            continue
        if folder not in taken:
            taken[folder] = {name_key(n) for n in (existing(folder) if existing else ())}
        name = free_name(entry.path.name, taken[folder])
        taken[folder].add(name_key(name))
        plan.append(Move(entry.path, folder / name, entry.size))
    return plan


def list_names(folder: Path) -> List[str]:
    try:
        return os.listdir(folder)
    except (FileNotFoundError, NotADirectoryError):
        return []
