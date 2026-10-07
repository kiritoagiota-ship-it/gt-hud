"""Tela principal: velocímetro, números da viagem e controles."""
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

# sem sinal bom por esse tempo, aparece a dica de ir para um lugar aberto
DICA_APOS_S = 30
DICA_FECHADO = "GPS não pega em lugar fechado. Vá para uma área aberta."
DICA_DESLIGADO = "Ligue a Localização do celular (no painel de cima)."
DICAS = (DICA_FECHADO, DICA_DESLIGADO)


class TelaHUD(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._ev_relogio = None
        self._ev_msg = None
        self._deitada = None
        self._estado_visto = None

        self.raiz = BoxLayout(padding=tema.MARGEM, spacing=dp(10))

        # topo: status do GPS + navegação
        self.topo = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        self.ponto = Ponto(pos_hint={"center_y": 0.5})
        self.topo.add_widget(self.ponto)
        self.lbl_gps = Texto(text="Buscando GPS", font_size=tema.T_ROTULO + 1,
                             color=tema.CIANO_FRACO)
        self.topo.add_widget(self.lbl_gps)
        self.topo.add_widget(BotaoHUD(text="Mapa", size_hint_x=None, width=dp(92),
                                      font_size=tema.T_ROTULO + 1,
                                      on_release=lambda *a: App.get_running_app().voltar()))
        self.topo.add_widget(BotaoHUD(text="Ajustes", size_hint_x=None, width=dp(92),
                                      font_size=tema.T_ROTULO + 1,
                                      on_release=lambda *a: self._ir("config")))

        # velocímetro
        self.velo = Velocimetro()

        # mensagem curta (ex.: "Viagem salva") ou a dica de sem GPS; cabem
        # 2 linhas, para a dica não vazar em celular estreito
        self.lbl_msg = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.VERDE,
                             halign="center", size_hint_y=None, height=dp(36))

        # números
        self.grade = GridLayout(cols=2, spacing=dp(8))
        self.b_max = Bloco(rotulo="Máxima (km/h)", valor="0")
        self.b_med = Bloco(rotulo="Média (km/h)", valor="0")
        self.b_dist = Bloco(rotulo="Distância", valor="0 m")
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
        if getattr(self, "_ev_velo", None) is None:
            self._ev_velo = Clock.schedule_interval(self._passo_velo, 0.2)

    def on_leave(self, *a):
        if self._ev_relogio is not None:
            self._ev_relogio.cancel()
            self._ev_relogio = None
        if getattr(self, "_ev_velo", None) is not None:
            self._ev_velo.cancel()
            self._ev_velo = None

    def _passo_velo(self, dt):
        """Entre uma leitura e outra do GPS o número segue a tendência."""
        app = App.get_running_app()
        v = app.velocidade_agora()
        if abs(v - self.velo.velocidade) >= 0.2:
            self.velo.velocidade = v
            self.velo.alerta = v > app.ajustes["limite_kmh"]

    # --- dados do GPS ----------------------------------------------------
    def _ao_ler(self, vel):
        app = App.get_running_app()
        if vel is None:  # leitura descartada por baixa precisão
            self._status_gps()
            return
        self.velo.velocidade = vel
        self.velo.alerta = vel > app.ajustes["limite_kmh"]
        self._status_gps()
        if app.viagem.estado != self._estado_visto:
            # quem mudou foi a pausa automática (os botões já remontam sozinhos)
            if app.viagem.estado == Viagem.PAUSADA:
                self._mensagem("Pausa automática: parado", tema.LARANJA)
            else:
                self._mensagem("Andando de novo: gravando", tema.CIANO)
            self._montar_controles()
        self._atualizar_numeros()

    def _tique(self, dt):
        self._status_gps()
        self._atualizar_numeros()

    def _status_gps(self):
        """Bolinha + texto do GPS. Antes só existia "Sem sinal" (vermelho) até
        o 1º sinal bom: parecia quebrado dentro de casa, onde o GPS de
        satélite não pega. Agora diz se está buscando (e quantos satélites
        vê), se o sinal está fraco ou se perdeu o sinal que tinha."""
        app = App.get_running_app()
        sat = app.gps.satelites()  # (vistos, em uso) ou None
        dica = None
        if app.gps_desligado:
            cor, texto = tema.VERMELHO, "GPS do celular\ndesligado"
            dica = DICA_DESLIGADO
        elif app.gps.modo == "SIM":
            cor, texto = tema.LARANJA, "Simulador  %d m" % (app.precisao or 0)
        elif app.sinal_ok():
            prec = app.precisao or 0
            cor = tema.VERDE if prec <= 10 else tema.LARANJA
            texto = "GPS  %d m" % prec
            if sat and sat[1]:
                texto += "\n%d satélites" % sat[1]
        else:
            if app.sinal_fraco():
                cor, texto = tema.LARANJA, "Sinal fraco: %d m" % (app.precisao_ultima or 0)
            elif app.ja_teve_sinal:
                cor, texto = tema.VERMELHO, "Sem sinal do GPS"
            else:
                cor, texto = tema.LARANJA, "Buscando GPS"
            if sat and sat[0]:
                # "em uso" > 0 aqui = o GPS já calculou a posição e ela não
                # chegou ao app (foi assim que se achou o bug do Android 12+)
                texto += "\n%d vistos, %d em uso" % sat
            if app.segundos_sem_sinal() > DICA_APOS_S:
                dica = DICA_FECHADO
        if not app.sinal_ok():
            self.velo.velocidade = 0
            self.velo.alerta = False
        self.ponto.cor = cor
        self.lbl_gps.text = texto
        self._mostrar_dica(dica)

    def _mostrar_dica(self, dica):
        # a dica fica parada no lugar das mensagens curtas, sem apagar sozinha;
        # uma mensagem curta (ex.: "Viagem salva") passa na frente
        livre = not self.lbl_msg.text or self.lbl_msg.text in DICAS
        if dica and livre:
            self.lbl_msg.text = dica
            self.lbl_msg.color = tema.LARANJA
        elif not dica and self.lbl_msg.text in DICAS:
            self.lbl_msg.text = ""

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
            # a viagem grava sozinha em toda rota iniciada (e só nelas)
            c.add_widget(Texto(text="Toda rota iniciada é gravada sozinha. Busque um destino no mapa.",
                               font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO, halign="center"))
        else:
            # sem Pausar/Finalizar na mão: a viagem é a rota. Ela pausa sozinha
            # parada (se a pausa automática está ligada) e é salva ao chegar
            # ou ao encerrar a rota no mapa. (Antes dava para "Finalizar" aqui
            # no meio da rota e a viagem ficava cortada.)
            pausada = v.estado == Viagem.PAUSADA
            c.add_widget(Texto(text="Pausada: você está parado. Volta ao andar." if pausada
                               else "Gravando esta rota. Salva sozinha ao chegar ou encerrar.",
                               font_size=tema.T_ROTULO + 1, halign="center",
                               color=tema.LARANJA if pausada else tema.CIANO_FRACO))
            c.add_widget(BotaoHUD(text="Ver no mapa", size_hint_x=0.6,
                                  on_release=lambda *a: self._ir("mapa")))

    def _mensagem(self, texto, cor):
        self.lbl_msg.text = texto
        self.lbl_msg.color = cor
        if self._ev_msg:
            self._ev_msg.cancel()
        self._ev_msg = Clock.schedule_once(lambda dt: setattr(self.lbl_msg, "text", ""), 3)

    def _ir(self, nome):
        App.get_running_app().abrir(nome)
