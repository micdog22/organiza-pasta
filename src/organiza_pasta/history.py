"""Execução do plano, histórico em JSON e desfazer."""

from __future__ import annotations

import errno
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import List, Optional, Tuple

from .categories import name_key
from .planner import HISTORY_NAME, Move, free_name, list_names


class HistoryError(Exception):
    """Histórico ausente, vazio ou ilegível."""


@dataclass
class Result:
    done: List[Move] = field(default_factory=list)
    errors: List[Tuple[Move, str]] = field(default_factory=list)
    missing: List[Move] = field(default_factory=list)
    renamed: List[Move] = field(default_factory=list)
    created: List[PurePath] = field(default_factory=list)
    interrupted: bool = False


def _move_file(source: Path, target: Path) -> None:
    try:
        os.rename(source, target)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.move(str(source), str(target))


def _make_folders(root: Path, folder: PurePath) -> List[PurePath]:
    created = []
    current = PurePath()
    for part in folder.parts:
        current = current / part
        try:
            (root / current).mkdir()
            created.append(current)
        except FileExistsError:
            if not (root / current).is_dir():
                raise
    return created


def _place(root: Path, move: Move, result: Result) -> Move:
    """Move um arquivo sem sobrescrever; se o destino passou a existir, usa outro nome."""
    folder = move.target.parent
    result.created += _make_folders(root, folder)
    if os.path.lexists(root / move.target):
        taken = {name_key(n) for n in list_names(root / folder)}
        move = Move(move.source, folder / free_name(move.target.name, taken), move.size)
        result.renamed.append(move)
    _move_file(root / move.source, root / move.target)
    return move


def execute(root: Path, plan: List[Move]) -> Result:
    result = Result()
    try:
        for move in plan:
            try:
                result.done.append(_place(root, move, result))
            except OSError as exc:
                result.errors.append((move, exc.strerror or str(exc)))
    except KeyboardInterrupt:
        result.interrupted = True  # o que já foi movido continua no histórico
    return result


# ---------------------------------------------------------------- histórico

def history_path(root: Path) -> Path:
    return Path(root) / HISTORY_NAME


def load_history(root: Path) -> dict:
    path = history_path(root)
    if not path.exists():
        return {"versao": 1, "execucoes": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("execucoes"), list):
            raise ValueError
        return data
    except (ValueError, OSError):
        raise HistoryError(
            f"o histórico {HISTORY_NAME} está corrompido ou ilegível; renomeie ou apague esse arquivo"
        ) from None


def _write_history(root: Path, data: dict) -> None:
    path = history_path(root)
    if not data["execucoes"]:
        if path.exists():
            path.unlink()
        return
    fd, temp = tempfile.mkstemp(prefix=".organiza-pasta-", suffix=".tmp", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def record_run(root: Path, mode: str, result: Result) -> None:
    if not result.done:
        return
    data = load_history(root)
    data["execucoes"].append({
        "data": datetime.now().isoformat(timespec="seconds"),
        "modo": mode,
        "movimentos": [{"de": m.source.as_posix(), "para": m.target.as_posix()} for m in result.done],
        "pastas_criadas": [p.as_posix() for p in result.created],
    })
    _write_history(root, data)


def _safe_relative(raw: object) -> PurePath:
    text = str(raw) if isinstance(raw, str) else ""
    posix = PurePosixPath(text)
    windows_anchor = os.name == "nt" and PureWindowsPath(text).anchor
    if not text or posix.is_absolute() or windows_anchor or ".." in posix.parts:
        raise HistoryError(f"caminho inválido no histórico: {raw!r}")
    return PurePath(*posix.parts)


def last_run(root: Path, data: Optional[dict] = None) -> dict:
    data = load_history(root) if data is None else data
    if not data["execucoes"]:
        raise HistoryError("não há nenhuma organização para desfazer nesta pasta")
    return data["execucoes"][-1]


def undo_plan(run: dict) -> List[Move]:
    """Movimentos inversos da execução, do último para o primeiro."""
    moves = []
    for item in reversed(run.get("movimentos", [])):
        if not isinstance(item, dict):
            raise HistoryError("histórico em formato inesperado")
        moves.append(Move(_safe_relative(item.get("para")), _safe_relative(item.get("de"))))
    return moves


def undo_last(root: Path) -> Result:
    """Devolve os arquivos da última execução aos lugares de origem."""
    root = Path(root)
    data = load_history(root)
    run = last_run(root, data)
    result = Result()
    failed = []
    for move in undo_plan(run):
        if not (root / move.source).is_file():
            result.missing.append(move)
            continue
        try:
            result.done.append(_place(root, move, result))
        except OSError as exc:
            result.errors.append((move, exc.strerror or str(exc)))
            failed.append({"de": move.target.as_posix(), "para": move.source.as_posix()})
    created = [_safe_relative(p) for p in run.get("pastas_criadas", [])]
    for folder in sorted(created, key=lambda p: len(p.parts), reverse=True):
        try:
            (root / folder).rmdir()  # só remove pastas que ficaram vazias
        except OSError:
            pass
    if failed:
        run["movimentos"] = list(reversed(failed))
    else:
        data["execucoes"].pop()
    _write_history(root, data)
    return result
