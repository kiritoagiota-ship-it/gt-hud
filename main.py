"""GT-HUD: navegação de bike (mapa, rota, curva a curva, subidas, voz) e
velocímetro GPS com registro de viagens, para a Ouxi GT20."""
import gc
import json
import os
import sys
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import NoTransition, ScreenManager

import android_utils
import diagnostico
import goiania
import rede
import rota as rotas
import tema
from ajustes import Ajustes
from banco import Banco
from filtro import FiltroVelocidade
from ritmo import Ritmo
import ao_vivo
import diagnostico as registro
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
RECALCULO_ESPERA_S = 12     # depois de falhar, espera antes de tentar de novo
MAX_RECENTES = 8

# O mapa é preparado numa thread; no Python só uma roda por vez (GIL). Trocar
# de vez a cada 2 ms (o padrão é 5) deixa a tela esperar menos: menos tranco.
sys.setswitchinterval(0.002)


class GTHudApp(App):
    title = "GT-HUD"

    def build(self):
        Window.clearcolor = tema.FUNDO
        Window.softinput_mode = "below_target"  # teclado não cobre o campo da busca
        Window.bind(on_keyboard=self._tecla)

        pasta = self.user_data_dir
        diagnostico.iniciar(pasta, self.versao())
        self.ajustes = Ajustes(pasta)
        self.banco = Banco(pasta)
        self.filtro = FiltroVelocidade(alfa=self.ajustes["alfa"])
        self.ritmo = Ritmo(self.ajustes["ritmo"])
        self.corrida = None          # corrida ao vivo em andamento (ao_vivo.AoVivo)
        self._hoje = None            # (dia, metros, segundos andando) das viagens de hoje
        self.viagem = Viagem()
        self.gps = ServicoGPS(self._ao_receber_gps, self._ao_status_gps)
        self.voz = Voz(pasta)
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
        self._fim_agendado = False
        self._saudou = False
        self._avisou_gps_perdido = False
        self._pilha_telas = []
        self._caminho_recentes = os.path.join(pasta, "recentes.json")
        self.recentes = self._ler_recentes()
        self._caminho_salvos = os.path.join(pasta, "salvos.json")
        self.salvos = self._ler_json(self._caminho_salvos)

        # sem animação de troca: o esmaecer desenhava o mapa 2x por quadro
        # (pesado no celular) e a troca instantânea parece mais rápida
        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(TelaBoot(name="boot"))
        self.sm.add_widget(TelaMapa(name="mapa"))
        self.sm.add_widget(TelaBusca(name="busca"))
        self.sm.add_widget(TelaHUD(name="hud"))
        self.sm.add_widget(TelaViagens(name="viagens"))
        self.sm.add_widget(TelaDetalhe(name="detalhe"))
        self.sm.add_widget(TelaConfig(name="config"))
        Clock.schedule_interval(lambda dt: self.vigiar_gps(), 2.0)
        self.fundo = SegundoPlano(self)
        return self.sm

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

    def on_pause(self):
        self.fundo.ao_pausar()  # rota ativa: segue navegando minimizado
        return True  # não fecha o app ao trocar de tela no celular

    def on_resume(self):
        self.fundo.ao_voltar()
        if self.sm.current == "config":  # pode estar voltando da tela de permissão da bolha
            self.sm.get_screen("config").on_pre_enter()
        self.aplicar_tela_ligada()
        self.aplicar_orientacao()
        self.sm.get_screen("mapa").mapa.ao_voltar()

    def on_stop(self):
        self.parar_corrida()
        self.fundo.terminou()
        self.salvar_viagem_atual()  # não perde a viagem se o app fechar
        self.gps.parar()

    # --- navegação entre telas ---------------------------------------------
    def abrir(self, nome):
        """Vai para a tela `nome` lembrando de onde veio (para o Voltar)."""
        if self.sm.current != nome:
            self._pilha_telas.append(self.sm.current)
        self.sm.current = nome

    def voltar(self):
        anterior = self._pilha_telas.pop() if self._pilha_telas else "mapa"
        self.sm.current = anterior if anterior != "boot" else "mapa"

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
            vel = self.filtro.atualizar(d["speed"], d.get("t"), d.get("speed_acc"))
        self.posicao = (d["lat"], d["lon"])
        if d.get("bearing") is not None and vel >= RUMO_MIN_KMH:
            self.rumo = d["bearing"]
            self._t_rumo = agora
        if not self._saudou:
            self._saudou = True
            self.voz.falar(["bem_vindo"], P_INFO)
        # antes de registrar: se retomou agora, esta leitura já entra
        self.viagem.checar_pausa_auto(vel, self.ajustes["pausa_auto"])
        self.viagem.registrar(d["lat"], d["lon"], vel)
        self._checar_limite(vel)
        if self.nav is not None:
            self._navegar(d["lat"], d["lon"], vel, agora)
        return vel

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
        self.sm.get_screen("mapa").mostrar_previa(rota, self.rotas_previa)
        nome = self.destino["nome"]
        rede.em_segundo_plano(lambda: rotas.pedir_alternativas(origem, alvo, rumo, nome, [rota]),
                              lambda rs: self._alternativas_prontas(rs, pedido),
                              lambda e: self._alternativas_prontas([rota], pedido))

    def _alternativas_prontas(self, lista, pedido):
        if pedido != self._pedido or self.destino is None or self.nav is not None:
            return
        self.calculando_alternativas = False
        self.rotas_previa = lista or [self.rota_previa]
        if self.rota_previa not in self.rotas_previa:
            self.rota_previa = self.rotas_previa[0]
        self.sm.get_screen("mapa").mostrar_previa(self.rota_previa, self.rotas_previa, enquadrar=True)

    def escolher_rota_previa(self, rota):
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
            tela.previa_erro("Não consegui calcular a rota. Confira a internet.")
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
        self.ritmo.comecar()
        if self.viagem.estado == Viagem.PARADA:
            self.viagem.iniciar()  # a navegação grava a viagem sozinha
        self.gps.seguir_rota(rota.pontos)
        self.sm.get_screen("mapa").modo_navegando(rota)
        self.fundo.comecou()  # notificação + Android deixa seguir minimizado

    def encerrar_navegacao(self, chegou=False):
        if self.nav is None:
            return
        self.nav = None
        self.estado_nav = None
        self.rota_previa = None
        self.destino = None
        self.ajustes["ritmo"] = round(self.ritmo.terminar(), 3)
        self.parar_corrida(chegou)
        self.gps.deixar_rota()
        salvou = self.salvar_viagem_atual()
        if not chegou:
            self.voz.falar(["navegacao_encerrada"], P_INFO)
        texto = "Você chegou!" if chegou else "Navegação encerrada."
        if salvou:
            texto += "  Viagem salva (%s)." % ("%.1f km" % (self.ultima_salva_m / 1000.0)).replace(".", ",")
        self.sm.get_screen("mapa").modo_livre(texto, tema.VERDE)

    def _navegar(self, lat, lon, vel, agora):
        nav = self.nav
        self.estado_nav = e = nav.atualizar(lat, lon, vel, agora)
        self.ritmo.leitura(nav, vel, agora)  # aprende o ritmo do dono (tempo de chegada)
        if self.corrida is not None and e:
            self.corrida.leitura(lat, lon, vel, self.rumo, e["restante_m"], e["restante_s"])
        if nav.chegou and not self._fim_agendado:
            self._fim_agendado = True
            Clock.schedule_once(lambda dt: self.encerrar_navegacao(chegou=True), 5)
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

        def todas():
            primeira = rotas.pedir_rota(origem, alvo, rumo, d["nome"])
            return rotas.pedir_alternativas(origem, alvo, rumo, d["nome"], [primeira])

        def prontas(lista):
            if pedido == self._pedido and self.nav is not None:
                tela.mostrar_escolha_nav(lista)

        def falhou(erro):
            if pedido == self._pedido and self.nav is not None:
                tela.fechar_escolha_nav()
                tela.mensagem("Sem internet para calcular rotas.", tema.LARANJA)
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

    def _recalcular(self):
        if self.destino is None or self.posicao is None:
            return
        self._recalculando = True
        self.voz.falar(["recalculando"], 2)
        origem, rumo, destino = self.posicao, self.rumo_recente(), self.destino
        rede.em_segundo_plano(
            lambda: rotas.pedir_rota(origem, (destino["lat"], destino["lon"]), rumo, destino["nome"]),
            self._recalculou, self._recalculo_falhou)

    def _recalculou(self, rota):
        self._recalculando = False
        if self.nav is None:
            return
        self.nav.trocar_rota(rota)
        self.gps.seguir_rota(rota.pontos)
        if self.corrida is not None:
            self.corrida.trocar_rota(rota)
        self.na_tela(lambda: self.sm.get_screen("mapa").trocar_rota(rota))

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

    def salvar_viagem_atual(self):
        resultado = self.viagem.finalizar()
        self.fundo.sincronizar()
        if not resultado:
            return None
        resumo, pontos = resultado
        if resumo["distancia_m"] < DISTANCIA_MINIMA_M:
            # não salva viagem vazia (antes bastavam 5 leituras: ficar parado
            # 5 s com sinal salvava uma viagem de "0 m")
            return None
        self.ultima_salva_m = resumo["distancia_m"]
        self._hoje = None
        return self.banco.salvar_viagem(resumo, pontos)

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
