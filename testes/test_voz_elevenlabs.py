"""Gravação da voz pela ElevenLabs (o pedido e os erros) e a pasta das frases por voz."""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error

import caminhos
import falas
import voz

sys.path.insert(0, os.path.join(caminhos.RAIZ, "ferramentas"))
import gerar_voz_elevenlabs as gravar  # noqa: E402


class _Resposta:
    def __init__(self, dados):
        self._dados = dados

    def read(self):
        return self._dados

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TesteGravacao(unittest.TestCase):
    def test_cabe_nos_creditos_do_plano_gratuito(self):
        total = sum(len(t) for t in falas.GRAVADAS.values())
        self.assertLess(total, gravar.LIMITE_CARACTERES)
        self.assertLess(total, 10000 / 3)            # dá para gravar tudo 3 vezes com 10.000 créditos

    def test_cada_pedaco_leva_o_texto_vizinho(self):
        self.assertEqual(gravar.vizinhos("em_200"), ("Parceiro,", "viramos à direita."))
        self.assertEqual(gravar.vizinhos("vire_direita"), ("Parceiro, em duzentos metros,", ""))
        self.assertEqual(gravar.vizinhos("subida_8")[0], "Parceiro, em duzentos metros,")
        self.assertEqual(gravar.vizinhos("recalculando"), ("", ""))          # frase inteira: sem vizinho
        for chave in falas.FALAS:
            self.assertEqual(len(gravar.vizinhos(chave)), 2)

    def test_a_voz_gravada_tem_as_mesmas_falas_com_o_texto_dela(self):
        self.assertEqual(set(falas.GRAVADAS), set(falas.FALAS))          # as mesmas chaves: o app monta igual
        self.assertEqual(falas.GRAVADAS["vire_direita"], "viramos à direita.")
        self.assertEqual(falas.GRAVADAS["em_200"], falas.FALAS["em_200"])  # distâncias iguais
        self.assertEqual(falas.FALAS["vire_direita"], "vire à direita.")   # a tela e a voz do celular não mudaram
        self.assertEqual(falas.texto_manobra("direita"), "Vire à direita")

    def test_o_pedido(self):
        vistos = []

        def abrir(pedido, timeout=0):
            vistos.append(pedido)
            return _Resposta(b"MP3")
        self.assertEqual(gravar.pedir("CHAVE-SECRETA", "VOZ123", "vire à direita.", "Senhor,", "", abrir=abrir), b"MP3")
        p = vistos[0]
        self.assertEqual(p.full_url, "https://api.elevenlabs.io/v1/text-to-speech/VOZ123?output_format=mp3_44100_128")
        self.assertEqual(p.get_method(), "POST")
        self.assertEqual(p.get_header("Xi-api-key"), "CHAVE-SECRETA")
        corpo = json.loads(p.data.decode("utf-8"))
        self.assertEqual((corpo["text"], corpo["model_id"], corpo["previous_text"]),
                         ("vire à direita.", "eleven_multilingual_v2", "Senhor,"))
        self.assertNotIn("next_text", corpo)
        self.assertEqual(corpo["voice_settings"]["style"], 0.0)              # tom sério

    def test_erros_claros_e_sem_a_chave(self):
        def recusa(codigo):
            def abrir(pedido, timeout=0):
                raise urllib.error.HTTPError(pedido.full_url, codigo, "x", None, io.BytesIO(b'{"detail": "motivo"}'))
            return abrir
        for codigo, trecho in ((401, "chave"), (404, "Voice ID"), (429, "créditos")):
            with self.assertRaises(RuntimeError) as c:
                gravar.pedir("CHAVE-SECRETA", "V", "oi", abrir=recusa(codigo))
            self.assertIn(trecho, str(c.exception))
            self.assertIn("[erro %d]" % codigo, str(c.exception))
            self.assertNotIn("CHAVE-SECRETA", str(c.exception))


class TestePastaDasFrases(unittest.TestCase):
    def test_uma_pasta_por_voz_e_a_antiga_sai(self):
        original = voz.PASTA_VOZ
        with tempfile.TemporaryDirectory() as gravacoes, tempfile.TemporaryDirectory() as celular:
            voz.PASTA_VOZ = gravacoes
            try:
                self.assertEqual(voz.marca_da_voz(), "3")                    # sem voz.json: a voz de antes
                antiga = voz.pasta_das_frases(celular)
                self.assertTrue(antiga.endswith("falas3") and os.path.isdir(antiga))
                os.makedirs(os.path.join(celular, "outra_coisa"))
                with open(os.path.join(gravacoes, "voz.json"), "w", encoding="utf-8") as f:
                    json.dump({"origem": "elevenlabs", "voz": "Ab/C..1", "feita_em": "20261008120000"}, f)
                nova = voz.pasta_das_frases(celular)
                self.assertTrue(nova.endswith("falasAbC1-20261008120000"))
                self.assertFalse(os.path.exists(antiga))                     # as frases da voz antiga saíram
                self.assertTrue(os.path.isdir(os.path.join(celular, "outra_coisa")))   # o resto fica
            finally:
                voz.PASTA_VOZ = original


if __name__ == "__main__":
    unittest.main()
