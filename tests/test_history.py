import json
import shutil
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from organiza_pasta.categories import DEFAULT_CATEGORIES, build_extension_map  # noqa: E402
from organiza_pasta.history import (  # noqa: E402
    HistoryError,
    execute,
    history_path,
    load_history,
    record_run,
    undo_last,
    undo_plan,
)
from organiza_pasta.planner import Move, build_plan, list_names, scan  # noqa: E402

MAP = build_extension_map(DEFAULT_CATEGORIES)


class ExecuteUndoTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.files = {
            "foto.jpg": "imagem",
            "contrato.pdf": "pdf",
            "música.mp3": "som",
            "sem-extensao": "texto",
        }
        for name, content in self.files.items():
            (self.root / name).write_text(content, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def organize(self, mode="tipo"):
        entries, _ = scan(self.root)
        plan = build_plan(entries, mode, MAP, lambda folder: list_names(self.root / folder))
        result = execute(self.root, plan)
        record_run(self.root, mode, result)
        return result

    def snapshot(self):
        return {
            unicodedata.normalize("NFC", p.relative_to(self.root).as_posix()): p.read_text(encoding="utf-8")
            for p in self.root.rglob("*") if p.is_file() and p.name != history_path(self.root).name
        }

    def test_roundtrip(self):
        before = self.snapshot()
        result = self.organize()
        self.assertEqual(len(result.done), 4)
        self.assertEqual(self.snapshot(), {
            "Imagens/foto.jpg": "imagem",
            "PDFs/contrato.pdf": "pdf",
            "Áudios/música.mp3": "som",
            "Outros/sem-extensao": "texto",
        })
        self.assertTrue(history_path(self.root).exists())
        undo = undo_last(self.root)
        self.assertEqual(len(undo.done), 4)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), sorted(self.files))  # pastas criadas somem
        self.assertFalse(history_path(self.root).exists())

    def test_existing_destination_folder_is_kept_after_undo(self):
        (self.root / "Imagens").mkdir()
        (self.root / "Imagens" / "foto.jpg").write_text("antiga", encoding="utf-8")
        self.organize()
        self.assertEqual((self.root / "Imagens" / "foto (1).jpg").read_text(encoding="utf-8"), "imagem")
        self.assertEqual((self.root / "Imagens" / "foto.jpg").read_text(encoding="utf-8"), "antiga")
        undo_last(self.root)
        self.assertEqual((self.root / "foto.jpg").read_text(encoding="utf-8"), "imagem")
        self.assertEqual((self.root / "Imagens" / "foto.jpg").read_text(encoding="utf-8"), "antiga")

    def test_undo_handles_missing_and_occupied_files(self):
        self.organize()
        (self.root / "PDFs" / "contrato.pdf").unlink()
        (self.root / "foto.jpg").write_text("nova", encoding="utf-8")
        result = undo_last(self.root)
        self.assertEqual([m.source.as_posix() for m in result.missing], ["PDFs/contrato.pdf"])
        self.assertEqual([m.target.as_posix() for m in result.renamed], ["foto (1).jpg"])
        self.assertEqual((self.root / "foto.jpg").read_text(encoding="utf-8"), "nova")
        self.assertEqual((self.root / "foto (1).jpg").read_text(encoding="utf-8"), "imagem")
        self.assertFalse((self.root / "PDFs").exists())

    def test_multiple_runs_are_undone_in_order(self):
        self.organize()
        (self.root / "nova.png").write_text("png", encoding="utf-8")
        self.organize()
        self.assertEqual(len(load_history(self.root)["execucoes"]), 2)
        undo_last(self.root)
        self.assertTrue((self.root / "nova.png").exists())
        self.assertTrue((self.root / "Imagens" / "foto.jpg").exists())
        undo_last(self.root)
        self.assertTrue((self.root / "foto.jpg").exists())
        with self.assertRaises(HistoryError):
            undo_last(self.root)

    def test_execute_does_not_overwrite_file_created_after_planning(self):
        entries, _ = scan(self.root)
        plan = build_plan(entries, "tipo", MAP, lambda folder: list_names(self.root / folder))
        (self.root / "Imagens").mkdir()
        (self.root / "Imagens" / "foto.jpg").write_text("chegou depois", encoding="utf-8")
        result = execute(self.root, plan)
        self.assertEqual((self.root / "Imagens" / "foto.jpg").read_text(encoding="utf-8"), "chegou depois")
        self.assertEqual([m.target.as_posix() for m in result.renamed], ["Imagens/foto (1).jpg"])

    def test_errors_are_collected(self):
        plan = [Move(PurePath("nao-existe.jpg"), PurePath("Imagens/nao-existe.jpg"))]
        result = execute(self.root, plan)
        self.assertEqual(result.done, [])
        self.assertEqual(len(result.errors), 1)

    def test_corrupted_history(self):
        history_path(self.root).write_text("{ quebrado", encoding="utf-8")
        with self.assertRaises(HistoryError):
            load_history(self.root)

    def test_unsafe_paths_in_history_are_rejected(self):
        for bad in ("../fora.txt", "/etc/passwd", ""):
            run = {"movimentos": [{"de": bad, "para": "Outros/x"}]}
            with self.subTest(bad=bad), self.assertRaises(HistoryError):
                undo_plan(run)

    def test_history_format(self):
        self.organize()
        data = json.loads(history_path(self.root).read_text(encoding="utf-8"))
        run = data["execucoes"][-1]
        self.assertEqual(run["modo"], "tipo")
        self.assertIn({"de": "foto.jpg", "para": "Imagens/foto.jpg"}, run["movimentos"])
        self.assertIn("Imagens", run["pastas_criadas"])


if __name__ == "__main__":
    unittest.main()
