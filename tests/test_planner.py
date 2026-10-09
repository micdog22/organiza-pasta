import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from organiza_pasta.categories import DEFAULT_CATEGORIES, build_extension_map, category_names  # noqa: E402
from organiza_pasta.planner import (  # noqa: E402
    Entry,
    build_plan,
    free_name,
    ignore_reason,
    scan,
    split_name,
)

MAP = build_extension_map(DEFAULT_CATEGORIES)
MAY_2024 = datetime(2024, 5, 17, 12, 0).timestamp()
DEC_2023 = datetime(2023, 12, 31, 23, 0).timestamp()


def entry(name, mtime=MAY_2024, size=10):
    return Entry(PurePath(name), mtime, size)


def targets(plan):
    return {m.source.as_posix(): m.target.as_posix() for m in plan}


class IgnoreTests(unittest.TestCase):
    def test_reasons(self):
        self.assertEqual(ignore_reason(".DS_Store"), "oculto")
        self.assertEqual(ignore_reason(".organiza-pasta-historico.json"), "oculto")
        self.assertEqual(ignore_reason("~$relatorio.docx"), "temporário do Office")
        self.assertEqual(ignore_reason("Thumbs.db"), "arquivo do sistema")
        self.assertEqual(ignore_reason("desktop.ini"), "arquivo do sistema")
        for name in ("filme.mkv.crdownload", "iso.PART", "foto.jpg.download", "x.tmp", "y.opdownload"):
            with self.subTest(name=name):
                self.assertEqual(ignore_reason(name), "download incompleto ou temporário")
        self.assertIsNone(ignore_reason("relatorio.pdf"))
        self.assertIsNone(ignore_reason("partitura.pdf"))


class NameTests(unittest.TestCase):
    def test_split_name(self):
        self.assertEqual(split_name("foto.jpg"), ("foto", ".jpg"))
        self.assertEqual(split_name("site.tar.gz"), ("site", ".tar.gz"))
        self.assertEqual(split_name("LEIAME"), ("LEIAME", ""))
        self.assertEqual(split_name("versao.1.2.zip"), ("versao.1.2", ".zip"))

    def test_free_name(self):
        self.assertEqual(free_name("foto.jpg", set()), "foto.jpg")
        self.assertEqual(free_name("foto.jpg", {"foto.jpg"}), "foto (1).jpg")
        self.assertEqual(free_name("foto.jpg", {"foto.jpg", "foto (1).jpg"}), "foto (2).jpg")
        self.assertEqual(free_name("site.tar.gz", {"site.tar.gz"}), "site (1).tar.gz")
        self.assertEqual(free_name("LEIAME", {"leiame"}), "LEIAME (1)")

    def test_collision_ignores_case_and_unicode_form(self):
        decomposed = "Relato\u0301rio.pdf"  # "Relatório" como o macOS às vezes guarda
        plan = build_plan([entry("relatório.PDF")], "tipo", MAP, lambda folder: [decomposed])
        self.assertEqual(targets(plan), {"relatório.PDF": "PDFs/relatório (1).PDF"})


class PlanTests(unittest.TestCase):
    def test_by_type(self):
        plan = build_plan([entry("a.jpg"), entry("b.pdf"), entry("c.xyz")], "tipo", MAP)
        self.assertEqual(targets(plan), {"a.jpg": "Imagens/a.jpg", "b.pdf": "PDFs/b.pdf", "c.xyz": "Outros/c.xyz"})

    def test_by_date_and_type_and_date(self):
        entries = [entry("a.jpg", MAY_2024), entry("b.pdf", DEC_2023)]
        self.assertEqual(targets(build_plan(entries, "data", MAP)), {"a.jpg": "2024/05/a.jpg", "b.pdf": "2023/12/b.pdf"})
        self.assertEqual(
            targets(build_plan(entries, "tipo-e-data", MAP)),
            {"a.jpg": "Imagens/2024/05/a.jpg", "b.pdf": "PDFs/2023/12/b.pdf"},
        )

    def test_never_overwrites_existing_files(self):
        existing = {PurePath("Imagens"): ["foto.jpg", "foto (1).jpg"]}
        plan = build_plan([entry("foto.jpg")], "tipo", MAP, lambda folder: existing.get(folder, []))
        self.assertEqual(targets(plan), {"foto.jpg": "Imagens/foto (2).jpg"})

    def test_collisions_inside_the_plan(self):
        entries = [entry("Foto.JPG"), entry("sub/foto.jpg"), entry("outra/FOTO.jpg")]
        self.assertEqual(sorted(targets(build_plan(entries, "tipo", MAP)).values()), [
            "Imagens/FOTO (2).jpg", "Imagens/Foto.JPG", "Imagens/foto (1).jpg",
        ])

    def test_file_already_in_place_is_kept(self):
        self.assertEqual(build_plan([entry("Imagens/a.jpg")], "tipo", MAP), [])

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            build_plan([entry("a.jpg")], "cor", MAP)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for rel in (
            "foto.jpg", ".oculto", "filme.mkv.crdownload", "~$doc.docx", "regras.json",
            "sub/interno.png", "Imagens/ja-organizada.jpg", "2024/05/antiga.pdf",
            "Programa.app/Contents/binario", "projeto/.git/HEAD", "projeto/main.py", ".cache/x.txt",
        ):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
        try:
            os.symlink(self.root / "foto.jpg", self.root / "atalho.jpg")
        except (OSError, NotImplementedError):
            pass

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def names(self, entries):
        return sorted(e.path.as_posix() for e in entries)

    def test_top_level_only(self):
        entries, ignored = scan(self.root, skip_files=[self.root / "regras.json"])
        self.assertEqual(self.names(entries), ["foto.jpg"])
        reasons = {p.as_posix(): r for p, r in ignored}
        self.assertEqual(reasons[".oculto"], "oculto")
        self.assertEqual(reasons["filme.mkv.crdownload"], "download incompleto ou temporário")
        self.assertEqual(reasons["~$doc.docx"], "temporário do Office")
        self.assertEqual(reasons["regras.json"], "arquivo de regras")
        if (self.root / "atalho.jpg").is_symlink():
            self.assertEqual(reasons["atalho.jpg"], "link simbólico")

    def test_recursive_skips_destinations_bundles_and_projects(self):
        entries, _ = scan(self.root, recursive=True, skip_folders=category_names(DEFAULT_CATEGORIES))
        self.assertEqual(self.names(entries), ["foto.jpg", "regras.json", "sub/interno.png"])

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "permissões POSIX")
    def test_unreadable_subfolder_is_skipped(self):
        locked = self.root / "sub"
        locked.chmod(0)
        try:
            entries, ignored = scan(self.root, recursive=True, skip_folders=category_names(DEFAULT_CATEGORIES))
        finally:
            locked.chmod(0o755)
        self.assertNotIn("sub/interno.png", self.names(entries))
        self.assertIn((PurePath("sub"), "sem permissão de leitura"), ignored)

    def test_entries_have_size_and_mtime(self):
        os.utime(self.root / "foto.jpg", (MAY_2024, MAY_2024))
        [found] = [e for e in scan(self.root)[0] if e.path.name == "foto.jpg"]
        self.assertEqual(found.size, 1)
        self.assertEqual(int(found.mtime), int(MAY_2024))


if __name__ == "__main__":
    unittest.main()
