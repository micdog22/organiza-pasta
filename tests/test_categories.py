import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from organiza_pasta.categories import (  # noqa: E402
    DEFAULT_CATEGORIES,
    OTHER,
    ConfigError,
    build_extension_map,
    classify,
    load_rules,
    merge_rules,
    sort_key,
)

DEFAULT_MAP = build_extension_map(DEFAULT_CATEGORIES)


class ClassifyTests(unittest.TestCase):
    def test_common_downloads(self):
        cases = {
            "foto.jpg": "Imagens",
            "IMG_0001.HEIC": "Imagens",
            "video.MP4": "Vídeos",
            "audio.Opus": "Áudios",
            "contrato.docx": "Documentos",
            "nota-fiscal.xml": "Documentos",
            "boleto.pdf": "PDFs",
            "extrato.csv": "Planilhas",
            "aula.pptx": "Apresentações",
            "fotos.zip": "Compactados",
            "instalador.exe": "Instaladores",
            "ubuntu.iso": "Instaladores",
            "app.dmg": "Instaladores",
            "script.py": "Código",
            "fonte.woff2": "Fontes",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify(name, DEFAULT_MAP), expected)

    def test_unknown_and_without_extension(self):
        self.assertEqual(classify("arquivo.xyz", DEFAULT_MAP), OTHER)
        self.assertEqual(classify("LEIAME", DEFAULT_MAP), OTHER)
        self.assertEqual(classify("estranho.", DEFAULT_MAP), OTHER)

    def test_compound_extension_has_priority(self):
        mapping = build_extension_map({"Backups": ["tar.gz"], "Compactados": ["gz"]})
        self.assertEqual(classify("site.TAR.GZ", mapping), "Backups")
        self.assertEqual(classify("log.gz", mapping), "Compactados")

    def test_each_extension_in_a_single_default_category(self):
        seen = {}
        for category, extensions in DEFAULT_CATEGORIES.items():
            for ext in extensions:
                self.assertNotIn(ext, seen, f"{ext} em {seen.get(ext)} e {category}")
                self.assertEqual(ext, ext.lower())
                seen[ext] = category

    def test_sort_ignores_accents(self):
        names = ["Vídeos", "Áudios", "Código", "Compactados", "Apresentações"]
        self.assertEqual(sorted(names, key=sort_key), ["Apresentações", "Áudios", "Código", "Compactados", "Vídeos"])


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, content) -> Path:
        path = self.tmp / "regras.json"
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_rules_are_normalized(self):
        rules = load_rules(self.write({"Livros": [".EPUB", "mobi", "mobi"], " Modelos 3D ": ["stl"]}))
        self.assertEqual(rules, {"Livros": ["epub", "mobi"], "Modelos 3D": ["stl"]})

    def test_example_file_in_repository_is_valid(self):
        rules = load_rules(Path(__file__).resolve().parents[1] / "exemplos" / "regras.json")
        self.assertIn("Livros", rules)

    def test_custom_rules_win_over_defaults(self):
        merged = merge_rules({"Notas Fiscais": ["xml"], "imagens": ["cbz"]})
        mapping = build_extension_map(merged)
        self.assertEqual(classify("nfe.xml", mapping), "Notas Fiscais")
        self.assertNotIn("xml", merged["Documentos"])
        self.assertEqual(classify("quadrinho.cbz", mapping), "Imagens")
        self.assertNotIn("imagens", merged)

    def test_errors(self):
        cases = [
            ("{", "JSON inválido"),
            ([], "objeto JSON"),
            ({}, "objeto JSON"),
            ({"Livros": "epub"}, "lista de extensões"),
            ({"Livros": []}, "lista de extensões"),
            ({"Livros": ["epub", 3]}, "extensão inválida"),
            ({"Livros": ["e pub"]}, "extensão inválida"),
            ({"../fora": ["epub"]}, "nome de categoria inválido"),
            ({".oculta": ["epub"]}, "nome de categoria inválido"),
            ({"": ["epub"]}, "sem nome"),
            ({"A": ["epub"], "B": ["EPUB"]}, "aparece em"),
        ]
        for content, message in cases:
            with self.subTest(content=content), self.assertRaises(ConfigError) as ctx:
                load_rules(self.write(content))
            self.assertIn(message, str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as ctx:
            load_rules(self.tmp / "nao-existe.json")
        self.assertIn("não encontrado", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
