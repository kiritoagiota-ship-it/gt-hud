"""Teste de TELA do GT-HUD (janela no 2º monitor). Rodar por
ferramentas/testes_tela/rodar_todos.py (que isola APPDATA/KIVY_HOME)."""
import os
import runpy
import sys
import time

from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")
Config.set("graphics", "position", "custom")
Config.set("graphics", "left", "2400")   # DISPLAY2 começa em x=1920
Config.set("graphics", "top", "60")
Config.set("input", "mouse", "mouse,disable_multitouch")

PASTA = os.path.dirname(os.path.abspath(__file__))
FOTOS = os.path.join(PASTA, "fotos")
os.makedirs(FOTOS, exist_ok=True)
for f in os.listdir(FOTOS):
    os.remove(os.path.join(FOTOS, f))

RAIZ = os.path.dirname(os.path.dirname(PASTA))  # raiz do projeto
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
sys.argv = ["main.py"]

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.metrics import dp  # noqa: E402

import voz  # noqa: E402
import widgets.mapa as wmapa  # noqa: E402

FALAS = []


def falar_falso(self, pedacos, prioridade=1, texto=None):
    import falas
    frase = texto or falas.frase([p for p in pedacos if p in falas.FALAS])
    FALAS.append(frase)
    print("[FALA]", frase, flush=True)


voz.Voz.falar = falar_falso
wmapa.VOLTA_A_SEGUIR_S = 4.0  # no teste: volta a seguir mais rápido
ERROS = []


def foto(nome):
    """Desenha o app numa imagem fora da tela (Fbo): sai sempre o quadro
    inteiro, sem a sobreposicao de monitoramento do PC por cima."""
    def tirar(dt):
        from PIL import Image
        caminho = os.path.join(FOTOS, nome + ".png")
        App.get_running_app().root.export_to_png(caminho)
        img = Image.open(caminho).convert("RGBA")
        fundo = Image.new("RGBA", img.size, (4, 7, 11, 255))  # Window.clearcolor do app
        Image.alpha_composite(fundo, img).convert("RGB").save(caminho)
        print("[FOTO]", nome, flush=True)
    Clock.schedule_once(tirar, 0)


def checar(cond, texto):
    print("[CHECA]", "OK " if cond else "FALHOU", texto, flush=True)
    if not cond:
        ERROS.append(texto)




import tema  # noqa: E402


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def destino(dt):
    app().ajustes["rota_preferida"] = "rapida"
    app().escolher_destino({"nome": "Setor Sudoeste", "endereco": "", "lat": -16.7200, "lon": -49.2950})


def navegar(dt):
    a = app()
    rota = a.rota_previa
    checar(rota is not None, "rota calculada")
    # (o limite da via vem do servidor quando ele sabe; no teste, um limite certo no caminho todo)
    rota.limites = [(0.0, rota.total_m * 0.5, 40), (rota.total_m * 0.5, rota.total_m, 60)]
    a.iniciar_navegacao()


def ver(dt):
    a, t = app(), tela()
    m = t.mapa
    e = a.estado_nav
    checar(e is not None and e.get("limite_via") == 40, "a navegação sabe o limite da via: %s" % (e or {}).get("limite_via"))
    checar(t.placa_limite.parent is not None and t.placa_limite.numero.text == "40", "placa de 40 ao lado do velocímetro")
    checar(t._limite_do_alerta() == min(a.ajustes["limite_kmh"], 43), "o velocímetro avisa pelo limite da via (+3): %s" % t._limite_do_alerta())
    checar(len(m._curva) >= 2 and len(m._g_curva.children) >= 6, "seta da próxima curva desenhada no chão (%d pontos)" % len(m._curva))
    checar(len(m._rastro) >= 3, "rastro atrás da seta: %d pontos" % len(m._rastro))
    checar(abs(m._e_halo.size[0] - dp(44)) > 0.01 or m._c_halo.a != 0.30, "o halo da seta respira")
    placas = [r for r in m._rotulos if r.placa is not None]
    print("[TESTE] nomes em placa:", [r.info["texto"] for r in placas], flush=True)
    foto("s0_navegando")


def alerta(dt):
    """O próximo semáforo/lombada/radar do caminho, como se estivesse chegando."""
    a, t = app(), tela()
    m = t.mapa
    nav = a.nav
    proximo = next(((d, tipo) for d, tipo in nav.alertas if d > nav.dist_feita + 20), None)
    if proximo is None:
        print("[TESTE] sem semáforo/lombada/radar à frente nesta rota", flush=True)
        return
    onde = nav.rota.ponto_em(proximo[0])[:2]
    m.seguindo = False
    m.centro = onde
    m._aplicar()
    m._escolher_sinais()
    T["sinalizar"] = t._sinalizar
    t._sinalizar = lambda e: None     # (senão a navegação de verdade apaga o destaque do teste na leitura seguinte)
    m.destacar_alerta(onde, tema.VERMELHO)
    grandes = [s for s in m._sinais if abs(s[3].x - 1.4) < 0.01]
    checar(m._destaque is not None, "alerta chegando destacado (%s)" % proximo[1])
    checar(len(grandes) >= 1, "a placa dele cresceu (%d de %d ícones)" % (len(grandes), len(m._sinais)))
    T["destaque"] = True
    Clock.schedule_once(lambda dt: foto("s1_alerta_pulsando"), 0.4)


def ver_pulso(dt):
    m = tela().mapa
    if T.get("destaque"):
        checar(m._m_pulso in m._visiveis and any(c.a > 0.02 for c, _ in m._pulso), "anel pulsando em volta da placa")
        m.destacar_alerta(None)
        checar(all(abs(s[3].x - 1.0) < 0.01 for s in m._sinais) and m._m_pulso not in m._visiveis, "passou: placa e anel voltam ao normal")
    m.seguindo = True
    if T.get("sinalizar"):
        tela()._sinalizar = T["sinalizar"]


def avenida(dt):
    """Numa avenida grande, parado e de perto: o nome vem dentro da plaquinha."""
    a = app()
    a.encerrar_navegacao()
    m = tela().mapa
    m.seguindo = False
    m.centro = (-16.7020, -49.2740)      # Avenida T-9 / T-63, Setor Bueno
    m.zoom = 16.2
    m._aplicar()


def ver_avenida(dt):
    m = tela().mapa
    placas = [r for r in m._rotulos if r.placa is not None]
    soltos = [r for r in m._rotulos if r.info.get("tipo") == "rua" and r.placa is None]
    print("[TESTE] em placa: %s | soltos: %d" % ([r.info["texto"] for r in placas], len(soltos)), flush=True)
    checar(len(placas) >= 1, "avenida com o nome em placa: %s" % [r.info["texto"] for r in placas][:3])
    checar(all(r.info["peso"] >= 5 for r in placas) and all(r.info["peso"] < 5 for r in soltos), "só as vias principais ganham placa")
    checar(tela().placa_limite.parent is None and not m._curva and len(m._g_curva.children) == 0,
           "fora da navegação: sem placa de limite e sem seta de curva")
    foto("s2_placas_de_avenida")


def trocar_tema(dt):
    a = app()
    T["tema"] = tema.modo
    a.trocar_tema("claro" if tema.modo == "escuro" else "escuro")
    capa = getattr(a, "_capa_tema", None)
    checar(tema.modo != T["tema"], "tema trocado: %s -> %s" % (T["tema"], tema.modo))
    checar(capa is not None and capa.parent is not None and capa.opacity > 0.9, "a tela antiga fica por cima e vai se dissolvendo")
    Clock.schedule_once(lambda dt: foto("s3_meio_da_troca"), 0.6)


def ver_tema(dt):
    a = app()
    capa = getattr(a, "_capa_tema", None)
    checar(capa is not None and capa.parent is None, "a dissolução terminou e a foto saiu de cima")
    a.trocar_tema(T["tema"])


T = {}


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(destino, 7)
Clock.schedule_once(navegar, 14)
Clock.schedule_once(ver, 22)
Clock.schedule_once(alerta, 23)
Clock.schedule_once(ver_pulso, 24.5)
Clock.schedule_once(avenida, 25.5)
Clock.schedule_once(ver_avenida, 29)
Clock.schedule_once(trocar_tema, 30)
Clock.schedule_once(ver_tema, 32.5)
Clock.schedule_once(fim, 35)
runpy.run_path("main.py", run_name="__main__")
