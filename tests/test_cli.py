import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from organiza_pasta.cli import format_size, main  # noqa: E402

HISTORY = ".organiza-pasta-historico.json"


def run(*args, answer=None):
    out, err = io.StringIO(), io.StringIO()
    answers = mock.patch("builtins.input", side_effect=EOFError if answer is None else [answer])
    with redirect_stdout(out), redirect_stderr(err), answers:
        try:
            code = main([str(a) for a in args])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for name in ("foto.jpg", "boleto.pdf", "planilha.xlsx", ".escondido", "video.mp4.part"):
            (self.root / name).write_text(name, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def listing(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))

    def test_simulate_changes_nothing(self):
        before = self.listing()
        code, out, _ = run(self.root, "--simular")
        self.assertEqual(code, 0)
        self.assertIn("foto.jpg -> Imagens/foto.jpg", out)
        self.assertIn("video.mp4.part (ignorado: download incompleto ou temporário)", out)
        self.assertIn("Simulação: nenhum arquivo foi movido.", out)
        self.assertEqual(self.listing(), before)

    def test_confirmation_refused_or_unanswered(self):
        before = self.listing()
        code, out, _ = run(self.root, answer="n")
        self.assertEqual(code, 1)
        self.assertIn("Nada foi alterado.", out)
        code, _, _ = run(self.root)  # sem resposta (EOF) também cancela
        self.assertEqual(code, 1)
        self.assertEqual(self.listing(), before)

    def test_organize_with_confirmation_then_undo(self):
        code, out, _ = run(self.root, answer="s")
        self.assertEqual(code, 0)
        self.assertIn("Pronto: 3 arquivos movidos.", out)
        self.assertTrue((self.root / "Imagens" / "foto.jpg").exists())
        self.assertTrue((self.root / "Planilhas" / "planilha.xlsx").exists())
        self.assertTrue((self.root / ".escondido").exists())
        self.assertTrue((self.root / "video.mp4.part").exists())

        code, out, _ = run(self.root, "--desfazer", "--simular")
        self.assertEqual(code, 0)
        self.assertIn("Imagens/foto.jpg -> foto.jpg", out)
        self.assertTrue((self.root / "Imagens" / "foto.jpg").exists())

        code, out, _ = run(self.root, "--desfazer", "-s")
        self.assertEqual(code, 0)
        self.assertIn("3 arquivos devolvidos", out)
        self.assertEqual(self.listing(), [".escondido", "boleto.pdf", "foto.jpg", "planilha.xlsx", "video.mp4.part"])

    def test_by_date_without_prompt(self):
        code, _, _ = run(self.root, "--por", "data", "-s")
        self.assertEqual(code, 0)
        history = json.loads((self.root / HISTORY).read_text(encoding="utf-8"))
        targets = [m["para"] for m in history["execucoes"][0]["movimentos"]]
        self.assertTrue(all(len(t.split("/")) == 3 for t in targets))

    def test_custom_rules(self):
        rules = self.root / "regras.json"
        rules.write_text(json.dumps({"Boletos": ["pdf"]}), encoding="utf-8")
        code, _, _ = run(self.root, "--config", rules, "-s")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "Boletos" / "boleto.pdf").exists())
        self.assertTrue(rules.exists(), "o próprio arquivo de regras não deve ser movido")

    def test_nothing_to_do(self):
        empty = self.root / "vazia"
        empty.mkdir()
        code, out, _ = run(empty, "-s")
        self.assertEqual(code, 0)
        self.assertIn("Nada para organizar", out)

    def test_errors(self):
        code, _, err = run(self.root / "nao-existe")
        self.assertEqual(code, 2)
        self.assertIn("pasta não encontrada", err)
        bad = self.root / "ruim.json"
        bad.write_text("[1, 2]", encoding="utf-8")
        code, _, err = run(self.root, "--config", bad, "-s")
        self.assertEqual(code, 2)
        self.assertIn("erro nas regras", err)
        code, _, err = run(self.root, "--desfazer", "-s")
        self.assertEqual(code, 1)
        self.assertIn("não há nenhuma organização para desfazer", err)
        code, _, err = run(self.root, "--por", "cor")
        self.assertEqual(code, 2)

    def test_corrupted_history_stops_before_moving(self):
        (self.root / HISTORY).write_text("{", encoding="utf-8")
        before = self.listing()
        code, _, err = run(self.root, "-s")
        self.assertEqual(code, 1)
        self.assertIn("corrompido", err)
        self.assertEqual(self.listing(), before)

    def test_format_size(self):
        self.assertEqual(format_size(0), "0 bytes")
        self.assertEqual(format_size(1), "1 byte")
        self.assertEqual(format_size(1000), "1.000 bytes")
        self.assertEqual(format_size(1536), "1,5 KB")
        self.assertEqual(format_size(10 * 1024 ** 2), "10 MB")
        self.assertEqual(format_size(int(2.25 * 1024 ** 3)), "2,2 GB")


if __name__ == "__main__":
    unittest.main()
