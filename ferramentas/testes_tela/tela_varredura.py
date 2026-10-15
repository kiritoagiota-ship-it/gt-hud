"""Teste de TELA do GT-HUD (janela no 2º monitor): os consertos da varredura de 15/10/2026 que
só dá para conferir com o app de verdade. Rodar por ferramentas/testes_tela/rodar_todos.py.

- Voltar do Android com o Umbra aberto fecha ELE (antes, sem rota nem gravação, fechava o app);
- a falha atrasada de um pedido de rota VELHO não pinta de erro a prévia do destino novo;
- Umbra médio (chamado andando): a legenda ganha a placa escura por trás;
- a placa de vídeo recusa o desenho: ele aparece com as imagens prontas (antes ficava invisível);
- "Encerrar" (guardar_tudo_ao_fechar) não deixa etapa do Umbra marcada como "em curso"."""
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

RAIZ = os.path.dirname(os.path.dirname(PASTA))  # raiz do projeto
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
sys.path.insert(0, PASTA)
import caminhos  # noqa: E402,F401  (as pastas do código no caminho de busca)
sys.argv = ["main.py"]

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

import diagnostico  # noqa: E402
import rota_falsa  # noqa: E402
import tema  # noqa: E402
import umbra  # noqa: E402
import voz  # noqa: E402

rota_falsa.instalar()
ERROS = []


def falar_falso(self, pedacos, prioridade=1, texto=None):
    """Sem som no teste: a fala "dura" 1,2 s."""
    agora = time.monotonic()
    self._livre_em = agora + 1.2
    self._comecou(pedacos, None, agora, 1.2)


voz.Voz.falar = falar_falso


def checar(cond, texto):
    print("[CHECA]", "OK " if cond else "FALHOU", texto, flush=True)
    if not cond:
        ERROS.append(texto)


def foto(nome):
    Window.screenshot(name=os.path.join(FOTOS, nome + ".png"))
    print("[FOTO]", nome, flush=True)


def app():
    return App.get_running_app()


def rosto():
    return app().sm.get_screen("mapa").rosto_umbra


def voltar_fecha_o_umbra(dt):
    a = app()
    if a.posicao is None:
        a.posicao = (-16.6869, -49.2648)
    a.umbra.microfone = False
    a.velocidade_agora = lambda: 0.0
    a.umbra.chamar()
    checar(a.umbra.conversando and rosto().modo == "grande", "chamado: grande, conversando")
    tratou = a._tecla(Window, 27)
    checar(tratou is True, "Voltar com o Umbra aberto é tratado pelo app (não fecha o app)")
    checar(a.umbra.estado == umbra.OCULTO and rosto().modo is None, "Voltar fechou o Umbra")


def dois_destinos(dt):
    a = app()
    a.escolher_destino({"nome": "Destino A", "lat": -16.6990, "lon": -49.2580})
    global PEDIDO_A
    PEDIDO_A = a._pedido
    a.escolher_destino({"nome": "Destino B", "lat": -16.6950, "lon": -49.2700})


def falha_velha(dt):
    a = app()
    t = a.sm.get_screen("mapa")
    checar(a.rota_previa is not None and not t.btn_iniciar.disabled, "prévia do destino B pronta")
    a._rota_falhou(Exception("o servidor demorou"), PEDIDO_A)        # a falha atrasada do pedido A
    checar(not t.btn_iniciar.disabled, "a falha do pedido velho não desliga o Iniciar")
    checar(t.lbl_resumo.color != tema.VERMELHO, "nem pinta a prévia nova de vermelho")
    foto("v1_previa_nova_intacta")
    a.cancelar_previa()


def medio(dt):
    a = app()
    a.velocidade_agora = lambda: 25.0
    a.umbra.chamar()
    checar(rosto().modo == "medio", "andando: médio")


def medio_foto(dt):
    r = rosto()
    foto("v2_legenda_medio")
    checar(r._cor_placa.a > 0.5 and r._placa.size[0] > 0, "médio: a legenda tem a placa escura por trás (%.2f)"
           % r._cor_placa.a)
    checar(r._placa.pos[1] <= r.lbl_fala.center_y <= r._placa.pos[1] + r._placa.size[1],
           "a placa fica atrás do texto")
    app().umbra.fechar(calar=True)
    app().velocidade_agora = lambda: 0.0


def desenho_recusado(dt):
    r = rosto()
    r.fonte_propria = "void main() { este desenho nao compila }"
    r.recompilar()
    r.mostrar("grande")
    checar(r.simples and r.modo == "grande", "desenho recusado: cai para as imagens prontas")


def desenho_recusado_foto(dt):
    r = rosto()
    foto("v3_imagens_prontas")
    checar(r.presenca > 0.9 and r._ret_img.texture is not None, "e aparece (presença %.2f)" % r.presenca)
    r.esconder()


def encerrar_limpa(dt):
    r = rosto()
    r.fonte_propria = None
    r.simples = False
    r.recompilar()
    diagnostico.etapa("umbra_escuta")          # como se a escuta do nome estivesse no meio
    marca = os.path.join(diagnostico._pasta, "etapa_em_curso.txt")
    checar(os.path.exists(marca), "etapa marcada antes do Encerrar")
    app().guardar_tudo_ao_fechar()            # o que o "Encerrar" da notificação faz antes de matar o app
    checar(not os.path.exists(marca), "Encerrar não deixa etapa do Umbra marcada como em curso")


def fim(dt):
    print("[FIM] erros:", ERROS, flush=True)
    app().stop()


Clock.schedule_once(voltar_fecha_o_umbra, 7)
Clock.schedule_once(dois_destinos, 9)
Clock.schedule_once(falha_velha, 11)
Clock.schedule_once(medio, 12)
Clock.schedule_once(medio_foto, 13.4)
Clock.schedule_once(desenho_recusado, 15)
Clock.schedule_once(desenho_recusado_foto, 16.2)
Clock.schedule_once(encerrar_limpa, 17.5)
Clock.schedule_once(fim, 18.5)
runpy.run_path("main.py", run_name="__main__")
