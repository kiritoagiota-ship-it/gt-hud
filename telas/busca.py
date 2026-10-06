"""Busca de destino. Enquanto a pessoa digita, já aparecem os lugares do
celular (salvos + base offline de Goiânia); "Buscar" (ou Enter) procura
também na internet (ruas, links colados). Sem texto, mostra os lugares
salvos (com botão de apagar) e os destinos recentes.

Em cima, dois atalhos de um toque: Casa e Trabalho. Vazio, o toque define;
definido, o toque já traça a rota; segurar o dedo troca ou apaga."""
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import busca
import rede
import tema
from util import fmt_dist_nav
from widgets.botao import BotaoHUD
from widgets.comuns import Cabecalho, ItemViagem, Texto, escolher, pedir_nome

DIGITANDO_ESPERA_S = 0.25   # parou de digitar por isso: busca no celular
SEGURAR_S = 0.6             # dedo parado no atalho: trocar/apagar
ATALHOS = (("casa", "Casa"), ("trabalho", "Trabalho"))


class TelaBusca(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._buscando = False
        self._pedido = 0            # cada busca tem um número: resposta velha é ignorada
        self._ev_digitando = None
        self._definindo = None      # "casa"/"trabalho": o próximo lugar tocado vira o atalho
        self._ev_segurar = None
        self._segurou = False
        raiz = BoxLayout(orientation="vertical", padding=tema.MARGEM, spacing=dp(10))
        raiz.add_widget(Cabecalho("Para onde, senhor?", self._voltar))

        linha = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.campo = TextInput(
            hint_text="Lugar, tipo, rua ou link do Google Maps", multiline=False, font_size=tema.T_BOTAO,
            background_normal="", background_active="", background_color=tema.PAINEL,
            foreground_color=tema.BRANCO, hint_text_color=tema.CIANO_FRACO,
            cursor_color=tema.CIANO, padding=(dp(12), dp(14)), write_tab=False)
        self.campo.bind(on_text_validate=lambda *a: self._buscar(),
                        text=lambda *a: self._texto_mudou())
        linha.add_widget(self.campo)
        linha.add_widget(BotaoHUD(text="Buscar", destaque=True, size_hint_x=None, width=dp(96),
                                  on_release=lambda *a: self._buscar()))
        raiz.add_widget(linha)

        atalhos = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.btn_atalho = {}
        for chave, _ in ATALHOS:
            b = BotaoHUD(text="", font_size=tema.T_ROTULO + 2, shorten=True, shorten_from="right")
            b.bind(on_press=lambda w, c=chave: self._atalho_apertou(c),
                   on_release=lambda w, c=chave: self._atalho_soltou(c),
                   size=lambda w, s: setattr(w, "text_size", (s[0] - dp(16), None)))
            b.halign = "center"
            self.btn_atalho[chave] = b
            atalhos.add_widget(b)
        raiz.add_widget(atalhos)

        self.lbl_status = Texto(text="", font_size=tema.T_ROTULO + 1, color=tema.CIANO_FRACO,
                                size_hint_y=None, height=dp(22))
        raiz.add_widget(self.lbl_status)
        rolagem = ScrollView(do_scroll_x=False, bar_color=tema.CIANO, bar_width=dp(3))
        self.lista = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        self.lista.bind(minimum_height=self.lista.setter("height"))
        rolagem.add_widget(self.lista)
        raiz.add_widget(rolagem)
        self.add_widget(raiz)

    def on_pre_enter(self, *a):
        self._definindo = None
        self.campo.text = ""
        self._pintar_atalhos()
        self._mostrar_recentes()

    # --- atalhos Casa / Trabalho ---------------------------------------------------
    def _pintar_atalhos(self):
        guardados = App.get_running_app().ajustes["atalhos"]
        for chave, nome in ATALHOS:
            b = self.btn_atalho[chave]
            definido = chave in guardados
            b.text = nome if definido else "+ " + nome
            b.destaque = self._definindo == chave
            b.cor = tema.CIANO if definido or self._definindo == chave else tema.CIANO_FRACO

    def _atalho_apertou(self, chave):
        self._segurou = False
        if self._ev_segurar is not None:
            self._ev_segurar.cancel()
        self._ev_segurar = Clock.schedule_once(lambda dt: self._atalho_segurado(chave), SEGURAR_S)

    def _atalho_segurado(self, chave):
        self._ev_segurar = None
        self._segurou = True
        if chave in App.get_running_app().ajustes["atalhos"]:
            self._opcoes_atalho(chave)

    def _atalho_soltou(self, chave):
        if self._ev_segurar is not None:
            self._ev_segurar.cancel()
            self._ev_segurar = None
        if self._segurou:
            return
        app = App.get_running_app()
        lugar = app.ajustes["atalhos"].get(chave)
        if lugar is None:
            self._opcoes_atalho(chave)
        else:
            self.campo.focus = False
            app.escolher_destino(dict(lugar, fonte="salvo"))

    def _opcoes_atalho(self, chave):
        app = App.get_running_app()
        nome = dict(ATALHOS)[chave]
        definido = chave in app.ajustes["atalhos"]
        opcoes = []
        if app.posicao is not None:
            opcoes.append(("É aqui, onde estou agora", lambda: self._definir_aqui(chave)))
        opcoes.append(("Escolher na busca", lambda: self._definir_pela_busca(chave)))
        if definido:
            opcoes.append(("Apagar", lambda: self._apagar_atalho(chave)))
        opcoes.append(("Cancelar", None))
        self.campo.focus = False
        escolher(("Trocar " if definido else "Definir ") + nome, opcoes)

    def _definir_aqui(self, chave):
        app = App.get_running_app()
        nome = dict(ATALHOS)[chave]
        app.definir_atalho(chave, {"nome": nome, "endereco": "", "lat": app.posicao[0], "lon": app.posicao[1]})
        self._pintar_atalhos()
        self.lbl_status.text = "%s definida aqui. Toque nela para traçar a rota." % nome \
            if chave == "casa" else "%s definido aqui. Toque nele para traçar a rota." % nome

    def _definir_pela_busca(self, chave):
        self._definindo = chave
        self._pintar_atalhos()
        self.lbl_status.text = "Busque e toque no lugar que é: %s" % dict(ATALHOS)[chave]
        self.campo.focus = True

    def _apagar_atalho(self, chave):
        App.get_running_app().definir_atalho(chave, None)
        self._pintar_atalhos()

    def on_enter(self, *a):
        self.campo.focus = True  # já abre o teclado

    def _texto_mudou(self):
        if self._ev_digitando is not None:
            self._ev_digitando.cancel()
            self._ev_digitando = None
        texto = self.campo.text.strip()
        if not texto:
            self._pedido += 1          # resposta que ainda vier não vale mais
            self._buscando = False
            self._mostrar_recentes()
        elif len(texto) >= 3 and "http" not in texto:
            # enquanto digita: só o que está no celular (rápido, sem internet)
            self._ev_digitando = Clock.schedule_once(lambda dt: self._buscar_local(), DIGITANDO_ESPERA_S)

    def _buscar_local(self):
        self._ev_digitando = None
        texto = self.campo.text.strip()
        if len(texto) < 3 or self._buscando:
            return
        app = App.get_running_app()
        self._pedido += 1
        pedido, salvos, perto = self._pedido, list(app.salvos), app.posicao

        def pronto(lugares):
            if pedido != self._pedido:
                return   # a pessoa já digitou mais
            n = len(lugares)
            self.lbl_status.text = ("%d no celular. Toque em Buscar para procurar também na internet." % n) \
                if n else "Nada no celular com esse nome. Toque em Buscar para procurar na internet."
            self._listar(lugares)
        rede.em_segundo_plano(lambda: busca.buscar_local(texto, perto, salvos)[:busca.MAX_RESULTADOS],
                              pronto, lambda e: None)

    def _mostrar_recentes(self):
        app = App.get_running_app()
        if app.salvos or app.recentes:
            self.lbl_status.text = "Salvos e recentes"
        else:
            self.lbl_status.text = "Digite um lugar, tipo (farmácia) ou rua de Goiânia."
        self.lista.clear_widgets()
        for lugar in app.salvos:
            self._adicionar(dict(lugar, fonte="salvo"), apagavel=True)
        for lugar in app.recentes:  # o que já está nos salvos não repete
            if not any(app.mesmo_lugar(lugar, s) for s in app.salvos):
                self._adicionar(lugar, apagavel=True)

    def _listar(self, lugares):
        self.lista.clear_widgets()
        for lugar in lugares:
            self._adicionar(lugar, apagavel=lugar.get("fonte") == "salvo")

    def _adicionar(self, lugar, apagavel=False):
        partes = ["Salvo por você" if lugar.get("fonte") == "salvo" else "",
                  fmt_dist_nav(lugar["dist_m"]) if lugar.get("dist_m") is not None else "",
                  (lugar.get("endereco") or "").strip()]
        item = ItemViagem(lugar["nome"], "  |  ".join(p for p in partes if p) or " ")
        item.bind(on_release=lambda w, l=lugar: self._escolher(l))
        if not apagavel:
            self.lista.add_widget(item)
            return
        linha = BoxLayout(size_hint_y=None, height=item.height, spacing=dp(6))
        linha.add_widget(item)
        if lugar.get("fonte") == "salvo":
            # salvo: dá para trocar o nome (ex.: ficou "Plus Code 9MJH+9W") ou apagar
            linha.add_widget(BotaoHUD(text="Editar", font_size=tema.T_ROTULO + 1,
                                      size_hint_x=None, width=dp(84),
                                      on_release=lambda w, l=lugar: self._editar(l)))
        else:
            linha.add_widget(BotaoHUD(text="Apagar", cor=tema.VERMELHO, font_size=tema.T_ROTULO + 1,
                                      size_hint_x=None, width=dp(84),
                                      on_release=lambda w, l=lugar: self._apagar(l)))
        self.lista.add_widget(linha)

    def _editar(self, lugar):
        self.campo.focus = False
        escolher(lugar["nome"], [("Trocar o nome", lambda: self._renomear(lugar)),
                                 ("Apagar", lambda: self._apagar(lugar)),
                                 ("Cancelar", None)])

    def _renomear(self, lugar):
        def salvar(nome):
            App.get_running_app().renomear_lugar(lugar, nome)
            if self.campo.text.strip():
                self._buscar_local()
            else:
                self._mostrar_recentes()
            self.lbl_status.text = "Nome trocado para: %s" % nome
        # nome que é só um código não serve de sugestão: o campo vem vazio
        so_codigo = lugar["nome"].startswith(("Plus Code ", "Local colado", "Lugar do Google Maps"))
        pedir_nome(salvar, sugestao="" if so_codigo else lugar["nome"], titulo="Novo nome do lugar")

    def _apagar(self, lugar):
        App.get_running_app().apagar_lugar(lugar)
        if self.campo.text.strip():
            self._buscar()          # estava numa busca: refaz sem o apagado
        else:
            self._mostrar_recentes()

    def _buscar(self):
        texto = self.campo.text.strip()
        if len(texto) < 3 or self._buscando:
            return
        if self._ev_digitando is not None:
            self._ev_digitando.cancel()
            self._ev_digitando = None
        app = App.get_running_app()
        self._buscando = True
        self._pedido += 1
        pedido = self._pedido
        self.lbl_status.text = "Buscando..."
        salvos = list(app.salvos)
        rede.em_segundo_plano(lambda: busca.buscar(texto, app.posicao, salvos),
                              lambda lugares: self._resultados(lugares, pedido),
                              lambda erro: self._falhou(erro, pedido))

    def _resultados(self, lugares, pedido=None):
        if pedido is not None and pedido != self._pedido:
            return
        self._buscando = False
        n = len(lugares)
        self.lbl_status.text = ("%d %s" % (n, "resultado" if n == 1 else "resultados")) if n else \
            "Nada encontrado. Cole o Plus Code ou o link do Google Maps, ou segure o dedo no mapa e salve o ponto."
        self._listar(lugares)

    def _falhou(self, erro, pedido=None):
        if pedido is not None and pedido != self._pedido:
            return
        self._buscando = False
        self.lista.clear_widgets()
        self.lbl_status.text = "Nada na base offline e sem internet para buscar ruas."

    def _escolher(self, lugar):
        self.campo.focus = False
        app = App.get_running_app()
        if self._definindo is not None:
            # estava definindo Casa/Trabalho: este lugar vira o atalho (não traça rota)
            chave, self._definindo = self._definindo, None
            app.definir_atalho(chave, lugar)
            self.campo.text = ""
            self._pintar_atalhos()
            self.lbl_status.text = "%s: %s. Toque no atalho para traçar a rota." % (
                dict(ATALHOS)[chave], lugar["nome"])
            return
        if lugar.get("fonte") != "colado":
            app.escolher_destino(lugar)
            return
        ja = next((s for s in app.salvos if app.mesmo_lugar(s, lugar)), None)
        if ja is not None:   # esse ponto já foi colado e nomeado antes: não pergunta de novo
            app.escolher_destino(dict(ja, fonte="salvo"))
            return
        # veio colado (Plus Code, coordenada ou link): SEMPRE com nome. O campo
        # já vem com o nome do link ou do lugar conhecido naquele ponto; a
        # pessoa confirma ou troca. Fica salvo: na próxima é só digitar o nome.
        sugestao = lugar.get("sugestao", "") if lugar.get("sem_nome") else lugar["nome"]

        def ir(nome):
            app.salvar_lugar(nome, lugar["lat"], lugar["lon"], lugar.get("endereco", ""))
            limpo = {k: v for k, v in lugar.items() if k not in ("sem_nome", "sugestao")}
            app.escolher_destino(dict(limpo, nome=nome))
        pedir_nome(ir, sugestao=sugestao, titulo="Que lugar é esse?", botao="Salvar e ir")

    def _voltar(self):
        self.campo.focus = False
        App.get_running_app().voltar()
