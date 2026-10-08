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
import caminhos  # noqa: E402,F401  (as pastas do código no caminho de busca)
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
T9 = (-16.7105, -49.2970)


def resolver_falso(texto, perto=None, chave_tomtom=None, **k):
    """O endereço da loja cai no trecho certo (com o número); o "Rua 77" só acha a rua; o resto, nada."""
    PEDIDOS.append(texto)
    if "T9" in texto:
        return {"lugar": {"nome": "Av T9, 4724", "endereco": "Jardim Planalto", "lat": T9[0], "lon": T9[1]},
                "certo": True, "bairro": "Jardim Planalto"}
    if "Rua 77" in texto:
        return {"lugar": {"nome": "Rua 77, 10", "endereco": "Setor Central", "lat": -16.6700, "lon": -49.2560},
                "certo": False, "bairro": "Setor Central"}
    return None


busca.resolver_endereco = resolver_falso
busca.certeza = lambda lugares: None      # (a busca comum do teste nunca "tem certeza")
# (e responde na hora: a de verdade vai à internet e às vezes passava dos 3 s que o teste espera)
busca.buscar = lambda texto, perto=None, salvos=(), chave_tomtom=None, endereco=False: []


def app():
    return App.get_running_app()


def tela():
    return app().sm.get_screen("mapa")


def endereco(dt):
    """O endereço do print do dono (Instagram), com quadra, lote e CEP."""
    app().abrir_endereco("geo:0,0?q=Av%20T9%2C%204724%2C%20quadra%2032%2C%20lote%2007%2C%20Goi%C3%A2nia%2C%20Brazil%2074333-010")


def ver_endereco(dt):
    a, t = app(), tela()
    checar(PEDIDOS[:1] == ["Av T9, 4724, quadra 32, lote 07, Goiânia, Brazil 74333-010"],
           "o endereço vai INTEIRO para ser resolvido (com o CEP): %s" % PEDIDOS[:1])
    checar(t._marca == T9 and a.destino is None, "o pino aparece no ponto achado, ainda sem rota")
    checar(t.lbl_marca.text == "Av T9, 4724", "com o endereço no cartão: " + t.lbl_marca.text)
    checar("Confira o ponto" in t.lbl_msg.text, "e o pedido para conferir: " + t.lbl_msg.text)
    checar(t.card_marca.parent is not None, "cartão com Ir para cá à vista")
    Clock.schedule_once(lambda dt: foto("e0_conferir_o_ponto"), 1.3)


def corrigir(dt):
    """Está errado? Segurar o dedo no lugar certo muda o pino."""
    t = tela()
    t._ao_segurar(-16.7120, -49.2990)
    checar(t._marca == (-16.7120, -49.2990), "segurar o dedo em outro lugar move o pino")


def ir(dt):
    tela()._ir_marca()


def ver_ir(dt):
    a = app()
    checar(a.destino is not None and abs(a.destino["lat"] + 16.7120) < 1e-6, "Ir para cá calcula a rota até o ponto corrigido")
    checar(tela().estado == "previa", "prévia da rota aberta")


def outro(dt):
    """Chega outro endereço com uma prévia aberta: ele passa na frente. Só a rua foi achada."""
    app().abrir_endereco("geo:0,0?q=Rua%2077%2C%2010%2C%20Centro%2C%20Goi%C3%A2nia")


def ver_outro(dt):
    a, t = app(), tela()
    checar(a.destino is None and t.estado == "livre" and t._marca == (-16.6700, -49.2560),
           "a prévia antiga saiu e o pino novo entrou")
    checar("não o número" in t.lbl_msg.text, "avisa que achou só a rua: " + t.lbl_msg.text)
    foto("e1_so_a_rua")
    t._fechar_marca()


def ponto(dt):
    app().abrir_endereco("geo:0,0?q=-16.6853,-49.2662(Bosque%20dos%20Buritis)")


def ver_ponto(dt):
    t = tela()
    checar(t._marca == (-16.6853, -49.2662) and t.lbl_marca.text == "Bosque dos Buritis", "ponto exato com nome: pino e nome no cartão")
    t._fechar_marca()


def nada(dt):
    app().abrir_endereco("geo:0,0?q=Lugar%20Que%20Ninguem%20Conhece%2C%20Goi%C3%A2nia")


def ver_nada(dt):
    a = app()
    checar(a.sm.current == "busca" and "Lugar Que Ninguem Conhece" in a.sm.get_screen("busca").campo.text,
           "não achou: abre a busca com o texto (tela %s)" % a.sm.current)
    a.voltar()


def fora(dt):
    app().abrir_endereco("geo:-23.5614,-46.6559?q=Avenida+Paulista")


def ver_fora(dt):
    a = app()
    checar(tela()._marca is None and "fora de Goiânia" in tela().lbl_msg.text, "outra cidade: avisa e não marca nada")
    a.abrir_endereco("tel:123")
    checar(tela()._marca is None, "pedido que não é endereço é ignorado")


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


Clock.schedule_once(endereco, 7)
Clock.schedule_once(ver_endereco, 9)
Clock.schedule_once(corrigir, 11)
Clock.schedule_once(ir, 12)
Clock.schedule_once(ver_ir, 18)
Clock.schedule_once(outro, 19)
Clock.schedule_once(ver_outro, 21)
Clock.schedule_once(ponto, 22)
Clock.schedule_once(ver_ponto, 23.5)
Clock.schedule_once(nada, 24)
Clock.schedule_once(ver_nada, 27)
Clock.schedule_once(fora, 28)
Clock.schedule_once(ver_fora, 29)
Clock.schedule_once(navegando, 30)
Clock.schedule_once(ver_navegando, 40)
Clock.schedule_once(fim, 41)
runpy.run_path("main.py", run_name="__main__")
