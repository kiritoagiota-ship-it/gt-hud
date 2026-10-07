"""Ajustes: voz, subidas e giro do mapa (navegação), alerta de velocidade,
vibração, pausa automática, orientação, tela ligada, suavização e simulador."""

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

import tema
from widgets.botao import BotaoHUD
from widgets.comuns import Cabecalho, Texto


def _texto_que_cresce(texto, **kw):
    """Label com quebra de linha cuja ALTURA acompanha o texto (com a fonte
    do celular maior, a explicação de 3 linhas invadia a linha de baixo)."""
    lbl = Label(text=texto, halign="left", valign="top", size_hint_y=None, **kw)
    lbl.bind(width=lambda l, w: setattr(l, "text_size", (w, None)),
             texture_size=lambda l, t: setattr(l, "height", t[1]))
    return lbl


class Linha(BoxLayout):
    """Título + explicação à esquerda, controle à direita (centralizado na
    altura). A linha cresce até caber o texto."""
    ALTURA_MIN = dp(80)

    def __init__(self, titulo, explicacao, controle, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", self.ALTURA_MIN)
        kw.setdefault("spacing", dp(10))
        super().__init__(**kw)
        textos = BoxLayout(orientation="vertical", spacing=dp(3), padding=(0, dp(10)))
        self.titulo = _texto_que_cresce(titulo, font_size=tema.T_BOTAO, bold=True, color=tema.BRANCO)
        self.explicacao = _texto_que_cresce(explicacao, font_size=tema.T_ROTULO, color=tema.CIANO_FRACO)
        textos.add_widget(self.titulo)
        textos.add_widget(self.explicacao)
        textos.add_widget(Widget())  # sobra embaixo, não no meio
        for lbl in (self.titulo, self.explicacao):
            lbl.bind(height=self._ajustar)
        ancora = AnchorLayout(size_hint_x=None, width=controle.width, anchor_y="center")
        controle.size_hint_y = None
        controle.height = dp(50)
        ancora.add_widget(controle)
        self.add_widget(textos)
        self.add_widget(ancora)

    def _ajustar(self, *a):
        self.height = max(self.ALTURA_MIN, self.titulo.height + self.explicacao.height + dp(26))


class Seletor(BoxLayout):
    """[-] valor [+]"""

    def __init__(self, formato, ao_mudar, **kw):
        kw.setdefault("size_hint_x", None)
        kw.setdefault("width", dp(192))
        kw.setdefault("spacing", dp(4))
        super().__init__(**kw)
        self.formato = formato
        self.ao_mudar = ao_mudar
        self.add_widget(BotaoHUD(text="-", size_hint_x=None, width=dp(44),
                                 on_release=lambda *a: self.ao_mudar(-1)))
        # o valor ("32 km/h", "gravada") ficava por baixo dos botões com a fonte grande
        self.lbl = Label(font_size=tema.T_BOTAO, bold=True, color=tema.BRANCO,
                         halign="center", valign="middle", shorten=True, shorten_from="right")
        self.lbl.bind(size=lambda l, s: setattr(l, "text_size", s))
        self.add_widget(self.lbl)
        self.add_widget(BotaoHUD(text="+", size_hint_x=None, width=dp(44),
                                 on_release=lambda *a: self.ao_mudar(+1)))

    def mostrar(self, valor):
        self.lbl.text = self.formato % valor


class Alternar(BotaoHUD):
    def __init__(self, ao_mudar, **kw):
        kw.setdefault("size_hint_x", None)
        kw.setdefault("width", dp(130))
        super().__init__(**kw)
        self.ao_mudar = ao_mudar
        self.bind(on_release=lambda *a: self.ao_mudar(not self.destaque))

    def mostrar(self, ligado):
        self.destaque = bool(ligado)
        self.text = "Ligado" if ligado else "Desligado"


# As opções, agrupadas (eram mais de 20 linhas soltas, na ordem em que
# foram sendo criadas): seção -> títulos das linhas, na ordem da tela.
SECOES = [
    ("Voz", ["Voz do assistente", "Qual voz", "Tom da voz", "Efeito de IA", "Testar a voz"]),
    ("Navegação", ["Rota preferida", "Trânsito ao vivo", "Aviso de chuva", "Avisar subidas e descidas", "Avisar semáforos", "Continuar em segundo plano",
                   "Janela ao minimizar", "Tipo de janela", "Corrida ao vivo"]),
    ("Mapa e tela", ["Aparência", "Mapa gira com a direção", "Mapa offline de Goiânia",
                     "Tela deitada", "Manter tela ligada"]),
    ("Velocímetro e viagem", ["Alerta de velocidade", "Vibrar no limite", "Ajuste do velocímetro",
                              "Resposta do velocímetro",
                              "Pausa automática"]),
    ("Sistema", ["Diagnóstico", "Modo simulador"]),
]


class Secao(BoxLayout):
    """Título de um grupo de opções: nome em destaque e um risco até a borda."""

    def __init__(self, titulo, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        kw.setdefault("padding", (0, dp(14), 0, 0))
        super().__init__(**kw)
        self.lbl = Label(text=titulo.upper(), font_size=tema.T_ROTULO, bold=True, color=tema.CIANO,
                         size_hint_x=None, halign="left", valign="middle")
        self.lbl.bind(texture_size=lambda l, t: setattr(l, "width", t[0] + dp(10)))
        self.add_widget(self.lbl)
        self.add_widget(Widget())
        self.bind(pos=self._d, size=self._d)
        self.lbl.bind(width=self._d)

    def _d(self, *a):
        from kivy.graphics import Color, Line
        y = self.y + (self.height - dp(14)) / 2.0
        self.canvas.after.clear()
        with self.canvas.after:
            Color(*tema.com_alfa(tema.CIANO, 0.35))
            Line(points=[self.x + self.lbl.width + dp(4), y, self.right, y], width=dp(1))


class _Coletor:
    """Recebe as linhas na ordem do código e as põe na tela por seção."""

    def __init__(self):
        self.itens = []

    def add_widget(self, w):
        self.itens.append(w)

    def arrumar(self, grade):
        por_titulo = {w.titulo.text: w for w in self.itens if isinstance(w, Linha)}
        postos = set()
        for nome, titulos in SECOES:
            linhas = [por_titulo[t] for t in titulos if t in por_titulo]
            if not linhas:
                continue
            grade.add_widget(Secao(nome))
            for w in linhas:
                grade.add_widget(w)
                postos.add(id(w))
        for w in self.itens:   # o que não está em nenhuma seção (e o rodapé) vai no fim
            if id(w) not in postos:
                grade.add_widget(w)


_NOMES_TEMA = {"auto": "Automático", "claro": "Claro", "escuro": "Escuro"}


def _versao():
    return App.get_running_app().versao()


class TelaConfig(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(8))
        raiz.add_widget(Cabecalho("Ajustes", self._voltar))

        # rolagem: as opções não cabem numa tela deitada (nem em celular pequeno)
        rolagem = ScrollView(do_scroll_x=False, bar_color=tema.CIANO, bar_width=dp(3))
        grade = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        grade.bind(minimum_height=grade.setter("height"))
        rolagem.add_widget(grade)
        raiz.add_widget(rolagem)
        lista = _Coletor()   # as linhas são criadas abaixo e arrumadas em seções no fim

        self.alt_voz = Alternar(self._mudar_voz)
        lista.add_widget(Linha("Voz do assistente",
                               "Fala as curvas, as subidas e os avisos da navegação.",
                               self._centralizar(self.alt_voz)))

        self.sel_qual_voz = Seletor("%s", self._mudar_qual_voz)
        self.linha_qual_voz = Linha("Qual voz", "", self.sel_qual_voz)
        lista.add_widget(self.linha_qual_voz)

        self.sel_tom = Seletor("%.2f", self._mudar_tom)
        lista.add_widget(Linha("Tom da voz",
                               "Menor: mais grave e calma. Maior: mais aguda.",
                               self.sel_tom))

        self.alt_efeito = Alternar(lambda v: self._mudar_voz_config("voz_efeito", self.alt_efeito, v))
        lista.add_widget(Linha("Efeito de IA",
                               "Tratamento estilo assistente (Jarvis) na voz.",
                               self._centralizar(self.alt_efeito)))

        lista.add_widget(Linha("Testar a voz",
                               "Fala uma frase de exemplo com a voz escolhida.",
                               self._centralizar(BotaoHUD(text="Testar", size_hint_x=None, width=dp(130),
                                                          on_release=lambda *a: self._testar_voz()))))

        self.alt_subidas = Alternar(self._mudar_subidas)
        lista.add_widget(Linha("Avisar subidas e descidas",
                               "Na navegação, avisa antes de cada subida e descida forte.",
                               self._centralizar(self.alt_subidas)))

        self.alt_semaforos = Alternar(self._mudar_semaforos)
        lista.add_widget(Linha("Avisar semáforos",
                               "Fala \"Semáforo à frente\" no caminho (lombada é sempre avisada).",
                               self._centralizar(self.alt_semaforos)))

        self.btn_rota = BotaoHUD(text="", size_hint_x=None, width=dp(130), font_size=tema.T_ROTULO + 2,
                                 on_release=lambda *a: self._mudar_rota_preferida())
        lista.add_widget(Linha("Rota preferida",
                               "A que já vem escolhida ao buscar um destino. Tranquila: foge das "
                               "avenidas (costuma demorar uns minutos a mais). As duas sempre aparecem.",
                               self._centralizar(self.btn_rota)))

        self.btn_transito = BotaoHUD(text="", size_hint_x=None, width=dp(130), font_size=tema.T_ROTULO + 2,
                                     on_release=lambda *a: self._configurar_transito())
        self.linha_transito = Linha("Trânsito ao vivo", "", self._centralizar(self.btn_transito))
        lista.add_widget(self.linha_transito)

        self.alt_chuva = Alternar(lambda v: self._mudar_simples("avisar_chuva", self.alt_chuva, v))
        lista.add_widget(Linha("Aviso de chuva",
                               "Avisa na prévia e por voz se a previsão indica chuva na saída ou no "
                               "destino até a hora de chegar. É previsão: pode errar.",
                               self._centralizar(self.alt_chuva)))

        self.alt_fundo = Alternar(lambda v: self._mudar_simples("segundo_plano", self.alt_fundo, v))
        lista.add_widget(Linha("Continuar em segundo plano",
                               "Com rota ativa ou viagem gravando, minimizar o app (ou apagar a "
                               "tela) não para nada: a voz continua e aparece uma notificação.",
                               self._centralizar(self.alt_fundo)))

        self.btn_tipo = BotaoHUD(text="", size_hint_x=None, width=dp(130), font_size=tema.T_ROTULO + 2,
                                 on_release=lambda *a: self._mudar_tipo_flutuante())
        lista.add_widget(Linha("Tipo de janela",
                               "Painel: retângulo no meio da tela com o caminho à frente, a próxima "
                               "curva e a velocidade. Bolha: pequena, só minutos e km.",
                               self._centralizar(self.btn_tipo)))

        self.alt_bolha = Alternar(self._mudar_bolha)
        self.linha_bolha = Linha("Janela ao minimizar",
                                 "Minimizado, mostra os minutos e os km até o destino por cima "
                                 "dos outros apps (como a 99). Toque nela para voltar.",
                                 self._centralizar(self.alt_bolha))
        lista.add_widget(self.linha_bolha)

        self.alt_girar = Alternar(lambda v: self._mudar_simples("girar_mapa", self.alt_girar, v))
        lista.add_widget(Linha("Mapa gira com a direção",
                               "Na navegação, o caminho à frente fica sempre para cima.",
                               self._centralizar(self.alt_girar)))

        self.sel_limite = Seletor("%d km/h", self._mudar_limite)
        lista.add_widget(Linha("Alerta de velocidade",
                               "O velocímetro fica laranja e pisca acima deste valor.",
                               self.sel_limite))

        self.alt_vibrar = Alternar(lambda v: self._mudar_simples("vibrar_limite", self.alt_vibrar, v))
        lista.add_widget(Linha("Vibrar no limite",
                               "O celular vibra quando passa do alerta de velocidade.",
                               self._centralizar(self.alt_vibrar)))

        self.alt_pausa = Alternar(lambda v: self._mudar_simples("pausa_auto", self.alt_pausa, v))
        lista.add_widget(Linha("Pausa automática",
                               "Parado (semáforo), a viagem pausa sozinha e volta ao andar.",
                               self._centralizar(self.alt_pausa)))

        self.alt_deitada = Alternar(self._mudar_deitada)
        lista.add_widget(Linha("Tela deitada",
                               "Para o celular deitado no suporte do guidão.",
                               self._centralizar(self.alt_deitada)))

        self.alt_tela = Alternar(self._mudar_tela)
        lista.add_widget(Linha("Manter tela ligada",
                               "Evita a tela apagar durante a viagem.",
                               self._centralizar(self.alt_tela)))

        self.sel_ajuste = Seletor("%+d%%", self._mudar_ajuste)
        lista.add_widget(Linha("Ajuste do velocímetro",
                               "0% = velocidade real (GPS, a mesma que o radar mede). O painel da moto "
                               "costuma marcar uns 5 a 10% a mais: aumente aqui se quiser que o app "
                               "mostre igual a ele.",
                               self.sel_ajuste))

        self.sel_alfa = Seletor("%.1f", self._mudar_alfa)
        lista.add_widget(Linha("Resposta do velocímetro",
                               "Maior: acompanha a acelerada mais rápido (pode passar 1 ou 2 km/h do "
                               "ponto por um instante). Menor: mais calmo. 0.5 é o equilíbrio.",
                               self.sel_alfa))

        self.btn_offline = BotaoHUD(text="Baixar", size_hint_x=None, width=dp(130),
                                    on_release=lambda *a: self._baixar_offline())
        self.linha_offline = Linha("Mapa offline de Goiânia",
                                   "Baixa a cidade toda (~40 MB, use o Wi-Fi): o mapa abre "
                                   "na hora e funciona sem internet.",
                                   self._centralizar(self.btn_offline))
        lista.add_widget(self.linha_offline)
        import mapa_vetor
        partes = mapa_vetor.partes_no_pacote()
        if partes:   # o mapa já veio dentro do app: não há o que baixar
            self.btn_offline.text = "Incluído"
            self.btn_offline.disabled = True
            self.linha_offline.explicacao.text = (
                "Goiânia inteira já vem dentro do app (%d partes): o mapa abre na hora "
                "e funciona sem internet." % partes)

        self.btn_vivo = BotaoHUD(text="Configurar", size_hint_x=None, width=dp(130),
                                 on_release=lambda *a: self._configurar_vivo())
        self.linha_vivo = Linha("Corrida ao vivo", "", self._centralizar(self.btn_vivo))
        lista.add_widget(self.linha_vivo)

        lista.add_widget(Linha("Diagnóstico",
                               "Algo deu errado? Envie o registro do app para o Claude "
                               "(pelo WhatsApp, por exemplo). Pode conter sua localização.",
                               BotaoHUD(text="Enviar", size_hint_x=None, width=dp(130),
                                        on_release=lambda *a: self._enviar_diagnostico())))

        self.btn_tema = BotaoHUD(text="", size_hint_x=None, width=dp(130),
                                 on_release=lambda *a: self._mudar_tema())
        lista.add_widget(Linha("Aparência",
                               "Automático: tema claro de dia (lê melhor no sol) e escuro à "
                               "noite, pelo nascer e pôr do sol. Toque para trocar.",
                               self._centralizar(self.btn_tema)))

        self.alt_sim = Alternar(self._mudar_sim)
        lista.add_widget(Linha("Modo simulador",
                               "Usa GPS falso para testar o app parado.",
                               self._centralizar(self.alt_sim)))

        self.lbl_versao = Texto(text="", font_size=tema.T_ROTULO, color=tema.CIANO_FRACO,
                                halign="center", size_hint_y=None, height=dp(64))
        lista.add_widget(self.lbl_versao)
        lista.arrumar(grade)
        self.add_widget(raiz)

    @staticmethod
    def _centralizar(w):
        return w  # a Linha já centraliza o controle na altura

    def on_pre_enter(self, *a):
        aj = App.get_running_app().ajustes
        self.alt_voz.mostrar(aj["voz"])
        self._mostrar_qual_voz()
        self.sel_tom.mostrar(aj["voz_tom"])
        self.alt_efeito.mostrar(aj["voz_efeito"])
        self.alt_subidas.mostrar(aj["avisar_subidas"])
        self.alt_semaforos.mostrar(aj["avisar_semaforos"])
        self.alt_fundo.mostrar(aj["segundo_plano"])
        self._mostrar_bolha()
        self.alt_girar.mostrar(aj["girar_mapa"])
        self.sel_limite.mostrar(aj["limite_kmh"])
        self.alt_vibrar.mostrar(aj["vibrar_limite"])
        self.alt_pausa.mostrar(aj["pausa_auto"])
        self.alt_deitada.mostrar(aj["tela_deitada"])
        self.alt_tela.mostrar(aj["tela_ligada"])
        self.sel_alfa.mostrar(aj["alfa"])
        self.sel_ajuste.mostrar(aj["vel_ajuste"])
        self.alt_sim.mostrar(aj["simulador"])
        self.btn_tema.text = _NOMES_TEMA.get(aj["tema"], "Automático")
        self.btn_rota.text = "Tranquila" if aj["rota_preferida"] == "tranquila" else "Mais rápida"
        self.btn_tipo.text = "Bolha" if aj["flutuante_tipo"] == "bolha" else "Painel"
        self.alt_chuva.mostrar(aj["avisar_chuva"])
        self._mostrar_transito()
        self._mostrar_vivo()
        self.lbl_versao.text = ("GT-HUD versão %s\nMapa (c) OpenStreetMap, OpenFreeMap  |  "
                                "Lugares (c) Overture Maps Foundation" % _versao())

    def _mudar_limite(self, d):
        aj = App.get_running_app().ajustes
        aj["limite_kmh"] = max(10, min(tema.VEL_MAXIMA, aj["limite_kmh"] + d))
        self.sel_limite.mostrar(aj["limite_kmh"])

    def _mudar_simples(self, chave, botao, ligado):
        App.get_running_app().ajustes[chave] = ligado
        botao.mostrar(ligado)

    def _mudar_voz(self, ligado):
        app = App.get_running_app()
        app.ajustes["voz"] = ligado
        app.voz.ligada = ligado
        if not ligado:
            app.voz.calar()
        self.alt_voz.mostrar(ligado)

    def _mostrar_qual_voz(self, *a):
        app = App.get_running_app()
        estado = app.voz.estado_motor()
        nomes = app.voz.nomes_vozes()
        n = len(nomes)
        i = app.ajustes["voz_indice"]
        if estado == "iniciando":
            self.sel_qual_voz.mostrar("...")
            explicacao = "Ligando o motor de voz do celular..."
            if self.manager is not None and self.manager.current == self.name:
                Clock.schedule_once(self._mostrar_qual_voz, 0.5)
        elif estado == "sem":
            self.sel_qual_voz.mostrar("gravada")
            explicacao = "Sem voz em português no celular: usando a voz gravada do app."
        elif n == 0:
            self.sel_qual_voz.mostrar("padrao")
            explicacao = "Voz padrão do celular."
        elif i < 0:
            self.sel_qual_voz.mostrar("auto")
            auto = app.ajustes["voz_auto"]
            if app.voz._t_medida is not None:
                explicacao = "Medindo as vozes para achar a masculina..."
                if self.manager is not None and self.manager.current == self.name:
                    Clock.schedule_once(self._mostrar_qual_voz, 0.7)
            elif 0 <= auto < n:
                explicacao = "Automática (a mais grave, masculina): %s" % nomes[auto]
            else:
                explicacao = "Automática: a voz mais grave (masculina) do celular."
        elif i >= n:
            self.sel_qual_voz.mostrar("auto")
            explicacao = "Automática: a voz mais grave (masculina) do celular."
        else:
            self.sel_qual_voz.mostrar("%d de %d" % (i + 1, n))
            explicacao = "Voz: %s" % nomes[i]
        self.linha_qual_voz.explicacao.text = explicacao

    def _mudar_qual_voz(self, d):
        app = App.get_running_app()
        n = len(app.voz.nomes_vozes())
        if n == 0:
            return  # sem motor de voz em português: fica a voz gravada
        atual = app.ajustes["voz_indice"]   # -1 = automática (a mais grave)
        # roda por: auto, 1, 2, ... n, auto...
        app.ajustes["voz_indice"] = (atual + 1 + d) % (n + 1) - 1
        self._aplicar_voz(testar=True)
        if app.ajustes["voz_indice"] < 0:
            app._voz_automatica()
        self._mostrar_qual_voz()

    def _mudar_tom(self, d):
        app = App.get_running_app()
        app.ajustes["voz_tom"] = round(max(0.70, min(1.20, app.ajustes["voz_tom"] + d * 0.04)), 2)
        self.sel_tom.mostrar(app.ajustes["voz_tom"])
        self._aplicar_voz(testar=True)

    def _mudar_voz_config(self, chave, botao, ligado):
        App.get_running_app().ajustes[chave] = ligado
        botao.mostrar(ligado)
        self._aplicar_voz(testar=True)

    def _aplicar_voz(self, testar=False):
        app = App.get_running_app()
        app.aplicar_voz()
        if testar:
            self._testar_voz()

    def _testar_voz(self):
        app = App.get_running_app()
        app.voz.calar()
        app.voz.testar()

    def _mudar_subidas(self, ligado):
        app = App.get_running_app()
        app.ajustes["avisar_subidas"] = ligado
        if app.nav is not None:
            app.nav.avisar_subidas = ligado
        self.alt_subidas.mostrar(ligado)

    def _mostrar_bolha(self):
        app = App.get_running_app()
        ligada = app.ajustes["bolha"]
        permitida = app.fundo.android.bolha_permitida()
        self.alt_bolha.mostrar(ligada)
        if ligada and app.fundo.android.bolha is not None and not permitida:
            self.alt_bolha.text = "Permitir"
            self.linha_bolha.explicacao.text = ("Falta liberar \"Exibir sobre outros apps\" "
                                                "para o GT-HUD: toque em Permitir.")
        else:
            self.linha_bolha.explicacao.text = ("Com rota ativa e o app minimizado, uma janela fica por "
                                                "cima dos outros apps para você seguir acompanhando. "
                                                "Dá para arrastar; tocar nela volta ao app.")

    def _mudar_bolha(self, ligado):
        app = App.get_running_app()
        android = app.fundo.android
        if self.alt_bolha.text == "Permitir":
            android.pedir_bolha()   # abre a tela do Android; ao voltar, on_pre_enter atualiza
            return
        app.ajustes["bolha"] = ligado
        if ligado and android.bolha is not None and not android.bolha_permitida():
            android.pedir_bolha()
        self._mostrar_bolha()

    def _mudar_semaforos(self, ligado):
        app = App.get_running_app()
        app.ajustes["avisar_semaforos"] = ligado
        if app.nav is not None:
            app.nav.avisar_semaforos = ligado
        self.alt_semaforos.mostrar(ligado)

    def _mudar_deitada(self, ligado):
        app = App.get_running_app()
        app.ajustes["tela_deitada"] = ligado
        app.aplicar_orientacao()
        self.alt_deitada.mostrar(ligado)

    def _mudar_ajuste(self, d):
        app = App.get_running_app()
        novo = max(-15, min(15, app.ajustes["vel_ajuste"] + d))
        app.ajustes["vel_ajuste"] = novo
        app.filtro.ajuste = 1.0 + novo / 100.0
        self.sel_ajuste.mostrar(novo)

    def _mudar_alfa(self, d):
        app = App.get_running_app()
        novo = round(max(0.1, min(0.9, app.ajustes["alfa"] + d * 0.1)), 1)
        app.ajustes["alfa"] = novo
        app.filtro.alfa = novo
        self.sel_alfa.mostrar(novo)

    def _mudar_tela(self, ligado):
        app = App.get_running_app()
        app.ajustes["tela_ligada"] = ligado
        app.aplicar_tela_ligada()
        self.alt_tela.mostrar(ligado)

    def _mudar_sim(self, ligado):
        App.get_running_app().aplicar_simulador(ligado)
        self.alt_sim.mostrar(ligado)

    def _baixar_offline(self):
        if self.btn_offline.disabled:
            return
        self.btn_offline.disabled = True
        self.btn_offline.text = "..."
        fonte = App.get_running_app().sm.get_screen("mapa").mapa.fonte
        expl = self.linha_offline.explicacao

        def progresso(feitos, total, mb):
            expl.text = "Baixando: %d de %d partes (%.0f MB)..." % (feitos, total, mb)

        def fim(ok, falhas):
            self.btn_offline.disabled = False
            self.btn_offline.text = "Baixar"
            if falhas:
                expl.text = "Faltaram %d partes (sem internet?). Toque em Baixar de novo." % falhas
            else:
                expl.text = "Pronto: Goiânia inteira no celular (%d partes)." % ok
        fonte.baixar_goiania(progresso, fim)

    # --- corrida ao vivo: o endereço do banco gratuito do dono ------------------------
    def _mostrar_vivo(self, aviso=None):
        import ao_vivo
        pronto = ao_vivo.limpar_endereco(App.get_running_app().ajustes["firebase"]) is not None
        self.btn_vivo.text = "Trocar" if pronto else "Configurar"
        self.linha_vivo.explicacao.text = aviso or (
            "Pronto: na navegação, toque em \"Ao vivo\" para mandar o link no WhatsApp."
            if pronto else
            "Mande um link para alguém acompanhar sua rota pela web. Falta colar aqui o "
            "endereço do seu banco gratuito (Firebase).")

    def _configurar_vivo(self):
        import ao_vivo
        import rede
        from widgets.comuns import pedir_nome
        app = App.get_running_app()

        def salvar(texto):
            base = ao_vivo.limpar_endereco(texto)
            if base is None:
                self._mostrar_vivo("Esse não parece o endereço do banco. Ele termina em "
                                   "firebaseio.com ou firebasedatabase.app.")
                return
            self._mostrar_vivo("Testando o banco...")

            def resultado(problema):
                if problema is None:
                    app.ajustes["firebase"] = base
                    self._mostrar_vivo("Funcionou! Na navegação, toque em \"Ao vivo\".")
                else:
                    self._mostrar_vivo(problema)
            rede.em_segundo_plano(lambda: ao_vivo.testar(base), resultado,
                                  lambda e: self._mostrar_vivo("Não consegui testar o banco."))
        pedir_nome(salvar, sugestao=app.ajustes["firebase"], titulo="Endereço do banco (Firebase)",
                   botao="Salvar e testar", dica="https://...firebaseio.com", limite=200)

    # --- trânsito ao vivo: a chave da TomTom do dono ------------------------------------
    def _mostrar_transito(self, aviso=None):
        tem = bool((App.get_running_app().ajustes["tomtom"] or "").strip())
        self.btn_transito.text = "Trocar" if tem else "Configurar"
        self.linha_transito.explicacao.text = aviso or (
            "Ligado: acidentes, trânsito lento e obras aparecem na rota e são avisados por voz."
            if tem else
            "Acidentes, trânsito lento e obras na sua rota. Falta colar aqui a chave gratuita "
            "da TomTom (ela fica só no seu celular).")

    def _configurar_transito(self):
        import rede
        import transito
        from widgets.comuns import pedir_nome
        app = App.get_running_app()

        def salvar(texto):
            chave = "".join(texto.split())
            if len(chave) < 16:
                self._mostrar_transito("Isso não parece a chave: ela é um código comprido de letras e números.")
                return
            self._mostrar_transito("Testando a chave...")

            def resultado(problema):
                if problema is None:
                    app.ajustes["tomtom"] = chave
                    transito.esquecer()
                    self._mostrar_transito("Funcionou! O trânsito já entra na próxima rota.")
                else:
                    self._mostrar_transito(problema)
            rede.em_segundo_plano(lambda: transito.testar(chave), resultado,
                                  lambda e: self._mostrar_transito("Não consegui testar a chave."))
        # (o campo vem vazio: a chave guardada não é mostrada de novo)
        pedir_nome(salvar, sugestao="", titulo="Chave da TomTom", botao="Salvar e testar",
                   dica="Cole a chave aqui", limite=80)

    def _mudar_tipo_flutuante(self):
        app = App.get_running_app()
        novo = "painel" if app.ajustes["flutuante_tipo"] == "bolha" else "bolha"
        app.ajustes["flutuante_tipo"] = novo
        self.btn_tipo.text = "Bolha" if novo == "bolha" else "Painel"

    def _mudar_rota_preferida(self):
        app = App.get_running_app()
        nova = "rapida" if app.ajustes["rota_preferida"] == "tranquila" else "tranquila"
        app.ajustes["rota_preferida"] = nova
        self.btn_rota.text = "Tranquila" if nova == "tranquila" else "Mais rápida"

    def _mudar_tema(self):
        app = App.get_running_app()
        ordem = ["auto", "claro", "escuro"]
        atual = app.ajustes["tema"] if app.ajustes["tema"] in ordem else "auto"
        novo = ordem[(ordem.index(atual) + 1) % len(ordem)]
        app.ajustes["tema"] = novo
        self.btn_tema.text = _NOMES_TEMA[novo]
        # (se o tema mudar, as telas são remontadas e esta deixa de existir)
        Clock.schedule_once(lambda dt: app.conferir_tema(), 0.15)

    def _enviar_diagnostico(self):
        import diagnostico
        if not diagnostico.compartilhar(diagnostico.texto_para_enviar()):
            print("[diagnostico] nao deu para compartilhar")

    def _voltar(self):
        App.get_running_app().voltar()
