"""GT-HUD: velocímetro GPS e registro de viagens para a Ouxi GT20."""
import time

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import FadeTransition, ScreenManager

import android_utils
import tema
from ajustes import Ajustes
from banco import Banco
from filtro import FiltroVelocidade
from gps_service import ServicoGPS
from telas.boot import TelaBoot
from telas.config import TelaConfig
from telas.detalhe import TelaDetalhe
from telas.hud import TelaHUD
from telas.viagens import TelaViagens
from viagem import Viagem

# vibra uma vez ao passar do limite e só rearma depois de cair DESARME_KMH
# abaixo dele e de passar INTERVALO_VIBRA_S desde a última (senão vibraria
# sem parar andando em cima do limite)
DESARME_KMH = 2.0
INTERVALO_VIBRA_S = 15.0
VIBRA_TEMPOS = [0, 250, 150, 250]  # dois pulsos fortes: dá para sentir no guidão
VIBRA_FORCAS = [0, 255, 0, 255]


class GTHudApp(App):
    title = "GT-HUD"

    def build(self):
        Window.clearcolor = tema.FUNDO
        Window.bind(on_keyboard=self._tecla)

        pasta = self.user_data_dir
        self.ajustes = Ajustes(pasta)
        self.banco = Banco(pasta)
        self.filtro = FiltroVelocidade(alfa=self.ajustes["alfa"])
        self.viagem = Viagem()
        self.gps = ServicoGPS(self._ao_receber_gps, self._ao_status_gps)

        self.precisao = None
        self.gps_desligado = False
        self.ultima_salva_m = 0
        self._ouvintes = []
        self._alerta_armado = True
        self._ultima_vibracao = -INTERVALO_VIBRA_S

        self.sm = ScreenManager(transition=FadeTransition(duration=0.18))
        self.sm.add_widget(TelaBoot(name="boot"))
        self.sm.add_widget(TelaHUD(name="hud"))
        self.sm.add_widget(TelaViagens(name="viagens"))
        self.sm.add_widget(TelaDetalhe(name="detalhe"))
        self.sm.add_widget(TelaConfig(name="config"))
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

    # --- GPS -------------------------------------------------------------
    def solicitar_gps(self):
        android_utils.pedir_permissoes(self._resposta_permissao)

    def _resposta_permissao(self, ok):
        boot = self.sm.get_screen("boot")
        if ok or self.ajustes["simulador"]:
            self.gps.iniciar(usar_simulador=self.ajustes["simulador"])
            boot.aguardando_sinal()
        else:
            boot.permissao_negada()

    def aplicar_simulador(self, ligado):
        self.ajustes["simulador"] = ligado
        self.gps.parar()
        self.filtro.reset()
        self.gps_desligado = False
        self.solicitar_gps()

    def ouvir(self, funcao):
        """Telas se registram aqui para receber cada leitura (km/h ou None)."""
        self._ouvintes.append(funcao)

    def _avisar(self, vel):
        for f in self._ouvintes:
            f(vel)

    def _ao_receber_gps(self, d):
        self.gps_desligado = False
        precisao = d.get("accuracy")
        if not self.filtro.leitura_valida(precisao):
            self._avisar(None)
            return
        self.precisao = precisao
        if d.get("speed") is None:
            vel = self.filtro.valor  # fix sem velocidade: mantém a última
        else:
            vel = self.filtro.atualizar(d["speed"])
        # antes de registrar: se retomou agora, esta leitura já entra
        self.viagem.checar_pausa_auto(vel, self.ajustes["pausa_auto"])
        self.viagem.registrar(d["lat"], d["lon"], vel)
        self._checar_limite(vel)
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

    # --- viagem ----------------------------------------------------------
    def salvar_viagem_atual(self):
        resultado = self.viagem.finalizar()
        if not resultado:
            return None
        resumo, pontos = resultado
        if resumo["distancia_m"] < 20 and len(pontos) < 5:
            return None  # não salva viagem vazia
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
        if atual in ("viagens", "config"):
            self.sm.current = "hud"
            return True
        if atual == "hud" and self.viagem.estado != Viagem.PARADA:
            return True  # evita fechar o app sem querer durante a viagem
        return False


if __name__ == "__main__":
    GTHudApp().run()
