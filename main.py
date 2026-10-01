"""GT-HUD: navegação de bike (mapa, rota, curva a curva, subidas, voz) e
velocímetro GPS com registro de viagens, para a Ouxi GT20."""
import json
import os
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import FadeTransition, ScreenManager

import android_utils
import rede
import rota as rotas
import tema
from ajustes import Ajustes
from banco import Banco
from filtro import FiltroVelocidade
from gps_service import ServicoGPS
from navegacao import P_INFO, Navegacao
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
GPS_PERDIDO_FALA_S = 10     # navegando sem sinal por isso: o assistente avisa
RECALCULO_ESPERA_S = 12     # depois de falhar, espera antes de tentar de novo
MAX_RECENTES = 8


class GTHudApp(App):
    title = "GT-HUD"

    def build(self):
        Window.clearcolor = tema.FUNDO
        Window.softinput_mode = "below_target"  # teclado não cobre o campo da busca
        Window.bind(on_keyboard=self._tecla)

        pasta = self.user_data_dir
        self.ajustes = Ajustes(pasta)
        self.banco = Banco(pasta)
        self.filtro = FiltroVelocidade(alfa=self.ajustes["alfa"])
        self.viagem = Viagem()
        self.gps = ServicoGPS(self._ao_receber_gps, self._ao_status_gps)
        self.voz = Voz(pasta)
        self.voz.ligada = self.ajustes["voz"]

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
        self.nav = None              # Navegacao durante a navegação
        self.estado_nav = None       # o que a navegação mostra na tela
        self.rota_previa = None
        self.destino = None
        self._recalculando = False
        self._t_falha_recalculo = 0.0
        self._fim_agendado = False
        self._saudou = False
        self._avisou_gps_perdido = False
        self._pilha_telas = []
        self._caminho_recentes = os.path.join(pasta, "recentes.json")
        self.recentes = self._ler_recentes()

        self.sm = ScreenManager(transition=FadeTransition(duration=0.18))
        self.sm.add_widget(TelaBoot(name="boot"))
        self.sm.add_widget(TelaMapa(name="mapa"))
        self.sm.add_widget(TelaBusca(name="busca"))
        self.sm.add_widget(TelaHUD(name="hud"))
        self.sm.add_widget(TelaViagens(name="viagens"))
        self.sm.add_widget(TelaDetalhe(name="detalhe"))
        self.sm.add_widget(TelaConfig(name="config"))
        Clock.schedule_interval(self._vigiar_gps, 2.0)
        return self.sm

    # --- ciclo de vida ---------------------------------------------------
    def on_start(self):
        self.aplicar_tela_ligada()
        self.aplicar_orientacao()
        self.solicitar_gps()

    def on_pause(self):
        return True  # não fecha o app ao trocar de tela no celular

    def on_resume(self):
        self.aplicar_tela_ligada()
        self.aplicar_orientacao()

    def on_stop(self):
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
        """(cor, texto) curtos do GPS para o canto do mapa."""
        sat = self.gps.satelites()
        if self.gps_desligado:
            return tema.VERMELHO, "Localizacao do\ncelular desligada"
        if self.gps.modo == "SIM":
            return tema.LARANJA, "Simulador  %d m" % (self.precisao or 0)
        if self.sinal_ok():
            prec = self.precisao or 0
            texto = "GPS  %d m" % prec + ("\n%d satelites" % sat[1] if sat and sat[1] else "")
            return (tema.VERDE if prec <= 10 else tema.LARANJA), texto
        if self.sinal_fraco():
            return tema.LARANJA, "Sinal fraco: %d m" % (self.precisao_ultima or 0)
        texto = "Sem sinal do GPS" if self.ja_teve_sinal else "Buscando GPS"
        if sat and sat[0]:
            texto += "\n%d vistos, %d em uso" % sat
        return (tema.VERMELHO if self.ja_teve_sinal else tema.LARANJA), texto

    def rumo_para_mapa(self):
        return self.rumo

    def _ao_receber_gps(self, d):
        self.gps_desligado = False
        agora = time.monotonic()
        precisao = d.get("accuracy")
        self._t_leitura = agora
        self.precisao_ultima = precisao
        if not self.filtro.leitura_valida(precisao):
            self._avisar(None)
            return
        self._t_valida = agora
        self.ja_teve_sinal = True
        self.precisao = precisao
        if d.get("speed") is None:
            vel = self.filtro.valor  # fix sem velocidade: mantém a última
        else:
            vel = self.filtro.atualizar(d["speed"])
        self.posicao = (d["lat"], d["lon"])
        if d.get("bearing") is not None and vel >= RUMO_MIN_KMH:
            self.rumo = d["bearing"]
        if not self._saudou:
            self._saudou = True
            self.voz.falar(["bem_vindo"], P_INFO)
        # antes de registrar: se retomou agora, esta leitura já entra
        self.viagem.checar_pausa_auto(vel, self.ajustes["pausa_auto"])
        self.viagem.registrar(d["lat"], d["lon"], vel)
        self._checar_limite(vel)
        if self.nav is not None:
            self._navegar(d["lat"], d["lon"], vel, agora)
        self._avisar(vel)

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

    def _vigiar_gps(self, dt):
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
        if self.posicao is None:
            tela.previa_erro("Esperando o sinal do GPS para calcular a rota.")
            return
        origem, rumo = self.posicao, self.rumo
        rede.em_segundo_plano(
            lambda: rotas.pedir_rota(origem, (lugar["lat"], lugar["lon"]), rumo, lugar["nome"]),
            self._rota_pronta, self._rota_falhou)

    def _rota_pronta(self, rota):
        if self.destino is None:
            return  # cancelou enquanto calculava
        self.rota_previa = rota
        self.sm.get_screen("mapa").mostrar_previa(rota)

    def _rota_falhou(self, erro):
        if self.destino is None:
            return
        self.sm.get_screen("mapa").previa_erro("Nao consegui calcular a rota. Confira a internet.")
        self.voz.falar(["sem_internet"], P_INFO)

    def cancelar_previa(self):
        self.rota_previa = None
        self.destino = None
        self.sm.get_screen("mapa").modo_livre()

    def iniciar_navegacao(self):
        rota = self.rota_previa
        if rota is None:
            return
        self.nav = Navegacao(rota, self.voz.falar, self.ajustes["avisar_subidas"])
        self.estado_nav = None
        self._fim_agendado = False
        if self.viagem.estado == Viagem.PARADA:
            self.viagem.iniciar()  # a navegação grava a viagem sozinha
        self.gps.seguir_rota(rota.pontos)
        self.sm.get_screen("mapa").modo_navegando(rota)

    def encerrar_navegacao(self, chegou=False):
        if self.nav is None:
            return
        self.nav = None
        self.estado_nav = None
        self.rota_previa = None
        self.destino = None
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
        self.estado_nav = nav.atualizar(lat, lon, vel, agora)
        if nav.chegou and not self._fim_agendado:
            self._fim_agendado = True
            Clock.schedule_once(lambda dt: self.encerrar_navegacao(chegou=True), 5)
        elif (nav.recalcular_pedido and not self._recalculando
              and agora - self._t_falha_recalculo > RECALCULO_ESPERA_S):
            self._recalcular()

    def _recalcular(self):
        if self.destino is None or self.posicao is None:
            return
        self._recalculando = True
        self.voz.falar(["recalculando"], 2)
        origem, rumo, destino = self.posicao, self.rumo, self.destino
        rede.em_segundo_plano(
            lambda: rotas.pedir_rota(origem, (destino["lat"], destino["lon"]), rumo, destino["nome"]),
            self._recalculou, self._recalculo_falhou)

    def _recalculou(self, rota):
        self._recalculando = False
        if self.nav is None:
            return
        self.nav.trocar_rota(rota)
        self.gps.seguir_rota(rota.pontos)
        self.sm.get_screen("mapa").trocar_rota(rota)

    def _recalculo_falhou(self, erro):
        self._recalculando = False
        self._t_falha_recalculo = time.monotonic()
        if self.nav is not None:
            self.nav.desistir_de_recalcular()
            self.voz.falar(["sem_internet"], P_INFO)

    # --- destinos recentes ----------------------------------------------------
    def _ler_recentes(self):
        try:
            with open(self._caminho_recentes, encoding="utf-8") as f:
                return json.load(f)[:MAX_RECENTES]
        except (OSError, ValueError):
            return []

    def _guardar_recente(self, lugar):
        item = {k: lugar[k] for k in ("nome", "endereco", "lat", "lon") if k in lugar}
        self.recentes = [r for r in self.recentes
                         if (round(r["lat"], 4), round(r["lon"], 4))
                         != (round(item["lat"], 4), round(item["lon"], 4))]
        self.recentes.insert(0, item)
        del self.recentes[MAX_RECENTES:]
        try:
            with open(self._caminho_recentes, "w", encoding="utf-8") as f:
                json.dump(self.recentes, f)
        except OSError:
            pass

    # --- viagem ----------------------------------------------------------
    def salvar_viagem_atual(self):
        resultado = self.viagem.finalizar()
        if not resultado:
            return None
        resumo, pontos = resultado
        if resumo["distancia_m"] < DISTANCIA_MINIMA_M:
            # não salva viagem vazia (antes bastavam 5 leituras: ficar parado
            # 5 s com sinal salvava uma viagem de "0 m")
            return None
        self.ultima_salva_m = resumo["distancia_m"]
        return self.banco.salvar_viagem(resumo, pontos)

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
