"""Sons de aviso: qual som anuncia cada fala, volume e arquivos."""
import os
import unittest
import wave

import falas
import sons


class TesteSons(unittest.TestCase):
    def test_som_de_cada_tipo_de_fala(self):
        casos = {
            ("em_200", "vire_direita"): "curva", ("senhor", "em_100", "rotatoria_2"): "curva",
            ("senhor", "chegou"): "chegada", ("recalculando",): "recalculo", ("radar",): "radar",
            ("incidente",): "alerta", ("avenida",): "alerta", ("chuva",): "alerta",
            ("rota_calculada",): "inicio", ("caminho_melhor",): "pronto",
            ("semaforo",): "aviso", ("senhor", "em_200", "subida_6"): "aviso",
            ("em_frente",): None, ("bem_vindo",): None,
        }
        for pedacos, esperado in casos.items():
            self.assertEqual(sons.som_da_fala(list(pedacos)), esperado, pedacos)

    def test_as_falas_citadas_existem(self):
        for chave in sons._DA_FALA:
            self.assertIn(chave, falas.FALAS)

    def test_arquivos_curtos_e_sem_estourar(self):
        usados = set(sons._DA_FALA.values()) | {"curva", "aviso", "toque", "pronto"}
        for nome in usados:
            caminho = os.path.join(sons.PASTA, nome + ".wav")
            self.assertTrue(os.path.exists(caminho), nome)
            with wave.open(caminho, "rb") as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth()), (1, 2))
                dur = w.getnframes() / float(w.getframerate())
                quadros = w.readframes(w.getnframes())
            self.assertLess(dur, 0.85, nome)                      # a voz vem logo depois
            pico = max(abs(int.from_bytes(quadros[i:i + 2], "little", signed=True))
                       for i in range(0, len(quadros), 2))
            self.assertLess(pico, 32767 * 0.86, nome)             # com folga: não distorce no celular
            self.assertGreater(pico, 32767 * (0.2 if nome == "toque" else 0.6), nome)

    def test_desligado_nao_toca_e_nunca_da_erro(self):
        s = sons.Sons("desligado")
        self.assertFalse(s.tocar("curva"))
        self.assertFalse(s.tocar(None))
        s.definir_volume("alto")
        self.assertEqual(s.volume, 1.0)
        self.assertFalse(s.tocar("som_que_nao_existe"))
        self.assertEqual(s.tocados, ["curva", "som_que_nao_existe"])


if __name__ == "__main__":
    unittest.main()
