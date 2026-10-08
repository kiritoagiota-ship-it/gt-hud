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




import busca  # noqa: E402

PEDIDOS = []
_buscar = busca.buscar


def buscar_falso(texto, perto=None, salvos=(), chave_tomtom=None, endereco=False):
    """A busca do teste: o endereço da loja a TomTom "acha com o número"; o outro fica em dúvida."""
    PEDIDOS.append((texto, endereco))
    if "T9" in texto:
        return [{"nome": "Avenida T-9, 4724", "endereco": "Jardim América, Goiânia", "lat": -16.7061, "lon": -49.2780,
                 "fonte": "TomTom", "exato": True, "nota": 51, "dist_m": 3000},
                {"nome": "Av. T 9 (01245)", "endereco": "Setor Marista", "lat": -16.6978, "lon": -49.2664,
                 "fonte": "mapa aberto", "nota": 15, "dist_m": 2000}]
    if "Rua 10" in texto:
        return [{"nome": "Rua 10", "endereco": "Setor Oeste", "lat": -16.6850, "lon": -49.2650, "fonte": "mapa aberto",
                 "nota": 15, "dist_m": 900},
                {"nome": "Rua 10", "endereco": "Setor Universitário", "lat": -16.6790, "lon": -49.2400,
                 "fonte": "mapa aberto", "nota": 15, "dist_m": 1700}]
    return _buscar(texto, perto, salvos, chave_tomtom)


busca.buscar = buscar_falso


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def ponto(dt):
    """Outro app mandou um ponto exato com nome."""
    app().abrir_endereco("geo:0,0?q=-16.6853,-49.2662(Bosque%20dos%20Buritis)")


def ver_ponto(dt):
    a = app()
    checar(a.destino is not None and a.destino["nome"] == "Bosque dos Buritis", "ponto recebido vira destino: %s" % (a.destino or {}).get("nome"))
    checar(a.sm.current == "mapa" and tela().estado == "previa", "já na prévia da rota")
    checar(a.rota_previa is not None, "rota calculada até o ponto recebido")
    foto("e0_ponto_recebido")
    a.cancelar_previa()


def endereco(dt):
    """O endereço do print do dono (Instagram): a TomTom acha com o número -> direto para a rota."""
    app().abrir_endereco("geo:0,0?q=Av%20T9%2C%204724%2C%20quadra%2032%2C%20lote%2007%2C%20Goi%C3%A2nia%2C%20Brazil%2074333-010")


def ver_endereco(dt):
    a = app()
    checar(PEDIDOS and PEDIDOS[0] == ("Av T9, 4724, Goiânia", True), "buscou o endereço limpo, como endereço: %s" % PEDIDOS[:1])
    checar(a.destino is not None and a.destino["nome"] == "Avenida T-9, 4724", "foi direto para o endereço com número: %s"
           % (a.destino or {}).get("nome"))
    checar(tela().estado == "previa" and a.rota_previa is not None, "prévia da rota até lá")
    foto("e1_endereco_recebido")
    a.cancelar_previa()


def duvida(dt):
    app().abrir_endereco("geo:0,0?q=Rua%2010%2C%20Goi%C3%A2nia")


def ver_duvida(dt):
    a = app()
    b = a.sm.get_screen("busca")
    checar(a.sm.current == "busca", "dois lugares possíveis: abriu a busca para escolher (tela %s)" % a.sm.current)
    checar(b.campo.text == "Rua 10, Goiânia", "com o endereço já digitado: " + b.campo.text)
    checar(len(b.lista.children) >= 2, "e as opções na lista: %d" % len(b.lista.children))
    foto("e2_em_duvida")
    a.voltar()


def fora(dt):
    app().abrir_endereco("geo:-23.5614,-46.6559?q=Avenida+Paulista")


def ver_fora(dt):
    a = app()
    checar(a.destino is None and "fora de Goiânia" in tela().lbl_msg.text, "endereço de outra cidade: avisa e não calcula: " + tela().lbl_msg.text)
    app().abrir_endereco("tel:123")          # o que não é endereço não faz nada (nem erro)
    checar(a.destino is None, "pedido que não é endereço é ignorado")


def navegando(dt):
    a = app()
    a.escolher_destino({"nome": "Bosque dos Buritis", "endereco": "", "lat": -16.6853, "lon": -49.2662})
    Clock.schedule_once(lambda dt: a.iniciar_navegacao(), 6)
    Clock.schedule_once(lambda dt: a.abrir_endereco("geo:-16.70,-49.27"), 8)


def ver_navegando(dt):
    a = app()
    checar(a.nav is not None and a.destino["nome"] == "Bosque dos Buritis", "navegando, o destino NÃO é trocado sozinho")
    checar("Encerre a rota" in tela().lbl_msg.text, "e avisa: " + tela().lbl_msg.text)


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(ponto, 7)
Clock.schedule_once(ver_ponto, 13)
Clock.schedule_once(endereco, 14)
Clock.schedule_once(ver_endereco, 20)
Clock.schedule_once(duvida, 21)
Clock.schedule_once(ver_duvida, 24)
Clock.schedule_once(fora, 25)
Clock.schedule_once(ver_fora, 26)
Clock.schedule_once(navegando, 27)
Clock.schedule_once(ver_navegando, 37)
Clock.schedule_once(fim, 38)
runpy.run_path("main.py", run_name="__main__")
