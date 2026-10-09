"""Linha de comando do organiza-pasta."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__
from .argparse_ptbr import ArgumentParser
from .categories import (
    DEFAULT_CATEGORIES,
    ConfigError,
    build_extension_map,
    category_names,
    load_rules,
    merge_rules,
    sort_key,
)
from .history import HistoryError, Result, execute, last_run, load_history, record_run, undo_last, undo_plan
from .planner import MODES, Move, build_plan, list_names, scan

PROG = "organiza-pasta"

EPILOG = """\
exemplos:
  organiza-pasta ~/Downloads --simular      mostra o plano sem mexer em nada
  organiza-pasta ~/Downloads                organiza por tipo (pede confirmação)
  organiza-pasta ~/Downloads --por data -s  organiza em AAAA/MM sem perguntar
  organiza-pasta ~/Downloads --config regras.json
  organiza-pasta ~/Downloads --desfazer     devolve tudo ao lugar de antes
"""


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=PROG,
        description=(
            "Organiza os arquivos de uma pasta (como Downloads) em subpastas por tipo\n"
            "ou por data. Nada é sobrescrito e dá para desfazer com --desfazer."
        ),
        epilog=EPILOG,
    )
    parser.add_argument("pasta", help="pasta a organizar, por exemplo ~/Downloads")
    parser.add_argument(
        "--por", choices=MODES, default="tipo",
        help="tipo (padrão): Imagens, PDFs, Vídeos...; data: AAAA/MM pela data de "
        "modificação; tipo-e-data: Imagens/AAAA/MM",
    )
    parser.add_argument("-r", "--recursivo", action="store_true", help="também organiza os arquivos das subpastas")
    parser.add_argument("-n", "--simular", action="store_true", help="só mostra o que seria feito, sem mover nada")
    parser.add_argument("-s", "--sim", action="store_true", help="não pede confirmação")
    parser.add_argument("--config", metavar="REGRAS", help="arquivo JSON com categorias personalizadas")
    parser.add_argument("--desfazer", action="store_true", help="desfaz a última organização feita nesta pasta")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}", help="mostra a versão e sai")
    return parser


# ---------------------------------------------------------------- utilidades de saída

def _color(text: str, code: str) -> str:
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return f"\033[{code}m{text}\033[0m"
    return text


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def format_size(size: int) -> str:
    """Tamanho no formato brasileiro: 512 bytes, 1,5 KB, 34,2 MB."""
    if size < 1024:
        return f"{size:,} {'byte' if size == 1 else 'bytes'}".replace(",", ".")
    value = float(size)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024 or unit == "TB":
            break
    text = f"{value:.1f}".replace(".", ",")
    return f"{text[:-2] if text.endswith(',0') else text} {unit}"


def confirm(question: str) -> bool:
    try:
        answer = input(f"{question} [s/N] ")
    except EOFError:
        print()
        return False
    return answer.strip().lower() in ("s", "sim", "y", "yes")


def _quoted(path: str) -> str:
    return f'"{path}"' if any(c.isspace() for c in path) else path


def _show_errors(result: Result) -> None:
    if result.errors:
        print(_color(f"Não foi possível mover {plural(len(result.errors), 'arquivo', 'arquivos')}:", "31"))
        for move, reason in result.errors:
            print(f"  {move.source.as_posix()}: {reason}")


# ---------------------------------------------------------------- organizar

def _summary(plan: List[Move]) -> List[Tuple[str, int, int]]:
    groups: Dict[str, List[int]] = {}
    for move in plan:
        folder = move.target.parent.as_posix()
        groups.setdefault(folder, [0, 0])
        groups[folder][0] += 1
        groups[folder][1] += move.size
    return [(folder, *groups[folder]) for folder in sorted(groups, key=sort_key)]


def _organize(root: Path, args: argparse.Namespace) -> int:
    rules = merge_rules(load_rules(args.config)) if args.config else dict(DEFAULT_CATEGORIES)
    load_history(root)  # avisa antes de mover qualquer coisa se o histórico estiver ilegível
    entries, ignored = scan(
        root,
        recursive=args.recursivo,
        skip_folders=category_names(rules),
        skip_files=[args.config] if args.config else [],
    )
    plan = build_plan(entries, args.por, build_extension_map(rules), lambda folder: list_names(root / folder))

    print(_color(f"Pasta: {args.pasta}  (organização por {args.por})", "1"))
    if ignored:
        reasons = Counter(reason for _, reason in ignored)
        details = ", ".join(f"{reason}: {count}" for reason, count in sorted(reasons.items()))
        print(f"Ignorados: {len(ignored)} ({details})")
    if not plan:
        print("Nada para organizar: a pasta já está em ordem.")
        return 0

    print()
    summary = _summary(plan)
    width = max(len(folder) for folder, _, _ in summary)
    for folder, count, size in summary:
        print(f"  {folder.ljust(width)}  {plural(count, 'arquivo', 'arquivos'):>13}  {format_size(size):>10}")
    total_size = sum(m.size for m in plan)
    print(f"\nTotal: {plural(len(plan), 'arquivo', 'arquivos')} ({format_size(total_size)}) "
          f"em {plural(len(summary), 'pasta', 'pastas')}.")
    renamed = [m for m in plan if m.target.name != m.source.name]
    if renamed:
        example = renamed[0].target.name
        print(f"{plural(len(renamed), 'arquivo vai', 'arquivos vão')} ganhar um número no nome para "
              f"não sobrescrever outro (ex.: {example}).")

    if args.simular:
        print()
        for move in plan:
            print(f"  {move.source.as_posix()} -> {move.target.as_posix()}")
        for path, reason in ignored:
            print(_color(f"  {path.as_posix()} (ignorado: {reason})", "2"))
        print("\nSimulação: nenhum arquivo foi movido.")
        return 0

    print()
    if not args.sim and not confirm(f"Mover {plural(len(plan), 'arquivo', 'arquivos')}?"):
        print("Nada foi alterado.")
        return 1

    result = execute(root, plan)
    record_run(root, args.por, result)
    if result.done:
        print(_color(f"Pronto: {plural(len(result.done), 'arquivo movido', 'arquivos movidos')}.", "32"))
        print(f"Para desfazer: organiza-pasta {_quoted(args.pasta)} --desfazer")
    if result.interrupted:
        print(_color("Interrompido: o que já foi movido está no histórico e pode ser desfeito.", "33"))
    _show_errors(result)
    return 1 if result.errors or result.interrupted else 0


# ---------------------------------------------------------------- desfazer

def _when(raw: str) -> str:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S").strftime("%d/%m/%Y às %H:%M")
    except (TypeError, ValueError):
        return str(raw)


def _undo(root: Path, args: argparse.Namespace) -> int:
    run = last_run(root)
    moves = undo_plan(run)
    print(_color(f"Última organização em {args.pasta}: {_when(run.get('data'))} "
                 f"({plural(len(moves), 'arquivo', 'arquivos')}, por {run.get('modo', 'tipo')})", "1"))
    if args.simular:
        for move in moves:
            print(f"  {move.source.as_posix()} -> {move.target.as_posix()}")
        print("\nSimulação: nenhum arquivo foi movido.")
        return 0
    if not args.sim and not confirm("Devolver os arquivos aos lugares de origem?"):
        print("Nada foi alterado.")
        return 1

    result = undo_last(root)
    print(_color(f"{plural(len(result.done), 'arquivo devolvido', 'arquivos devolvidos')} ao lugar de origem.", "32"))
    if result.missing:
        if len(result.missing) == 1:
            print("1 arquivo não foi encontrado (foi movido ou apagado depois) e ficou de fora:")
        else:
            print(f"{len(result.missing)} arquivos não foram encontrados (foram movidos ou apagados depois) "
                  "e ficaram de fora:")
        for move in result.missing:
            print(f"  {move.source.as_posix()}")
    if result.renamed:
        print(f"{plural(len(result.renamed), 'arquivo voltou', 'arquivos voltaram')} com outro nome "
              "porque o nome original já estava em uso:")
        for move in result.renamed:
            print(f"  {move.source.as_posix()} -> {move.target.as_posix()}")
    _show_errors(result)
    return 1 if result.errors else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # nomes de arquivo exóticos não derrubam a saída
    root = Path(args.pasta).expanduser()
    if not root.is_dir():
        print(f"{PROG}: erro: pasta não encontrada: {args.pasta}", file=sys.stderr)
        return 2
    try:
        return _undo(root, args) if args.desfazer else _organize(root, args)
    except ConfigError as exc:
        print(f"{PROG}: erro nas regras: {exc}", file=sys.stderr)
        return 2
    except HistoryError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{PROG}: erro: {exc.strerror or exc} ({exc.filename})", file=sys.stderr)
        return 1
