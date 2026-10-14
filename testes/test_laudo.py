"""laudo.py: o laudo de queda nativa do Android (tombstone em protobuf) vira texto legível."""
import os
import tempfile
import unittest

import caminhos  # noqa: F401
import laudo


def _vi(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _num(campo, v):
    return _vi(campo << 3) + _vi(v)


def _str(campo, v):
    v = v.encode() if isinstance(v, str) else v
    return _vi((campo << 3) | 2) + _vi(len(v)) + v


def laudo_falso():
    quadro = lambda f, a, o: _str(4, _num(1, 0x1234) + _str(4, f) + _num(5, o) + _str(6, a))
    caiu = _num(1, 77) + _str(2, "SDLThread") + quadro("glDrawElements", "/vendor/lib64/egl/libGLESv2_adreno.so", 40) \
        + quadro("", "/data/app/x/lib/arm64/libmain.so", 0)
    outra = _num(1, 12) + _str(2, "outra") + quadro("nada", "/system/lib64/libc.so", 1)
    log = _str(2, _str(1, "10-14 10:47:40.123") + _str(5, "Adreno-GSL") + _str(6, "<gsl_ldd_control>: falhou"))
    return (_num(5, 70) + _num(6, 77) + _str(9, "org.kirito.gthud")
            + _str(10, _str(2, "SIGSEGV") + _str(4, "SEGV_MAPERR") + _num(8, 1) + _num(9, 0x10))
            + _str(14, "")
            + _str(16, _num(1, 12) + _str(2, outra))
            + _str(16, _num(1, 77) + _str(2, caiu))
            + _str(18, _str(1, "main") + log))


class TestLaudo(unittest.TestCase):
    def test_tombstone_vira_texto(self):
        t = laudo.ler_laudo(laudo_falso())
        self.assertIn("SIGSEGV (SEGV_MAPERR) no endereço 0x10", t)
        self.assertIn("thread que caiu: SDLThread", t)
        self.assertIn("libGLESv2_adreno.so (glDrawElements+40)", t)
        self.assertIn("#01 libmain.so", t)
        self.assertNotIn("libc.so", t)                  # só a pilha da thread que caiu
        self.assertIn("Adreno-GSL: <gsl_ldd_control>: falhou", t)

    def test_lixo_vira_palavras(self):
        t = laudo.ler_laudo(b"\xff\xff\xff\xff libalgumacoisa.so \x00\x01 funcao_qualquer \x02")
        self.assertTrue(t.startswith("palavras do laudo:"))
        self.assertIn("libalgumacoisa.so", t)

    def test_resumir_so_as_novas_e_com_laudo(self):
        with tempfile.TemporaryDirectory() as d:
            cam = os.path.join(d, "laudo.pb")
            with open(cam, "wb") as f:
                f.write(laudo_falso())
            texto = ("laudo=0\n"
                     "2000|5|11|org.kirito.gthud|crash\n"
                     "1500|10|0|org.kirito.gthud|\n"
                     "1000|5|11|org.kirito.gthud|velha\n")
            linhas, nova = laudo.resumir(texto, cam, 1200)
        self.assertEqual(nova, 2000)
        tudo = "\n".join(linhas)
        self.assertIn("!!! QUEDA NATIVA [org.kirito.gthud] status 11: crash", tudo)
        self.assertIn("fechado pelo dono", tudo)
        self.assertNotIn("velha", tudo)                 # já vista antes
        self.assertIn("glDrawElements", tudo)

    def test_resumir_sem_nada(self):
        self.assertEqual(laudo.resumir("", "x", 5), ([], 5))
        self.assertEqual(laudo.resumir("laudo=-1\n", "x", 5), ([], 5))


if __name__ == "__main__":
    unittest.main()
