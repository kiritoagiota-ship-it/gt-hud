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



from kivy.uix.popup import Popup  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402

E = {}


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def marcar(dt):
    app().salvos = []
    tela()._ao_segurar(-16.7000, -49.2700)
    checar(tela().card_marca.parent is not None, "cartao 'ponto marcado' aberto")
    foto("20_marcado")


def nomear(dt):
    tela()._pedir_nome()
    def preencher(dt):
        pop = [w for w in Window.children if isinstance(w, Popup)]
        checar(len(pop) == 1, "janela de nome aberta")
        campo = [w for w in pop[0].walk() if isinstance(w, TextInput)][0]
        campo.text = "Barbearia do amigo"
        salvar = [w for w in pop[0].walk() if getattr(w, "text", "") == "Salvar"][0]
        salvar.dispatch("on_release")
        checar(app().salvos and app().salvos[0]["nome"] == "Barbearia do amigo", "lugar salvo: %s" % app().salvos[:1])
    Clock.schedule_once(preencher, 0.5)


def busca_salvos(dt):
    app().abrir("busca")
    Clock.schedule_once(lambda dt: foto("21_busca_salvos"), 0.5)
    def buscar(dt):
        b = app().sm.get_screen("busca")
        b.campo.text = "amigo"
        b._buscar()
    Clock.schedule_once(buscar, 1.0)
    def conferir(dt):
        b = app().sm.get_screen("busca")
        checar(len(b.lista.children) >= 1, "busca 'amigo' achou o salvo: " + b.lbl_status.text)
        foto("22_busca_amigo")
    Clock.schedule_once(conferir, 3.0)


def destino(dt):
    app().escolher_destino({"nome": "Destino teste", "endereco": "", "lat": -16.7310, "lon": -49.3050})


def ver_rotas(dt):
    rs = app().rotas_previa
    print("[TESTE] rotas:", [(r.nome_perfil, int(r.total_m)) for r in rs], flush=True)
    checar(len(rs) >= 2, "varias rotas na previa (%d)" % len(rs))
    foto("23_rotas_previa")
    if len(rs) >= 2:
        app().escolher_rota_previa(rs[1])
        checar(app().rota_previa is rs[1], "escolheu a 2a rota")
        Clock.schedule_once(lambda dt: foto("24_outra_rota"), 0.5)


def navegar(dt):
    app().iniciar_navegacao()
    sim = app().gps._sim
    original = sim._tick
    sim._ev.cancel()
    sim._ev = Clock.schedule_interval(lambda dt: original(dt * 3), 1 / 3.0)
    print("[TESTE] alertas na rota:", app().nav.alertas[:8], flush=True)


def ver_nav(dt):
    m = tela().mapa
    checar(len(m._sinais) > 0 or m.zoom < 15, "icones de semaforo/lombada no mapa (%d)" % len(m._sinais))
    foto("25_navegando")


def rotas_nav(dt):
    app().calcular_rotas_navegando()
    Clock.schedule_once(lambda dt: foto("26_calculando"), 0.3)


def ver_rotas_nav(dt):
    esc = tela()._escolha_nav
    checar(isinstance(esc, tuple), "rotas calculadas na navegacao: %s" % (len(esc[0]) if isinstance(esc, tuple) else esc))
    foto("27_rotas_nav")
    Clock.schedule_once(lambda dt: tela()._usar_escolhida(), 1.0)


def ajustes(dt):
    app().abrir("config")
    def fim_lista(dt):
        c = app().sm.get_screen("config")
        rol = [w for w in c.walk() if w.__class__.__name__ == "ScrollView"][0]
        rol.scroll_y = 0
        Clock.schedule_once(lambda dt: foto("28_ajustes_fim"), 0.4)
        c._baixar_offline()
        E["t0"] = time.time()
    Clock.schedule_once(fim_lista, 0.6)


def esperar_offline(dt):
    c = app().sm.get_screen("config")
    txt = c.linha_offline.explicacao.text
    if txt.startswith("Pronto") or txt.startswith("Faltaram") or time.time() - E["t0"] > 240:
        print("[TESTE] offline: %s (%.0f s)" % (txt, time.time() - E["t0"]), flush=True)
        checar(txt.startswith("Pronto"), "mapa offline baixado")
        foto("29_offline")
        Clock.schedule_once(fim, 1)
        return False


def fim(dt):
    print("[FIM] falas:", FALAS[-6:], "erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(marcar, 6)
Clock.schedule_once(nomear, 7)
Clock.schedule_once(busca_salvos, 9)
Clock.schedule_once(destino, 14)
Clock.schedule_once(ver_rotas, 26)
Clock.schedule_once(navegar, 29)
Clock.schedule_once(ver_nav, 40)
Clock.schedule_once(rotas_nav, 41)
Clock.schedule_once(ver_rotas_nav, 53)
Clock.schedule_once(ajustes, 57)
Clock.schedule_once(lambda dt: Clock.schedule_interval(esperar_offline, 1), 59)
runpy.run_path("main.py", run_name="__main__")
