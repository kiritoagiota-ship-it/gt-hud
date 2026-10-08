"""GT-HUD: navegação de bike (mapa, rota, curva a curva, subidas, voz) e
velocímetro GPS com registro de viagens, para a Ouxi GT20."""
import caminhos  # noqa: F401  (o PRIMEIRO import: põe as pastas do código no caminho)
import gc
import json
import threading
import os
import sys
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.screenmanager import NoTransition, ScreenManager

import android_utils
import busca
import diagnostico
import fluxo
import goiania
import mapa_vetor
import rede
import rota as rotas
import rota_tomtom
import sons
import tema
from ajustes import Ajustes
from banco import Banco
from filtro import FiltroVelocidade
from ritmo import Ritmo
import ao_vivo
import clima
import diagnostico as registro
import transito
from aprendizado import Aprendizado
from gps_service import ServicoGPS
from navegacao import P_INFO, Navegacao
from segundo_plano import SegundoPlano
from telas.boot import TelaBoot
from telas.busca import TelaBusca
from telas.config import TelaConfig
from telas.detalhe import TelaDetalhe
from telas.hud import TelaHUD
from telas.mapa import TelaMapa
from telas.viagens import TelaViagens
from viagem import Viagem
from voz import Voz
from widgets.comuns import entrar

# vibra uma vez ao passar do limite e só rearma depois de cair DESARME_KMH
# abaixo dele e de passar INTERVALO_VIBRA_S desde a última (senão vibraria
# sem parar andando em cima do limite)
DESARME_KMH = 2.0
INTERVALO_VIBRA_S = 15.0

SEM_SINAL_APOS_S = 5  # sem leitura boa por mais que isso = sem sinal
DISTANCIA_MINIMA_M = 20  # viagem mais curta que isso não é salva
VIBRA_TEMPOS = [0, 250, 150, 250]  # dois pulsos fortes: dá para sentir no guidão
VIBRA_FORCAS = [0, 255, 0, 255]

RUMO_MIN_KMH = 3.0          # parado, o rumo do GPS é ruído: fica o último
RUMO_VALIDO_S = 6.0         # rumo mais velho que isso não vai no pedido de rota
GPS_PERDIDO_FALA_S = 10     # navegando sem sinal por isso: o assistente avisa
FLUXO_A_CADA_S = 15.0          # mapa: confere se a vista tem as cores do trânsito (só baixa o que falta/venceu)
TRANSITO_MAPA_A_CADA_S = 240.0  # mapa: o trânsito de Goiânia é olhado de novo a cada isso (~360 consultas/dia no máximo, de 2.500)
# posição aproximada (rede/última conhecida), usada só enquanto o satélite não chega
APROX_PRECISAO_MAX_M = 1500.0  # mais vaga que isso não ajuda a achar a pessoa no mapa
APROX_IDADE_MAX_S = 3 * 3600   # "última posição conhecida" mais velha que isso: ele já pode estar longe
APROX_SO_SEM_GPS_HA_S = 20.0   # só assume depois de tanto tempo sem leitura boa do satélite
CAMINHO_A_CADA_S = 300.0       # navegando: a TomTom refaz o caminho com o trânsito de agora a cada isso
CAMINHO_PRIMEIRA_S = 45.0      # a 1ª conferência, pouco depois de sair
TRANSITO_A_CADA_S = 240.0      # navegando: olha o trânsito da rota de novo a cada isso
CHUVA_A_CADA_S = 600.0         # ... e a previsão de chuva
FIM_APOS_CHEGAR_S = 5.0        # chegou: a rota se encerra sozinha depois disso
RECALCULO_ESPERA_S = 12     # depois de falhar, espera antes de tentar de novo
MAX_RECENTES = 8

# O mapa é preparado numa thread; no Python só uma roda por vez (GIL). Trocar
# de vez a cada 2 ms (o padrão é 5) deixa a tela esperar menos: menos tranco.
sys.setswitchinterval(0.002)


class GTHudApp(App):
    title = "GT-HUD"

    def build(self):
        Window.softinput_mode = "below_target"  # teclado não cobre o campo da busca
        Window.bind(on_keyboard=self._tecla)

        pasta = self.user_data_dir
        diagnostico.iniciar(pasta, self.versao())
        self.ajustes = Ajustes(pasta)
        self.posicao = None
        # tema ANTES de montar qualquer tela (claro de dia, escuro à noite)
        tema.aplicar(self.tema_desejado())
        mapa_vetor.aplicar_tema(tema.claro())
        Window.clearcolor = tema.FUNDO
        self.banco = Banco(pasta)
        if not self.ajustes["alfa_v2"]:
            # o filtro mudou (07/10/2026): quem tinha baixado a "Resposta" para o
            # número não tremer estava só ganhando atraso; volta ao meio uma vez
            self.ajustes["alfa_v2"] = True
            if self.ajustes["alfa"] < 0.5:
                self.ajustes["alfa"] = 0.5
        self.filtro = FiltroVelocidade(alfa=self.ajustes["alfa"])
        self.filtro.ajuste = 1.0 + self.ajustes["vel_ajuste"] / 100.0
        self._gps_medidas = [0, 0.0, 0.0, 0.0, 0.0]   # leituras, soma dos intervalos, das idades, das incertezas; hora da última
        self.ritmo = Ritmo(self.ajustes["ritmo"])
        self.aprendizado = Aprendizado(self.banco.caminho)   # o que o app aprende com as viagens dele
        self.chuva_prevista = None   # previsão de chuva para a rota em vista (clima.chuva)
        self._chuva_dita = False
        self._t_transito = 0.0       # time.monotonic() da última conferência do trânsito na navegação
        self._t_caminho = 0.0        # ... e da última vez que a TomTom refez o caminho
        self.rota_sugerida = None    # caminho mais rápido que a TomTom achou durante a navegação
        self._endereco_pendente = None   # endereço recebido de outro app, esperando o GPS/a tela
        self.posicao_aproximada = False  # True: self.posicao veio da rede/última conhecida, não do satélite
        self._t_chuva = 0.0
        self.corrida = None          # corrida ao vivo em andamento (ao_vivo.AoVivo)
        self.ultimo_resumo = None    # números da última viagem finalizada (cartão de chegada)
        self._estava_fora = False    # saiu da rota: vibra uma vez
        self._hoje = None            # (dia, metros, segundos andando) das viagens de hoje
        self.viagem = Viagem()
        self.gps = ServicoGPS(self._ao_receber_gps, self._ao_status_gps, self.ao_posicao_aproximada)
        self.voz = Voz(pasta)
        self.sons = sons.Sons(self.ajustes["sons"])
        self.voz.sons = self.sons
        self.voz.gravada = self.ajustes["voz_fonte"] != "celular"
        self.voz.ligada = self.ajustes["voz"]
        if not self.ajustes["voz_masculina_v1"]:
            # o dono pediu voz masculina: quem tinha escolhido outra volta para a
            # automática (a mais grave do celular) uma vez
            self.ajustes["voz_masculina_v1"] = True
            self.ajustes["voz_indice"] = -1
            if self.ajustes["voz_tom"] == 0.88:
                self.ajustes["voz_tom"] = 0.94   # voz masculina já é grave: menos rebaixada
        self.aplicar_voz()
        Clock.schedule_once(self._voz_automatica, 1.0)

        self.rumo = None
        self.precisao = None         # da última leitura boa (m)
        self.precisao_ultima = None  # da última leitura, boa ou não
        self._t_leitura = 0.0        # time.monotonic() da última leitura
        self._t_valida = 0.0         # ... e da última leitura boa
        self._t_gps_inicio = time.monotonic()
        self.ja_teve_sinal = False
        self.gps_desligado = False
        self.ultima_salva_m = 0
        self._ouvintes = []
        self._alerta_armado = True
        self._ultima_vibracao = -INTERVALO_VIBRA_S

        self.posicao = None          # (lat, lon) da última leitura boa
        self.rumo = None             # direção do movimento (graus) quando andando
        self._t_rumo = -RUMO_VALIDO_S
        self.nav = None              # Navegacao durante a navegação
        self.estado_nav = None       # o que a navegação mostra na tela
        self.rota_previa = None
        self.rotas_previa = []
        self.calculando_alternativas = False
        self._pedido = 0               # cada busca de rota tem um número: resposta velha é ignorada
        self.destino = None
        self._recalculando = False
        self._t_falha_recalculo = 0.0
        self._escolheu_rota = False    # a pessoa tocou numa das rotas da prévia
        self._ofereceu_janela = False  # já avisou da permissão da janela flutuante nesta abertura
        self._fim_agendado = False
        self._fim_em = None            # time.monotonic() em que a rota se encerra depois de chegar
        self._saudou = False
        self._avisou_gps_perdido = False
        self._pilha_telas = []
        self._caminho_recentes = os.path.join(pasta, "recentes.json")
        self.recentes = self._ler_recentes()
        self._caminho_salvos = os.path.join(pasta, "salvos.json")
        self.salvos = self._ler_json(self._caminho_salvos)

        self.sm = self._montar_telas("boot")
        Clock.schedule_interval(lambda dt: self.vigiar_gps(), 2.0)
        Clock.schedule_interval(self.conferir_tema, 60.0)
        self.fundo = SegundoPlano(self)
        return self.sm

    @staticmethod
    def _montar_telas(primeira):
        """Todas as telas num ScreenManager novo; `primeira` já fica à vista."""
        # sem animação de troca: o esmaecer desenhava o mapa 2x por quadro
        # (pesado no celular) e a troca instantânea parece mais rápida
        sm = ScreenManager(transition=NoTransition())
        telas = {"boot": TelaBoot, "mapa": TelaMapa, "busca": TelaBusca, "hud": TelaHUD,
                 "viagens": TelaViagens, "detalhe": TelaDetalhe, "config": TelaConfig}
        if primeira not in telas or primeira == "detalhe":   # o detalhe precisa de uma viagem aberta
            primeira = "mapa"
        sm.add_widget(telas[primeira](name=primeira))        # a 1ª adicionada é a que aparece
        for nome, classe in telas.items():
            if nome != primeira:
                sm.add_widget(classe(name=nome))
        return sm

    # --- tema claro/escuro ------------------------------------------------------------
    def tema_desejado(self):
        """O tema que deveria estar valendo agora, pelos Ajustes e pela hora."""
        escolha = self.ajustes["tema"]
        if escolha in ("claro", "escuro"):
            return escolha
        lat, lon = self.posicao or goiania.CENTRO
        return tema.modo_pela_hora(lat, lon)

    def conferir_tema(self, dt=None):
        """A cada minuto e ao voltar para o app: amanheceu ou anoiteceu?"""
        desejado = self.tema_desejado()
        if desejado == tema.modo or self.fundo.minimizado:
            return
        if self.sm.current == "mapa" and self.sm.get_screen("mapa").estado == "previa":
            return  # escolhendo a rota: troca daqui a pouco, não no meio do toque
        self.trocar_tema(desejado)

    def trocar_tema(self, nome):
        """Troca as cores e REMONTA as telas (o que já está desenhado não muda
        sozinho), mantendo onde a pessoa estava: tela, mapa, rota e navegação."""
        if nome == tema.modo:
            return
        velha = self.sm
        atual = velha.current
        mapa_velho = velha.get_screen("mapa").mapa
        centro, zoom = mapa_velho.centro, mapa_velho.zoom
        try:
            velha.current_screen.dispatch("on_leave")   # para relógios e a animação do mapa
            mapa_velho.pausar()
        except Exception as e:
            print("[tema] ao soltar as telas antigas:", e)
        tema.aplicar(nome)
        mapa_vetor.aplicar_tema(tema.claro())
        Window.clearcolor = tema.FUNDO
        android_utils.cores_do_sistema(tema.FUNDO, tema.claro())
        mapa_velho.fonte.fechar()
        # a tela de antes vira uma "foto" por cima da nova e se dissolve devagar: as cores
        # mudam aos poucos, em vez de a tela piscar (pedido do dono, 08/10/2026)
        foto = None
        try:
            if not self.fundo.minimizado and velha.width > 2:
                foto = velha.export_as_image().texture
        except Exception as e:
            print("[tema] sem a foto da tela antiga:", e)
        self._ouvintes = []
        self.sm = self._montar_telas(atual)
        Window.remove_widget(velha)
        Window.add_widget(self.sm)
        self.root = self.sm
        if foto is not None:
            self._dissolver(foto)
        else:
            entrar(self.sm, 0.4)   # as telas novas aparecem suave (antes era um corte seco)
        tela = self.sm.get_screen("mapa")
        tela.mapa.centro, tela.mapa.zoom = centro, zoom
        if self.nav is not None:
            tela.modo_navegando(self.nav.rota)
        if self.posicao is not None:
            tela.mapa.mostrar_eu(self.posicao[0], self.posicao[1], self.rumo_para_mapa(), self.precisao, 0)
        if self.sm.current == "boot":
            if self.gps.ativo:
                self.sm.get_screen("boot").aguardando_sinal()
        elif self.sm.current != "mapa":
            # a tela do mapa precisa ter entrado uma vez para se registrar no GPS
            tela.on_pre_enter()
            tela.on_leave()
        gc.unfreeze()
        gc.collect()   # as telas antigas saem da memória
        gc.freeze()
        print("[tema] agora:", nome)
        self.atualizar_transito_do_mapa()   # o mapa novo nasce sem o trânsito desenhado
        self._fluxo_tiles = None
        self.atualizar_fluxo()

    def _dissolver(self, textura, segundos=1.3):
        """A foto da tela antiga por cima de tudo, sumindo aos poucos."""
        from kivy.animation import Animation
        from kivy.graphics import Color, Rectangle
        from kivy.uix.widget import Widget
        capa = Widget(size=Window.size, pos=(0, 0), size_hint=(None, None))
        capa.disabled = True                       # não rouba toque
        with capa.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=textura, pos=(0, 0), size=Window.size)
        Window.add_widget(capa)
        self._capa_tema = capa

        def tirar(*a):
            if capa.parent is not None:
                Window.remove_widget(capa)
        animacao = Animation(opacity=0.0, d=segundos, t="in_out_quad")
        animacao.bind(on_complete=tirar)
        animacao.start(capa)

    # --- voz -------------------------------------------------------------------
    def indice_voz(self):
        """Voz em uso: a escolhida nos Ajustes ou, na automática, a mais grave."""
        i = self.ajustes["voz_indice"]
        return i if i >= 0 else self.ajustes["voz_auto"]

    def aplicar_voz(self):
        self.voz.configurar(self.indice_voz(), self.ajustes["voz_tom"], self.ajustes["voz_efeito"])

    def _voz_automatica(self, dt=None, tentativas=[0]):
        """Na automática, mede as vozes uma vez (ou se a lista do celular mudou)."""
        if self.ajustes["voz_indice"] >= 0:
            return
        estado = self.voz.estado_motor()
        if estado == "iniciando" and tentativas[0] < 20:
            tentativas[0] += 1
            Clock.schedule_once(self._voz_automatica, 0.5)
            return
        if estado != "pronto":
            return
        nomes = self.voz.nomes_vozes()
        i = self.ajustes["voz_auto"]
        if 0 <= i < len(nomes) and nomes[i] == self.ajustes["voz_auto_nome"]:
            return  # já medida neste celular

        def achou(indice):
            if indice is not None and indice < len(nomes):
                self.ajustes["voz_auto"] = indice
                self.ajustes["voz_auto_nome"] = nomes[indice]
                self.aplicar_voz()
        self.voz.medir_vozes(achou)

    # --- ciclo de vida ---------------------------------------------------
    def versao(self):
        """1.0.N (gravado pelo build do GitHub); no PC não existe."""
        try:
            with open(os.path.join(self.directory, "versao.json")) as f:
                return json.load(f)["versao"]
        except (OSError, ValueError, KeyError):
            return "de teste (PC)"

    def on_start(self):
        android_utils.cores_do_sistema(tema.FUNDO, tema.claro())
        self.aplicar_tela_ligada()
        self.aplicar_orientacao()
        self.solicitar_gps()
        if diagnostico.fechou_com_erro():
            Clock.schedule_once(lambda dt: self.sm.get_screen("mapa").mensagem(
                "O app fechou com erro da última vez. Ajustes > Diagnóstico > Enviar",
                tema.LARANJA, 10), 4)
        # telas, botões e módulos vivem até o app fechar: "congelados", o
        # coletor de lixo para de varrê-los a cada passada (cada varredura
        # para o app inteiro; quanto menos objetos, menor o tranco)
        gc.collect()
        gc.freeze()
        Clock.schedule_once(self._fechar_corridas_esquecidas, 8)
        android_utils.ouvir_enderecos(self.abrir_endereco)
        recebido = android_utils.endereco_recebido()
        if recebido:
            self.abrir_endereco(recebido)
        Clock.schedule_once(self._aprender_com_as_antigas, 12)
        Clock.schedule_once(self.atualizar_transito_do_mapa, 5)
        Clock.schedule_interval(self.atualizar_transito_do_mapa, TRANSITO_MAPA_A_CADA_S)
        Clock.schedule_once(self.atualizar_fluxo, 6)
        self.sons.carregar_todos(Clock.schedule_once)
        Clock.schedule_interval(self.atualizar_fluxo, FLUXO_A_CADA_S)

    def on_pause(self):
        self._guardar_posicao()
        self.fundo.ao_pausar()  # rota ativa: segue navegando minimizado
        return True  # não fecha o app ao trocar de tela no celular

    def on_resume(self):
        self.fundo.ao_voltar()
        if self.sm.current == "config":  # pode estar voltando da tela de permissão da bolha
            self.sm.get_screen("config").on_pre_enter()
        self.aplicar_tela_ligada()
        self.aplicar_orientacao()
        self.conferir_tema()
        self.sm.get_screen("mapa").mapa.ao_voltar()
        self.atualizar_transito_do_mapa()

    def on_stop(self):
        self._guardar_posicao()
        self.parar_corrida()
        self.fundo.terminou()
        self.salvar_viagem_atual()  # não perde a viagem se o app fechar
        self.gps.parar()

    # --- endereço recebido de outro app ("Abrir com" do Android) ---------------------
    def abrir_endereco(self, uri):
        """Outro app mandou um endereço (toque num endereço do Instagram, do
        WhatsApp, de um site...). O app acha o ponto (CEP -> bairro, busca de
        endereços) e MOSTRA o pino para a pessoa conferir e tocar em "Ir para
        cá" (ou corrigir segurando o dedo no lugar certo). Não achou: abre a
        busca. Navegando, não troca o destino sozinho."""
        recebido = busca.de_geo(uri)
        print("[endereco] o outro app mandou:", repr(str(uri)[:300]))   # (para o diagnóstico)
        print("[app] endereco recebido:", "ponto" if recebido and "lat" in recebido else
              "texto" if recebido else "nao entendi")
        if recebido is None:
            return
        if self.posicao is None or self.sm.current == "boot":
            self._endereco_pendente = uri    # ainda abrindo/sem GPS: trata na 1ª posição
            return
        tela = self.sm.get_screen("mapa")
        if self.nav is not None:
            tela.mensagem("Encerre a rota atual para ir ao endereço recebido", tema.LARANJA, 8)
            return
        if "lat" in recebido:
            if not goiania.dentro(recebido["lat"], recebido["lon"], 0.01):
                self.sm.current = "mapa"
                tela.mensagem("O endereço recebido fica fora de Goiânia", tema.LARANJA, 8)
                return
            self._mostrar_recebido(recebido["lat"], recebido["lon"], recebido["nome"], True)
            return
        bruto = recebido["texto"]
        texto = busca.texto_de_endereco(bruto)
        self.sm.current = "mapa"
        tela.mensagem("Procurando: " + texto[:40], tema.CIANO, 8)
        chave_tomtom = transito.chave_em_uso(self.ajustes) or None
        posicao, salvos = self.posicao, list(self.salvos)

        def procurar():
            achado = busca.resolver_endereco(bruto, posicao, chave_tomtom)
            if achado is not None:
                return achado
            # sem rua reconhecível no texto: a busca comum (lugares salvos, comércios, TomTom)
            certo = busca.certeza(busca.buscar(texto, posicao, salvos, chave_tomtom, endereco=True))
            return None if certo is None else {"lugar": certo, "certo": True}

        def achou(achado):
            if self.nav is not None:
                return
            if achado is None:   # nada, ou mais de um lugar possível: a pessoa escolhe na busca
                self._buscar_na_tela(texto)
                return
            lugar = achado["lugar"]
            self._mostrar_recebido(lugar["lat"], lugar["lon"], lugar["nome"], achado["certo"])
        rede.em_segundo_plano(procurar, achou, lambda e: self._buscar_na_tela(texto))

    def _mostrar_recebido(self, lat, lon, nome, certo):
        """O pino no ponto achado, para conferir antes da rota."""
        if self.destino is not None and self.nav is None:
            self.cancelar_previa()   # havia outra prévia aberta: o endereço novo passa na frente
        self._pilha_telas.clear()
        self.sm.current = "mapa"
        self.sm.get_screen("mapa").mostrar_ponto_recebido(lat, lon, nome, certo)
        self._recebido_em = (lat, lon)   # (para anotar onde a pessoa corrigiu o pino)

    def _buscar_na_tela(self, texto):
        """Abre a tela de busca com o texto já digitado e procurando."""
        self.abrir("busca")
        tela = self.sm.get_screen("busca")
        tela.campo.text = texto
        Clock.schedule_once(lambda dt: tela._buscar(), 0.3)

    def _guardar_posicao(self):
        """Onde a pessoa está ao sair: na próxima abertura o mapa já nasce ali."""
        try:
            if self.posicao is not None:
                self.ajustes["ultima_posicao"] = [round(self.posicao[0], 5), round(self.posicao[1], 5)]
        except Exception as e:
            print("[app] ultima posicao:", e)

    # --- navegação entre telas ---------------------------------------------
    def abrir(self, nome):
        """Vai para a tela `nome` lembrando de onde veio (para o Voltar)."""
        if self.sm.current != nome:
            self._pilha_telas.append(self.sm.current)
        self._mostrar_tela(nome)

    def voltar(self):
        anterior = self._pilha_telas.pop() if self._pilha_telas else "mapa"
        self._mostrar_tela(anterior if anterior != "boot" else "mapa")

    def _mostrar_tela(self, nome):
        mudou = self.sm.current != nome
        self.sm.current = nome
        if mudou and nome != "mapa":  # o mapa entra direto (é pesado; e é para onde se volta com pressa)
            tela = self.sm.get_screen(nome)
            if tela.children:
                entrar(tela.children[0], 0.22, subir=dp(22))

    # --- GPS -------------------------------------------------------------
    def solicitar_gps(self):
        android_utils.pedir_permissoes(self._resposta_permissao)

    def _resposta_permissao(self, ok):
        boot = self.sm.get_screen("boot")
        if ok or self.ajustes["simulador"]:
            self.gps.iniciar(usar_simulador=self.ajustes["simulador"])
            self._t_gps_inicio = time.monotonic()
            self._t_leitura = self._t_valida = 0.0
            self.ja_teve_sinal = False
            boot.aguardando_sinal()
        else:
            boot.permissao_negada()

    def aplicar_simulador(self, ligado):
        self.ajustes["simulador"] = ligado
        self.gps.parar()
        self.filtro.reset()
        self.gps_desligado = False
        self.solicitar_gps()
        if self.nav is not None:
            self.gps.seguir_rota(self.nav.rota.pontos)

    def ouvir(self, funcao):
        """Telas se registram aqui para receber cada leitura (km/h ou None)."""
        self._ouvintes.append(funcao)

    def _avisar(self, vel):
        for f in self._ouvintes:
            f(vel)

    def sinal_ok(self):
        return time.monotonic() - self._t_valida <= SEM_SINAL_APOS_S

    def sinal_fraco(self):
        """Chegam leituras, mas imprecisas demais para o velocímetro."""
        return not self.sinal_ok() and time.monotonic() - self._t_leitura <= SEM_SINAL_APOS_S

    def segundos_sem_sinal(self):
        return time.monotonic() - max(self._t_valida, self._t_gps_inicio)

    def ao_posicao_aproximada(self, lat, lon, precisao, idade_s, fonte=""):
        """Posição pelas redes Wi-Fi/antenas ou a última que o Android guardou
        (LocalizacaoAprox.java). Só vale ENQUANTO o satélite não chega: mostra
        onde a pessoa está e já deixa calcular rota, como o Waze e o Maps. Não
        entra no velocímetro, na viagem gravada nem na navegação curva a curva."""
        agora = time.monotonic()
        if self.sinal_ok() or (self.posicao is not None and not self.posicao_aproximada
                               and agora - self._t_valida < APROX_SO_SEM_GPS_HA_S):
            return   # o satélite está valendo (ou valeu agora há pouco): ele manda
        if precisao > APROX_PRECISAO_MAX_M or idade_s > APROX_IDADE_MAX_S or not goiania.dentro(lat, lon, 0.05):
            return   # vaga demais, velha demais ou de outra cidade: não ajuda
        if self.nav is not None and self.posicao is not None:
            return   # navegando, a seta não pula para uma posição aproximada
        primeira = self.posicao is None
        self.posicao = (lat, lon)
        self.posicao_aproximada = True
        self.precisao_aproximada = precisao
        if primeira:
            print("[gps] posicao aproximada (%s): %d m, medida ha %d s" % (fonte, precisao, idade_s))
        if self.fundo.minimizado:
            return
        self.sm.get_screen("mapa").mapa.mostrar_eu(lat, lon, None, precisao, None)
        if self.sm.current == "boot":
            self.sm.get_screen("boot").posicao_aproximada(precisao)
        elif self._endereco_pendente is not None:
            pendente, self._endereco_pendente = self._endereco_pendente, None
            Clock.schedule_once(lambda dt: self.abrir_endereco(pendente), 0.5)

    def resumo_gps(self):
        """(cor, texto) curtos do GPS para o canto do mapa (cabe ao lado do
        menu: no máximo ~15 letras por linha)."""
        sat = self.gps.satelites()
        if self.gps_desligado:
            return tema.VERMELHO, "GPS do celular\ndesligado"
        if self.gps.modo == "SIM":
            return tema.LARANJA, "Simulador  %d m" % (self.precisao or 0)
        if self.sinal_ok():
            prec = self.precisao or 0
            texto = "GPS  %d m" % prec + ("\n%d satélites" % sat[1] if sat and sat[1] else "")
            return (tema.VERDE if prec <= 10 else tema.LARANJA), texto
        if self.sinal_fraco():
            return tema.LARANJA, "Sinal fraco\n%d m" % (self.precisao_ultima or 0)
        if self.posicao_aproximada:   # o mapa mostra onde ele está pelas redes; o satélite ainda não chegou
            return tema.LARANJA, "Posição aproximada\n(sem satélite ainda)"
        texto = "Sem sinal" if self.ja_teve_sinal else "Buscando GPS"
        if sat and sat[0]:
            texto += "\n%d de %d satélites" % (sat[1], sat[0])
        return (tema.VERMELHO if self.ja_teve_sinal else tema.LARANJA), texto

    @property
    def recalculando(self):
        return self._recalculando

    def rumo_para_mapa(self):
        return self.rumo

    def rumo_recente(self):
        """Rumo só se estava andando agora há pouco. Para a rota: um rumo
        velho (parou, virou a bike) faria a rota começar com meia-volta."""
        return self.rumo if time.monotonic() - self._t_rumo <= RUMO_VALIDO_S else None

    def na_tela(self, funcao):
        """Mexer em tela só na thread do Kivy: com o app minimizado (thread de
        segundo plano), fica para quando ele voltar."""
        if self.fundo.minimizado:
            Clock.schedule_once(lambda dt: funcao())
        else:
            funcao()

    def _ao_receber_gps(self, d):
        """Leitura do GPS com o app aberto (Clock): lógica + tela."""
        vel = self.processar_leitura(d)
        self._avisar(vel)
        self.fundo.atualizar()  # (só faz algo com rota ativa ou viagem gravando)

    def processar_leitura(self, d):
        """Tudo da leitura que NÃO é tela (filtro, viagem, alerta, navegação).
        Roda também na thread de segundo plano. Devolve a velocidade (km/h)
        ou None se a leitura era ruim."""
        self.gps_desligado = False
        agora = time.monotonic()
        precisao = d.get("accuracy")
        self._t_leitura = agora
        self.precisao_ultima = precisao
        if not self.filtro.leitura_valida(precisao):
            return None
        self._t_valida = agora
        self.ja_teve_sinal = True
        self.precisao = precisao
        if d.get("speed") is None:
            vel = self.filtro.valor  # fix sem velocidade: mantém a última
        else:
            vel = self.filtro.atualizar(d["speed"], d.get("t"), d.get("speed_acc"), d.get("age"))
            self._medir_gps(d, agora)
        self.posicao = (d["lat"], d["lon"])
        self.posicao_aproximada = False
        if d.get("bearing") is not None and vel >= RUMO_MIN_KMH:
            self.rumo = d["bearing"]
            self._t_rumo = agora
        if self._endereco_pendente is not None and not self.fundo.minimizado:
            pendente, self._endereco_pendente = self._endereco_pendente, None
            Clock.schedule_once(lambda dt: self.abrir_endereco(pendente), 0.5)   # (a tela do mapa acabou de entrar)
        if not self._saudou:
            self._saudou = True
            self.voz.falar(["bem_vindo"], P_INFO)
        # antes de registrar: se retomou agora, esta leitura já entra
        self.viagem.checar_pausa_auto(vel, self.ajustes["pausa_auto"])
        self.viagem.registrar(d["lat"], d["lon"], vel)
        self._checar_limite(vel)
        if self.nav is not None:
            self._navegar(d["lat"], d["lon"], vel, agora)
            self.conferir_fim()
        return vel

    def _medir_gps(self, d, agora):
        """Para o diagnóstico: de quanto em quanto tempo o GPS deste celular
        entrega a velocidade, com que atraso e com que incerteza (é o que
        limita a rapidez do velocímetro). Uma linha a cada 120 leituras."""
        m = self._gps_medidas
        if m[4] and agora - m[4] < 5:
            m[0] += 1
            m[1] += agora - m[4]
            m[2] += d.get("age") or 0.0
            m[3] += d.get("speed_acc") or 0.0
        m[4] = agora
        if m[0] >= 120:
            print("[gps] leitura a cada %.2f s, atraso do chip %.2f s, incerteza da velocidade %.2f m/s" % (
                m[1] / m[0], m[2] / m[0], m[3] / m[0]))
            m[0], m[1], m[2], m[3] = 0, 0.0, 0.0, 0.0

    def velocidade_agora(self):
        """Velocidade para o mostrador NESTE instante (o GPS dá 1 leitura por
        segundo; entre elas o filtro segue a tendência). As telas chamam isto
        algumas vezes por segundo."""
        if not self.sinal_ok():
            return 0.0
        return self.filtro.previsto()

    def _checar_limite(self, vel):
        limite = self.ajustes["limite_kmh"]
        if vel > limite:
            agora = time.monotonic()
            if (self._alerta_armado and self.ajustes["vibrar_limite"]
                    and agora - self._ultima_vibracao >= INTERVALO_VIBRA_S):
                android_utils.vibrar(VIBRA_TEMPOS, VIBRA_FORCAS)
                self._ultima_vibracao = agora
            self._alerta_armado = False
        elif vel <= limite - DESARME_KMH:
            self._alerta_armado = True

    def _ao_status_gps(self, tipo, status):
        if status == "gps":
            if tipo == "provider-disabled":
                self.gps_desligado = True
            elif tipo == "provider-enabled":
                self.gps_desligado = False

    def vigiar_gps(self):
        """Navegando, o assistente avisa quando o GPS some e quando volta."""
        if self.nav is None or self.gps.modo == "SIM":
            self._avisou_gps_perdido = False
            return
        if not self.sinal_ok() and self.segundos_sem_sinal() > GPS_PERDIDO_FALA_S:
            if not self._avisou_gps_perdido:
                self._avisou_gps_perdido = True
                self.voz.falar(["senhor", "gps_perdido"], P_INFO)
        elif self.sinal_ok() and self._avisou_gps_perdido:
            self._avisou_gps_perdido = False
            self.voz.falar(["gps_ok"], P_INFO)

    # --- destino, rota e navegação --------------------------------------------
    def escolher_destino(self, lugar):
        self._escolheu_rota = False
        self.destino = lugar
        self._guardar_recente(lugar)
        self._pilha_telas.clear()
        tela = self.sm.get_screen("mapa")
        self.sm.current = "mapa"
        tela.previa_calculando(lugar)
        if not goiania.dentro(lugar["lat"], lugar["lon"], 0.01):
            tela.previa_erro("Fora de Goiânia: o app navega só dentro da cidade.")
            return
        if self.posicao is None:
            tela.previa_erro("Esperando o sinal do GPS para calcular a rota.")
            return
        self._pedido += 1
        pedido = self._pedido
        origem, rumo, alvo = self.posicao, self.rumo_recente(), (lugar["lat"], lugar["lon"])
        # 1º a mais rápida (aparece logo); as outras opções chegam depois
        rede.em_segundo_plano(lambda: rotas.pedir_rota(origem, alvo, rumo, lugar["nome"]),
                              lambda r: self._rota_pronta(r, pedido, origem, rumo, alvo),
                              self._rota_falhou)

    def _rota_pronta(self, rota, pedido, origem, rumo, alvo):
        if self.destino is None or pedido != self._pedido:
            return  # cancelou (ou escolheu outro destino) enquanto calculava
        self.rota_previa = rota
        self.rotas_previa = [rota]
        self.calculando_alternativas = True
        self.chuva_prevista = None
        self._chuva_dita = False
        self.sm.get_screen("mapa").mostrar_previa(rota, self.rotas_previa)
        self.sons.tocar("pronto")   # a rota chegou
        self._informar_rotas([rota], pedido, origem, alvo, chuva=True)
        nome = self.destino["nome"]
        def parcial(lista):
            # a primeira rota tranquila aparece em uns 7 s; o refino segue por trás
            rede._entregar(lambda l: self._alternativas_prontas(l, pedido, final=False), lista)
        chave_tomtom = transito.chave_em_uso(self.ajustes) or None
        self.noite_na_previa = noite = tema.e_noite(origem[0], origem[1])
        rede.em_segundo_plano(lambda: rotas.pedir_alternativas(origem, alvo, rumo, nome, [rota], parcial,
                                                               chave_tomtom=chave_tomtom, noite=noite),
                              lambda rs: self._alternativas_prontas(rs, pedido),
                              lambda e: self._alternativas_prontas([rota], pedido))

    def _alternativas_prontas(self, lista, pedido, final=True):
        if pedido != self._pedido or self.destino is None or self.nav is not None:
            return
        if final:
            self.calculando_alternativas = False
        elif not self.calculando_alternativas:
            return   # um parcial atrasado, depois do resultado final
        era_tranquila = self.rota_previa is not None and "tranquila" in self.rota_previa.nome_perfil
        self.rotas_previa = lista or [self.rota_previa]
        if self.rota_previa not in self.rotas_previa:
            # a tranquila que estava escolhida deu lugar a uma melhor: segue na tranquila
            calma = next((r for r in self.rotas_previa if "tranquila" in r.nome_perfil), None)
            self.rota_previa = calma if (era_tranquila and calma is not None) else self.rotas_previa[0]
        if self.ajustes["rota_preferida"] == "tranquila" and not self._escolheu_rota:
            # quem prefere a tranquila já a encontra escolhida (se existir uma)
            calma = next((r for r in self.rotas_previa if "tranquila" in r.nome_perfil), None)
            if calma is not None:
                self.rota_previa = calma
        self.sm.get_screen("mapa").mostrar_previa(self.rota_previa, self.rotas_previa, enquadrar=final)
        self._informar_rotas(self.rotas_previa, pedido)

    # --- o que o app sabe a mais sobre as rotas: histórico dele, trânsito, chuva -----------
    def _informar_rotas(self, lista, pedido, origem=None, alvo=None, chuva=False):
        """Em segundo plano, para cada rota ainda não olhada: o tempo pelo
        histórico dele, os trechos que costumam estar lentos e o trânsito de
        agora (se houver chave da TomTom); e a previsão de chuva (uma vez por
        destino). Quando termina, a prévia é redesenhada com os avisos."""
        novas = [r for r in lista if not getattr(r, "_informada", False)]
        if not novas and not chuva:
            return
        for r in novas:
            r._informada = True
        chave = transito.chave_em_uso(self.ajustes)
        quer_chuva = chuva and self.ajustes["avisar_chuva"] and origem is not None

        def olhar():
            ocorrencias = None
            if chave:
                try:
                    ocorrencias = transito.da_cidade(chave)
                except Exception as e:           # sem internet, chave recusada...: segue sem o trânsito
                    print("[transito]", type(e).__name__)
            for r in novas:
                self._informar(r, ocorrencias)
            previsao = None
            if quer_chuva:
                try:
                    previsao = clima.chuva(origem, alvo, novas[0].tempo_s if novas else 1200)
                except Exception as e:
                    print("[chuva]", type(e).__name__)
            return previsao

        def pronto(previsao):
            if pedido != self._pedido or self.destino is None or self.nav is not None:
                return
            if quer_chuva:
                self.chuva_prevista = previsao
            if self.rota_previa is not None:
                self.sm.get_screen("mapa").mostrar_previa(self.rota_previa, self.rotas_previa, enquadrar=False)
        rede.em_segundo_plano(olhar, pronto, lambda e: None)

    def atualizar_transito_do_mapa(self, dt=None):
        """O trânsito de Goiânia desenhado no mapa, mesmo sem rota (acidentes,
        obras, vias interditadas e trechos lentos). Sem chave: não faz nada."""
        chave = transito.chave_em_uso(self.ajustes)
        if not chave or getattr(self, "_buscando_transito", False):
            return
        self._buscando_transito = True

        def pronto(lista):
            self._buscando_transito = False
            self.na_tela(lambda: self.sm.get_screen("mapa").mapa.definir_ocorrencias(lista))

        def falhou(erro):
            self._buscando_transito = False
            print("[transito] mapa:", type(erro).__name__)
        rede.em_segundo_plano(lambda: transito.da_cidade(chave), pronto, falhou)

    def atualizar_fluxo(self, dt=None):
        """As ruas coloridas pela velocidade de agora na parte do mapa que
        está na tela (TomTom). Só baixa pedaço que falta ou que venceu."""
        chave = transito.chave_em_uso(self.ajustes)
        if not chave or self.sm is None or self.sm.current != "mapa":
            return
        if getattr(self, "fluxo", None) is None:
            self.fluxo = fluxo.Fluxo()
        mapa = self.sm.get_screen("mapa").mapa
        caixa = mapa.caixa_da_vista()
        if caixa is None or mapa.zoom < 12.5:
            return
        tiles = fluxo.tiles_da_caixa(*caixa)
        if tiles != getattr(self, "_fluxo_tiles", None):   # a vista mudou de pedaço: mostra o que já tem
            self._fluxo_tiles = tiles
            mapa.definir_fluxo(self.fluxo.segmentos(tiles))

        def chegou(mudou):
            if mudou:
                self.na_tela(lambda: self.sm.get_screen("mapa").mapa.definir_fluxo(
                    self.fluxo.segmentos(self._fluxo_tiles or [])))
        self.fluxo.atualizar(chave, tiles, chegou)

    def _informar(self, rota, ocorrencias):
        """Histórico e trânsito de UMA rota (roda numa thread)."""
        try:
            sabe = self.aprendizado.avaliar(rota)
            rota.tempo_pessoal_s = sabe["tempo_s"]
            rota.lentos, rota.extra_lento_s = sabe["lentos"], sabe["extra_s"]
        except Exception as e:
            print("[aprendizado]", e)
        if ocorrencias is not None:
            try:
                transito.avaliar(rota, ocorrencias)
            except Exception as e:
                print("[transito] avaliar:", e)

    def avisos_da_rota(self, rota):
        """Frases curtas para a prévia: chuva, trânsito de agora e trechos que
        costumam estar lentos."""
        avisos = []
        # À noite o cartão diz o que cada caminho É (o app não sabe de criminalidade: só
        # sabe se o caminho vai por rua de bairro, mais vazia, ou por rua principal).
        if getattr(self, "noite_na_previa", False):
            if rota.perfil == "noturna" or getattr(rota, "pelas_principais", False):
                avisos.append("Noite: pelas ruas principais (mais movimento e luz)")
            elif "tranquila" in rota.nome_perfil:
                avisos.append("Noite: este caminho vai por ruas mais vazias")
        if self.chuva_prevista is not None:
            avisos.append(clima.frase(self.chuva_prevista))
        do_transito = transito.resumo(rota)
        if do_transito:
            avisos.append(do_transito)
        if rota.lentos and not rota.incidentes:
            minutos = int(round(rota.extra_lento_s / 60.0))
            n = len(rota.lentos)
            avisos.append("Costuma estar lento: %d %s%s" % (
                n, "trecho" if n == 1 else "trechos", " (+%d min)" % minutos if minutos >= 1 else ""))
        return avisos

    def _conferir_transito_e_chuva(self, agora):
        """Na navegação: a cada TRANSITO_A_CADA_S olha de novo o trânsito da
        rota (acidente novo, trânsito que parou) e, a cada CHUVA_A_CADA_S, a
        previsão de chuva. Tudo em segundo plano."""
        nav, destino = self.nav, self.destino
        if nav is None:
            return
        chave = transito.chave_em_uso(self.ajustes)
        if chave and agora - self._t_transito >= TRANSITO_A_CADA_S:
            self._t_transito = agora
            rota = nav.rota

            def olhar():
                transito.avaliar(rota, transito.da_cidade(chave))
                return rota

            def pronto(r):
                if self.nav is None or self.nav.rota is not r:
                    return
                self.nav.incidentes = list(r.incidentes)
                self.na_tela(lambda: self.sm.get_screen("mapa").mapa.definir_transito(r.trechos_transito))
            rede.em_segundo_plano(olhar, pronto, lambda e: None)
        if chave and self.posicao is not None and agora - self._t_caminho >= CAMINHO_A_CADA_S:
            self._t_caminho = agora
            rota, feito, onde, rumo = nav.rota, nav.dist_feita, self.posicao, self.rumo_recente()

            def conferido(r):
                if r is None or self.nav is None or self.nav.rota is not rota:
                    return
                self.nav.definir_vivo(r["atraso_s"] * transito.ATRASO_MOTO, r["falta_s"])
                if r["melhor"] is not None and self.rota_sugerida is None:
                    self.rota_sugerida = r["melhor"]
                    minutos = int(round(r["ganho_s"] / 60.0))
                    self.voz.falar(["caminho_melhor"], P_INFO)
                    self.na_tela(lambda: self.sm.get_screen("mapa").mensagem(
                        "Caminho %d min mais rápido: toque em Rotas" % minutos, tema.VERDE, 12))
            rede.em_segundo_plano(lambda: rota_tomtom.conferir(chave, rota, feito, onde, rumo),
                                  conferido, lambda e: None)
        if (self.ajustes["avisar_chuva"] and not self._chuva_dita and destino is not None
                and self.posicao is not None and agora - self._t_chuva >= CHUVA_A_CADA_S):
            self._t_chuva = agora
            origem, alvo = self.posicao, (destino["lat"], destino["lon"])
            falta_s = (self.estado_nav or {}).get("restante_s", 600)

            def previsto(c):
                if c is None or self.nav is None or self._chuva_dita or c["em_min"] > 20:
                    return
                self._chuva_dita = True
                self.voz.falar(["chuva"], P_INFO, clima.fala(c))
                self.na_tela(lambda: self.sm.get_screen("mapa").mensagem(clima.frase(c), tema.LARANJA, 8))
            rede.em_segundo_plano(lambda: clima.chuva(origem, alvo, falta_s), previsto, lambda e: None)

    def escolher_rota_previa(self, rota):
        self._escolheu_rota = True
        self.rota_previa = rota
        self.sm.get_screen("mapa").mostrar_previa(rota, self.rotas_previa, enquadrar=False)

    def _rota_falhou(self, erro):
        if self.destino is None:
            return
        tela = self.sm.get_screen("mapa")
        if isinstance(erro, rotas.SemRota):
            tela.previa_erro(str(erro))
            self.voz.falar(["sem_rota"], P_INFO)
        else:
            tela.previa_erro("Sem resposta dos servidores de rota (o seu sinal de internet "
                             "pode estar fraco). Toque em Cancelar e tente de novo daqui a pouco.")
            self.voz.falar(["sem_internet"], P_INFO)

    def cancelar_previa(self):
        self.rota_previa = None
        self.rotas_previa = []
        self._pedido += 1
        self.destino = None
        self.sm.get_screen("mapa").modo_livre()

    def iniciar_navegacao(self):
        rota = self.rota_previa
        if rota is None:
            return
        self.nav = Navegacao(rota, self.voz.falar, self.ajustes["avisar_subidas"],
                             self.ajustes["avisar_semaforos"])
        self.estado_nav = None
        self._fim_agendado = False
        self._fim_em = None
        self._estava_fora = False
        android_utils.vibrar_padrao("inicio")
        agora = time.monotonic()
        self._t_transito = agora          # (a rota acabou de ser olhada na prévia)
        self._t_caminho = agora - CAMINHO_A_CADA_S + CAMINHO_PRIMEIRA_S
        self.rota_sugerida = None
        self._t_chuva = agora - CHUVA_A_CADA_S + 90.0
        if self.chuva_prevista is not None and self.ajustes["avisar_chuva"]:
            self._chuva_dita = True       # já está na tela desde a prévia: fala uma vez ao sair
            self.voz.falar(["chuva"], P_INFO, clima.fala(self.chuva_prevista))
        self.ritmo.comecar()
        if self.viagem.estado == Viagem.PARADA:
            self.viagem.iniciar()  # a navegação grava a viagem sozinha
        self.gps.seguir_rota(rota.pontos)
        self.sm.get_screen("mapa").modo_navegando(rota)
        self._oferecer_janela_flutuante()
        self._medir_rota_em_uso(rota)   # (a escolhida na prévia quase sempre já vem medida)
        self.fundo.comecou()  # notificação + Android deixa seguir minimizado

    def conferir_fim(self):
        """Chegou há FIM_APOS_CHEGAR_S? Encerra a rota. Chamado pelo Clock (app
        aberto), a cada leitura do GPS e pela thread de segundo plano."""
        if self._fim_em is not None and self.nav is not None and time.monotonic() >= self._fim_em:
            self.encerrar_navegacao(chegou=True)

    def _oferecer_janela_flutuante(self):
        """A janela ao minimizar (painel ou bolha) precisa da permissão
        "Exibir sobre outros apps". Sem ela nada aparece e a pessoa não sabe
        por quê: no começo da rota, uma vez por abertura do app, avisa e
        oferece abrir a tela do Android para liberar."""
        android = self.fundo.android
        if (self._ofereceu_janela or not self.ajustes["bolha"] or not self.ajustes["segundo_plano"]
                or getattr(android, "bolha", None) is None or android.bolha_permitida()):
            return
        self._ofereceu_janela = True
        from widgets.comuns import escolher
        escolher("Janela ao minimizar", [("Liberar agora", android.pedir_bolha), ("Agora não", None)],
                 texto="Para o painel da rota aparecer por cima dos outros apps quando você minimizar, "
                       "o Android precisa da permissão \"Exibir sobre outros apps\" para o GT-HUD.")

    def encerrar_navegacao(self, chegou=False):
        """Pode rodar na thread de segundo plano (chegada com o app
        minimizado): o que é de tela fica para quando o app voltar."""
        if self.nav is None:
            return
        self._fim_em = None
        destino_nome = (self.destino or {}).get("nome", "")
        self.nav = None
        self.estado_nav = None
        self.rota_previa = None
        self.destino = None
        self.ajustes["ritmo"] = round(self.ritmo.terminar(), 3)
        self.parar_corrida(chegou)
        self.gps.deixar_rota()
        salvou = self.salvar_viagem_atual(destino_nome)
        resumo = self.ultimo_resumo if salvou else None
        if not chegou:
            self.voz.falar(["navegacao_encerrada"], P_INFO)
        texto = "Você chegou!" if chegou else "Rota encerrada"

        def na_tela():
            tela = self.sm.get_screen("mapa")
            if resumo is not None:   # fechamento da rota: cartão com os números
                tela.modo_livre()
                tela.mostrar_resumo(texto, destino_nome, resumo)
            else:
                tela.modo_livre(texto + ". Trecho curto demais para salvar.", tema.VERDE)
        self.na_tela(na_tela)

    def _navegar(self, lat, lon, vel, agora):
        nav = self.nav
        self.estado_nav = e = nav.atualizar(lat, lon, vel, agora)
        self.ritmo.leitura(nav, vel, agora)  # aprende o ritmo do dono (tempo de chegada)
        if self.corrida is not None and e:
            self.corrida.leitura(lat, lon, vel, self.rumo, e["restante_m"], e["restante_s"],
                                 nav.dist_feita, e.get("fora_da_rota", False))
        self._conferir_transito_e_chuva(agora)
        fora = bool(e and e.get("fora_da_rota"))
        if fora and not self._estava_fora:
            android_utils.vibrar_padrao("fora")
        self._estava_fora = fora
        if nav.chegou and not self._fim_agendado:
            self._fim_agendado = True
            android_utils.vibrar_padrao("chegou")
            self.na_tela(lambda: self.sm.get_screen("mapa").mapa.comemorar())
            # quem acompanha pelo link vê "chegou" na hora, sem esperar nada
            self.parar_corrida(chegou=True)
            # a rota se encerra 5 s depois (tempo de ver/ouvir "você chegou").
            # Pelo relógio do celular, não só pelo Clock do Kivy: com o app
            # minimizado o Clock para, e a rota ficava "andando" para sempre
            # (serviço ligado, viagem sem salvar, link sem fim) até reabrir o app.
            self._fim_em = agora + FIM_APOS_CHEGAR_S
            Clock.schedule_once(lambda dt: self.conferir_fim(), FIM_APOS_CHEGAR_S + 0.1)
        elif (nav.recalcular_pedido and not self._recalculando
              and agora - self._t_falha_recalculo > RECALCULO_ESPERA_S):
            self._recalcular()

    # --- navegando: escolher outra rota até o destino ---------------------------------
    def calcular_rotas_navegando(self):
        if self.nav is None or self.destino is None or self.posicao is None:
            return
        tela = self.sm.get_screen("mapa")
        tela.escolha_nav_calculando()
        self._pedido += 1
        pedido = self._pedido
        origem, rumo, d = self.posicao, self.rumo_recente(), self.destino
        alvo = (d["lat"], d["lon"])

        chave_tomtom = transito.chave_em_uso(self.ajustes) or None
        sugerida, self.rota_sugerida = self.rota_sugerida, None

        def todas():
            primeira = rotas.pedir_rota(origem, alvo, rumo, d["nome"])
            # no meio do caminho a resposta precisa vir logo: sem o refino de contornar avenidas
            lista = rotas.pedir_alternativas(origem, alvo, rumo, d["nome"], [primeira], voltas=0,
                                            chave_tomtom=chave_tomtom)
            # o caminho mais rápido que a TomTom tinha acabado de achar entra na lista
            if sugerida is not None and not any(rotas.parecidas(r, sugerida) for r in lista):
                lista.append(sugerida)
            return lista

        def prontas(lista):
            if pedido == self._pedido and self.nav is not None:
                tela.mostrar_escolha_nav(lista)

        def falhou(erro):
            if pedido == self._pedido and self.nav is not None:
                tela.fechar_escolha_nav()
                tela.mensagem("Sem internet agora: sigo na rota atual. Tente de novo mais à frente.",
                              tema.LARANJA, 5)
        rede.em_segundo_plano(todas, prontas, falhou)

    def trocar_rota_navegando(self, rota):
        if self.nav is None:
            return
        self.nav.trocar_rota(rota)
        self.gps.seguir_rota(rota.pontos)
        if self.corrida is not None:
            self.corrida.trocar_rota(rota)
        self.sm.get_screen("mapa").trocar_rota(rota)
        self.voz.falar(["rota_trocada"], P_INFO)
        self._medir_rota_em_uso(rota)
        self._t_transito = 0.0
        self._t_caminho = time.monotonic() - CAMINHO_A_CADA_S + CAMINHO_PRIMEIRA_S

    def _recalcular(self):
        if self.destino is None or self.posicao is None:
            return
        self._recalculando = True
        self.voz.falar(["recalculando"], 2)
        origem, rumo, destino = self.posicao, self.rumo_recente(), self.destino
        alvo = (destino["lat"], destino["lon"])
        tranquila = "tranquila" in self.nav.rota.nome_perfil or self.nav.rota.perfil == "tranquila"
        viva = self.nav.rota.perfil == "transito"
        noturna = self.nav.rota.perfil == "noturna"
        chave_tomtom = transito.chave_em_uso(self.ajustes)

        def pedir():
            # saiu da rota TRANQUILA: a nova também evita avenida (antes o
            # recálculo vinha sempre pela mais rápida e devolvia a pessoa às avenidas)
            if viva and chave_tomtom:   # estava na rota "pelo trânsito de agora": a nova também é
                try:
                    nova = rota_tomtom.pedir(chave_tomtom, origem, alvo, rumo, destino["nome"])
                    if nova is not None:
                        return nova
                except Exception as e:
                    print("[rota] recalculo pela TomTom falhou:", type(e).__name__)
            if noturna:   # saiu da rota noturna: a nova também vai pelas ruas principais
                try:
                    nova = rotas.pedir_rota(origem, alvo, rumo, destino["nome"], "noturna")
                    nova.nome_perfil = rotas.NOME_NOTURNA
                    return nova
                except rotas.SemRota:
                    raise
                except Exception as e:
                    print("[rota] recalculo noturno falhou, indo pela rapida:", e)
            if tranquila:
                try:
                    nova = rotas.pedir_rota(origem, alvo, rumo, destino["nome"], "tranquila")
                    nova.nome_perfil = "Mais tranquila"
                    return nova
                except rotas.SemRota:
                    raise
                except Exception as e:
                    print("[rota] recalculo tranquilo falhou, indo pela rapida:", e)
            return rotas.pedir_rota(origem, alvo, rumo, destino["nome"])
        rede.em_segundo_plano(pedir, self._recalculou, self._recalculo_falhou)

    def _recalculou(self, rota):
        self._recalculando = False
        if self.nav is None:
            return
        self.nav.trocar_rota(rota)
        self.gps.seguir_rota(rota.pontos)
        if self.corrida is not None:
            self.corrida.trocar_rota(rota)
        self.na_tela(lambda: self.sm.get_screen("mapa").trocar_rota(rota))
        self._medir_rota_em_uso(rota)
        self._t_transito = 0.0   # rota nova: olha o trânsito dela na próxima leitura
        self._t_caminho = time.monotonic() - CAMINHO_A_CADA_S + CAMINHO_PRIMEIRA_S

    def _medir_rota_em_uso(self, rota):
        """Rota nova no meio do caminho ainda não tem as avenidas medidas: mede
        em segundo plano e, quando chegar, pinta os trechos e liga os avisos."""
        if rota.movimentada is not None or getattr(rota, "reserva", False):
            return

        def medida(resultado):
            if resultado is None or self.nav is None or self.nav.rota is not rota:
                return
            self.nav.avenidas = [a for a in rota.avenidas if a[1] - a[0] >= 300]
            # (os limites de velocidade da via vieram junto: a navegação lê de rota.limites)
            self.na_tela(lambda: self.sm.get_screen("mapa").mapa.definir_trechos(rota.trechos))
        rede.em_segundo_plano(lambda: rotas.medir_movimento(rota), medida, lambda e: None)

    def _recalculo_falhou(self, erro):
        self._recalculando = False
        self._t_falha_recalculo = time.monotonic()
        if self.nav is not None:
            self.nav.desistir_de_recalcular()
            # sem caminho a partir daqui (ex.: dentro de um parque): não é falta
            # de internet; o "recalculando" já foi dito, tenta de novo depois
            if not isinstance(erro, rotas.SemRota):
                self.voz.falar(["sem_internet"], P_INFO)

    # --- destinos recentes e lugares salvos ------------------------------------
    @staticmethod
    def _ler_json(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    @staticmethod
    def _gravar_json(caminho, dados):
        try:
            temporario = caminho + ".tmp"
            with open(temporario, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
            os.replace(temporario, caminho)
        except OSError:
            pass

    def _ler_recentes(self):
        return self._ler_json(self._caminho_recentes)[:MAX_RECENTES]

    def salvar_lugar(self, nome, lat, lon, endereco=""):
        """Lugar marcado no mapa pela pessoa (aparece primeiro na busca)."""
        novo = {"nome": nome, "endereco": endereco, "lat": lat, "lon": lon}
        # mesmo nome ou mesmo ponto: troca (salvar de novo o mesmo lugar com
        # outro nome deixava dois iguais na lista)
        self.salvos = [s for s in self.salvos if s["nome"] != nome and not self.mesmo_lugar(s, novo)]
        self.salvos.insert(0, novo)
        self._gravar_json(self._caminho_salvos, self.salvos)

    def renomear_lugar(self, lugar, novo_nome):
        """Troca o nome de um lugar salvo (e do mesmo ponto nos recentes e nos
        atalhos). Ex.: o que ficou salvo como "Plus Code 9MJH+9W"."""
        novo_nome = (novo_nome or "").strip()[:60]
        if not novo_nome:
            return
        for lista in (self.salvos, self.recentes):
            for item in lista:
                if self.mesmo_lugar(item, lugar):
                    item["nome"] = novo_nome
        # dois salvos não podem ficar com o mesmo nome: fica o que foi renomeado
        self.salvos = [s for s in self.salvos
                       if s["nome"] != novo_nome or self.mesmo_lugar(s, lugar)]
        self._gravar_json(self._caminho_salvos, self.salvos)
        self._gravar_json(self._caminho_recentes, self.recentes)
        atalhos = {k: (dict(v, nome=novo_nome) if self.mesmo_lugar(v, lugar) and v["nome"] == lugar["nome"] else v)
                   for k, v in self.ajustes["atalhos"].items()}
        if atalhos != self.ajustes["atalhos"]:
            self.ajustes["atalhos"] = atalhos

    def definir_atalho(self, qual, lugar):
        """qual: "casa" ou "trabalho"; lugar None apaga."""
        atalhos = dict(self.ajustes["atalhos"])
        if lugar is None:
            atalhos.pop(qual, None)
        else:
            atalhos[qual] = {"nome": lugar["nome"], "endereco": lugar.get("endereco", ""),
                             "lat": lugar["lat"], "lon": lugar["lon"]}
        self.ajustes["atalhos"] = atalhos

    @staticmethod
    def mesmo_lugar(a, b):
        return (round(a["lat"], 4), round(a["lon"], 4)) == (round(b["lat"], 4), round(b["lon"], 4))

    def apagar_lugar(self, lugar):
        """Some dos salvos E dos recentes (todo destino escolhido também vira
        recente: apagar só o salvo deixava ele lá, parecendo que não apagou)."""
        self.salvos = [s for s in self.salvos if not self.mesmo_lugar(s, lugar)]
        self.recentes = [r for r in self.recentes if not self.mesmo_lugar(r, lugar)]
        self._gravar_json(self._caminho_salvos, self.salvos)
        self._gravar_json(self._caminho_recentes, self.recentes)

    def _guardar_recente(self, lugar):
        item = {k: lugar[k] for k in ("nome", "endereco", "lat", "lon") if k in lugar}
        self.recentes = [r for r in self.recentes
                         if (round(r["lat"], 4), round(r["lon"], 4))
                         != (round(item["lat"], 4), round(item["lon"], 4))]
        self.recentes.insert(0, item)
        del self.recentes[MAX_RECENTES:]
        self._gravar_json(self._caminho_recentes, self.recentes)

    # --- corrida ao vivo (link para alguém acompanhar pela web) ---------------------
    def compartilhando(self):
        return self.corrida is not None and self.corrida.ativo

    def compartilhar_corrida(self):
        """Começa a mandar a corrida para o banco (se ainda não começou) e abre
        o "Compartilhar" do Android com o link. Devolve o link, "sem_rota" ou
        "sem_config" (falta o endereço do banco nos Ajustes)."""
        if self.nav is None:
            return "sem_rota"
        base = ao_vivo.limpar_endereco(self.ajustes["firebase"])
        if base is None:
            return "sem_config"
        if not self.compartilhando():
            self.corrida = ao_vivo.AoVivo(base)
            self.corrida.comecar(self.nav.rota, (self.destino or {}).get("nome", ""))
            # se o app fechar no meio, a próxima abertura apaga a posição do banco
            self.ajustes["corridas_abertas"] = self.ajustes["corridas_abertas"] + [
                [base, self.corrida.codigo, self.corrida.senha]]
            print("[ao vivo] corrida compartilhada")
        registro.compartilhar("Acompanhe minha corrida ao vivo:\n" + self.corrida.link,
                              "Minha corrida ao vivo", "Enviar o link da corrida")
        return self.corrida.link

    def parar_corrida(self, chegou=False):
        """Avisa o fim: a posição e o caminho somem do banco (o link para de mostrar)."""
        corrida, self.corrida = self.corrida, None
        if corrida is None:
            return
        corrida.terminar(chegou)

        def conferir():
            corrida.esperar_fim(15)
            return corrida
        rede.em_segundo_plano(conferir, self._corrida_encerrada)

    def _corrida_encerrada(self, corrida):
        if corrida.fim_avisado:
            self.ajustes["corridas_abertas"] = [c for c in self.ajustes["corridas_abertas"]
                                                if c[1] != corrida.codigo]

    def _fechar_corridas_esquecidas(self, dt=None):
        """Corridas que ficaram abertas no banco (app fechado no meio, ou sem
        internet na hora de encerrar): apaga a posição agora."""
        abertas = [c for c in self.ajustes["corridas_abertas"]
                   if self.corrida is None or c[1] != self.corrida.codigo]
        if not abertas:
            return

        def fechar():
            fechadas = []
            for base, codigo, senha in abertas:
                try:
                    ao_vivo.encerrar_esquecida(base, codigo, senha)
                    fechadas.append(codigo)
                except Exception as e:
                    print("[ao vivo] corrida antiga ainda aberta:", e)
            return fechadas

        def pronto(fechadas):
            self.ajustes["corridas_abertas"] = [c for c in self.ajustes["corridas_abertas"]
                                                if c[1] not in fechadas]
        rede.em_segundo_plano(fechar, pronto)

    # --- viagem ----------------------------------------------------------
    def resumo_de_hoje(self):
        """(metros, segundos andando) das viagens salvas hoje."""
        dia = time.strftime("%Y-%m-%d")
        if self._hoje is None or self._hoje[0] != dia:
            t = time.localtime()
            meia_noite = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
            hoje = [v for v in self.banco.listar_viagens() if (v["inicio"] or 0) >= meia_noite]
            self._hoje = (dia, sum(v["distancia_m"] or 0 for v in hoje),
                          sum(v["tempo_mov_s"] or 0 for v in hoje))
        return self._hoje[1], self._hoje[2]

    def salvar_viagem_atual(self, destino_nome=""):
        resultado = self.viagem.finalizar()
        self.fundo.sincronizar()
        self.ultimo_resumo = None
        if not resultado:
            return None
        resumo, pontos = resultado
        resumo["destino"] = destino_nome or ""
        self.ultimo_resumo = resumo
        if resumo["distancia_m"] < DISTANCIA_MINIMA_M:
            # não salva viagem vazia (antes bastavam 5 leituras: ficar parado
            # 5 s com sinal salvava uma viagem de "0 m")
            return None
        self.ultima_salva_m = resumo["distancia_m"]
        self._hoje = None
        # o app aprende com ela: velocidade dele em cada trecho, por horário
        threading.Thread(target=self._aprender, args=(list(pontos),), name="aprender", daemon=True).start()
        return self.banco.salvar_viagem(resumo, pontos)

    def _aprender(self, pontos):
        try:
            self.aprendizado.aprender(pontos)
        except Exception as e:
            print("[aprendizado] aprender:", e)

    def _aprender_com_as_antigas(self, dt=None):
        """Uma vez: as viagens que já estavam guardadas também ensinam."""
        if self.ajustes["aprendeu_v1"]:
            return
        self.ajustes["aprendeu_v1"] = True

        def todas():
            n = 0
            for v in self.banco.listar_viagens():
                _, pontos = self.banco.obter_viagem(v["id"])
                if len(pontos) > 20:
                    self.aprendizado.aprender(pontos)
                    n += 1
            print("[aprendizado] aprendeu com %d viagens guardadas" % n)
        threading.Thread(target=lambda: self._seguro(todas), name="aprender-antigas", daemon=True).start()

    @staticmethod
    def _seguro(funcao):
        try:
            funcao()
        except Exception as e:
            print("[aprendizado] viagens antigas:", e)

    def viagem_mudou(self):
        """As telas avisam quando a gravação começa, pausa ou termina: o
        segundo plano liga/desliga junto (gravar com a tela apagada)."""
        self.fundo.sincronizar()

    # --- tela ------------------------------------------------------------
    def aplicar_tela_ligada(self):
        android_utils.manter_tela_ligada(self.ajustes["tela_ligada"])

    def aplicar_orientacao(self):
        android_utils.definir_orientacao(self.ajustes["tela_deitada"])

    def _tecla(self, janela, tecla, *a):
        if tecla != 27:  # botão voltar do Android
            return False
        atual = self.sm.current
        if atual == "detalhe":
            self.sm.current = "viagens"
            return True
        if atual in ("viagens", "config", "hud", "busca"):
            self.voltar()
            return True
        if atual == "mapa":
            if self.sm.get_screen("mapa").estado == "previa":
                self.cancelar_previa()
                return True
            if self.nav is not None or self.viagem.estado != Viagem.PARADA:
                return True  # evita fechar o app sem querer durante a viagem
        return False


if __name__ == "__main__":
    GTHudApp().run()
