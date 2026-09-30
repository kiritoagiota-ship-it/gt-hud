"""Tela principal: velocímetro, números da viagem e controles."""
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen

import tema
from util import fmt_dist, fmt_tempo, fmt_vel
from viagem import Viagem
from widgets.botao import BotaoHUD
from widgets.comuns import Bloco, Ponto, Texto, soltar
from widgets.velocimetro import Velocimetro

SEM_SINAL_APOS_S = 5


class TelaHUD(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._t_ultima_valida = 0
        self._ev_relogio = None
        self._ev_msg = None
        self._deitada = None
        self._estado_visto = None

        self.raiz = BoxLayout(padding=tema.MARGEM, spacing=dp(10))

        # topo: status do GPS + navegação
        self.topo = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        self.ponto = Ponto(pos_hint={"center_y": 0.5})
        self.topo.add_widget(self.ponto)
        self.lbl_gps = Texto(text="Procurando sinal", font_size=tema.T_ROTULO + 1,
                             color=tema.CIANO_FRACO)
        self.topo.add_widget(self.lbl_gps)
        self.topo.add_widget(BotaoHUD(text="Viagens", size_hint_x=None, width=dp(92),
                                      font_size=tema.T_ROTULO + 1,
                                      on_release=lambda *a: self._ir("viagens")))
        self.topo.add_widget(BotaoHUD(text="Ajustes", size_hint_x=None, width=dp(92),
                                      font_size=tema.T_ROTULO + 1,
                                      on_release=lambda *a: self._ir("config")))

        # velocímetro
        self.velo = Velocimetro()

        # mensagem curta (ex.: "Viagem salva")
        self.lbl_msg = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.VERDE,
                             halign="center", size_hint_y=None, height=dp(20))

        # números
        self.grade = GridLayout(cols=2, spacing=dp(8))
        self.b_max = Bloco(rotulo="Maxima (km/h)", valor="0")
        self.b_med = Bloco(rotulo="Media (km/h)", valor="0")
        self.b_dist = Bloco(rotulo="Distancia", valor="0 m")
        self.b_tempo = Bloco(rotulo="Tempo", valor="00:00")
        for b in (self.b_max, self.b_med, self.b_dist, self.b_tempo):
            self.grade.add_widget(b)

        # controles
        self.controles = BoxLayout(size_hint_y=None, height=dp(62), spacing=dp(10))

        self.add_widget(self.raiz)
        self.bind(size=self._organizar)
        self._montar_controles()

    def _organizar(self, *a):
        """Em pé: tudo empilhado. Deitada: velocímetro grande à esquerda e
        o resto numa coluna à direita."""
        deitada = self.width > self.height
        if deitada == self._deitada:
            return
        self._deitada = deitada
        soltar(self.topo, self.velo, self.lbl_msg, self.grade, self.controles)
        self.raiz.clear_widgets()
        if deitada:
            self.raiz.orientation = "horizontal"
            self.velo.size_hint_x = 0.48
            self.grade.size_hint_y = 1
            coluna = BoxLayout(orientation="vertical", spacing=dp(8))
            for w in (self.topo, self.lbl_msg, self.grade, self.controles):
                coluna.add_widget(w)
            self.raiz.add_widget(self.velo)
            self.raiz.add_widget(coluna)
        else:
            self.raiz.orientation = "vertical"
            self.velo.size_hint_x = 1
            self.grade.size_hint_y = None
            self.grade.height = dp(190)
            for w in (self.topo, self.velo, self.lbl_msg, self.grade, self.controles):
                self.raiz.add_widget(w)

    # --- ciclo de vida ---------------------------------------------------
    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if not getattr(self, "_ouvindo", False):
            app.ouvir(self._ao_ler)
            self._ouvindo = True
        self.velo.limite = app.ajustes["limite_kmh"]
        self._montar_controles()
        self._atualizar_numeros()
        if self._ev_relogio is None:
            self._ev_relogio = Clock.schedule_interval(self._tique, 1.0)

    def on_leave(self, *a):
        if self._ev_relogio is not None:
            self._ev_relogio.cancel()
            self._ev_relogio = None

    # --- dados do GPS ----------------------------------------------------
    def _ao_ler(self, vel):
        app = App.get_running_app()
        if vel is None:  # leitura descartada por baixa precisão
            self._status_gps()
            return
        self._t_ultima_valida = time.time()
        self.velo.velocidade = vel
        self.velo.alerta = vel > app.ajustes["limite_kmh"]
        self._status_gps()
        if app.viagem.estado != self._estado_visto:
            # quem mudou foi a pausa automática (os botões já remontam sozinhos)
            if app.viagem.estado == Viagem.PAUSADA:
                self._mensagem("Pausa automatica: parado", tema.LARANJA)
            else:
                self._mensagem("Andando de novo: gravando", tema.CIANO)
            self._montar_controles()
        self._atualizar_numeros()

    def _tique(self, dt):
        self._status_gps()
        self._atualizar_numeros()

    def _status_gps(self):
        app = App.get_running_app()
        sem_sinal = time.time() - self._t_ultima_valida > SEM_SINAL_APOS_S
        if app.gps_desligado:
            self.ponto.cor = tema.VERMELHO
            self.lbl_gps.text = "GPS do celular desligado"
        elif app.gps.modo == "SIM":
            self.ponto.cor = tema.LARANJA
            self.lbl_gps.text = "Simulador  %d m" % (app.precisao or 0)
        elif sem_sinal:
            self.ponto.cor = tema.VERMELHO
            self.lbl_gps.text = "Sem sinal"
            self.velo.velocidade = 0
            self.velo.alerta = False
        else:
            prec = app.precisao or 0
            self.ponto.cor = tema.VERDE if prec <= 10 else tema.LARANJA
            self.lbl_gps.text = "GPS  %d m" % prec

    def _atualizar_numeros(self):
        v = App.get_running_app().viagem
        self.b_max.valor = fmt_vel(v.vel_max_kmh)
        self.b_med.valor = fmt_vel(v.vel_media_kmh)
        self.b_dist.valor = fmt_dist(v.distancia_m)
        self.b_tempo.valor = fmt_tempo(v.tempo_total_s)
        self.b_tempo.cor_acento = tema.LARANJA if v.estado == Viagem.PAUSADA else tema.CIANO

    # --- controles da viagem ---------------------------------------------
    def _montar_controles(self):
        v = App.get_running_app().viagem
        self._estado_visto = v.estado
        c = self.controles
        c.clear_widgets()
        if v.estado == Viagem.PARADA:
            c.add_widget(BotaoHUD(text="Iniciar viagem", destaque=True,
                                  on_release=lambda *a: self._iniciar()))
        elif v.estado == Viagem.GRAVANDO:
            c.add_widget(BotaoHUD(text="Pausar", on_release=lambda *a: self._pausar()))
            c.add_widget(BotaoHUD(text="Finalizar", cor=tema.LARANJA,
                                  on_release=lambda *a: self._finalizar()))
        else:
            c.add_widget(BotaoHUD(text="Retomar", destaque=True,
                                  on_release=lambda *a: self._retomar()))
            c.add_widget(BotaoHUD(text="Finalizar", cor=tema.LARANJA,
                                  on_release=lambda *a: self._finalizar()))

    def _iniciar(self):
        App.get_running_app().viagem.iniciar()
        self._mensagem("Gravando viagem", tema.CIANO)
        self._montar_controles()
        self._atualizar_numeros()

    def _pausar(self):
        App.get_running_app().viagem.pausar()
        self._mensagem("Viagem pausada", tema.LARANJA)
        self._montar_controles()
        self._atualizar_numeros()  # acento do Tempo fica laranja na hora

    def _retomar(self):
        App.get_running_app().viagem.retomar()
        self._mensagem("Gravando viagem", tema.CIANO)
        self._montar_controles()
        self._atualizar_numeros()

    def _finalizar(self):
        app = App.get_running_app()
        vid = app.salvar_viagem_atual()
        if vid:
            self._mensagem("Viagem salva: %s" % fmt_dist(app.ultima_salva_m), tema.VERDE)
        else:
            # antes sumia calada: parecia que o botao nao tinha funcionado
            self._mensagem("Viagem muito curta: nao foi salva", tema.LARANJA)
        self._montar_controles()
        self._atualizar_numeros()

    def _mensagem(self, texto, cor):
        self.lbl_msg.text = texto
        self.lbl_msg.color = cor
        if self._ev_msg:
            self._ev_msg.cancel()
        self._ev_msg = Clock.schedule_once(lambda dt: setattr(self.lbl_msg, "text", ""), 3)

    def _ir(self, nome):
        self.manager.current = nome
