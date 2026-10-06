"""Navegação com o app MINIMIZADO (pedido do dono: rota ativa + app
minimizado = continua rodando, com notificação e uma bolha mostrando km e
minutos até o destino, como a 99).

Como funciona:
- Ao começar a rota, liga o serviço Android de primeiro plano
  (java/.../ServicoNavegacao.java): é ele que faz o Android manter o GPS a
  1 posição/s e não matar o app; e mostra a notificação fixa.
- Minimizou (on_pause): o Kivy para o relógio dele (nada de Clock), mas o
  Python continua (ele solta a vez na espera). Uma thread daqui passa a
  fazer o que o Clock fazia: lê o GPS, roda a navegação (curvas, avisos,
  recálculo), faz a voz andar e atualiza notificação e bolha
  (java/.../Bolha.java). NADA de mexer em widget fora da thread do Kivy:
  o que é de tela fica para quando o app voltar (app.na_tela).
- Voltou (on_resume): a thread para e o app segue de onde ela parou.
"""
import threading
import time

import rede
from falas import texto_manobra
from util import fmt_dist, fmt_dist_nav, fmt_duracao, fmt_hora_chegada, fmt_tempo

INTERVALO_S = 0.2          # a thread confere o GPS 5x/s (o GPS manda 1x/s)
AVISO_A_CADA_S = 2.0       # notificação/bolha: no máximo 1 atualização a cada isso
VIGIA_A_CADA_S = 2.0       # "perdi o sinal do GPS" (no app aberto é o Clock)


def textos(app):
    """(título da notificação, texto, linha 1 da bolha, linha 2 da bolha)."""
    nav, e = app.nav, app.estado_nav
    if nav is None:
        v = getattr(app, "viagem", None)
        if v is None or v.estado == v.PARADA:
            return "GT-HUD", "", "", ""
        # só gravando a viagem (sem rota): distância e tempo
        dist, tempo = fmt_dist(v.distancia_m), fmt_tempo(v.tempo_total_s)
        if v.estado == v.PAUSADA:
            return "Viagem pausada  ·  %s" % dist, "Volta a gravar quando você andar.", dist, "pausada"
        return "Gravando viagem  ·  %s  ·  %s" % (dist, tempo), "GT-HUD segue gravando com a tela apagada.", dist, tempo
    if nav.chegou:
        return "Você chegou!", "GT-HUD: destino alcançado.", "Chegou", ""
    if not e:
        return "GT-HUD navegando", "Esperando o GPS...", "...", ""
    minutos, km = fmt_duracao(e["restante_s"]), fmt_dist_nav(e["restante_m"])
    titulo = "%s  ·  %s  ·  chega às %s" % (minutos, km, fmt_hora_chegada(e["restante_s"]))
    m = e.get("manobra")
    if e.get("fora_da_rota"):
        texto = "Fora da rota: recalculando..." if app.recalculando else "Fora da rota"
    elif m is not None:
        texto = "%s em %s" % (texto_manobra(m["acao"], m.get("saida")), fmt_dist_nav(e["dist_manobra"]))
        if m.get("ruas"):
            texto += " (%s)" % m["ruas"]
    else:
        texto = "Siga em frente"
    return titulo, texto, minutos, km


class _Android:
    """Ponte para o Java (serviço, notificação, bolha). No PC não faz nada
    (só escreve no registro, para os testes)."""

    def __init__(self):
        self.servico = self.bolha = self.ctx = None
        try:
            from jnius import autoclass
            self.ctx = autoclass("org.kivy.android.PythonActivity").mActivity
            self.servico = autoclass("org.kirito.gthud.ServicoNavegacao")
            self.bolha = autoclass("org.kirito.gthud.Bolha")
        except Exception as e:
            if not isinstance(e, ImportError):
                print("[fundo] sem servico/bolha:", e)

    def _chamar(self, nome, *args):
        try:
            return nome(*args)
        except Exception as e:
            print("[fundo] falhou:", getattr(nome, "__name__", nome), e)
            return None

    def iniciar(self):
        if self.servico is not None:
            self._chamar(self.servico.iniciar, self.ctx)
            self._pedir_notificacoes()

    def parar(self):
        if self.servico is not None:
            self._chamar(self.servico.parar, self.ctx)
        self.esconder_bolha()

    def notificar(self, titulo, texto):
        if self.servico is not None:
            self._chamar(self.servico.atualizar, self.ctx, titulo, texto)

    def bolha_permitida(self):
        if self.bolha is None:
            return False
        return bool(self._chamar(self.bolha.temPermissao, self.ctx))

    def pedir_bolha(self):
        if self.bolha is not None:
            self._chamar(self.bolha.pedirPermissao, self.ctx)

    def mostrar_bolha(self, a, b):
        if self.bolha is not None:
            self._chamar(self.bolha.atualizar, a, b)
            self._chamar(self.bolha.mostrar, self.ctx)

    def atualizar_bolha(self, a, b):
        if self.bolha is not None:
            self._chamar(self.bolha.atualizar, a, b)

    def esconder_bolha(self):
        if self.bolha is not None:
            self._chamar(self.bolha.esconder)

    @staticmethod
    def _pedir_notificacoes():
        """Android 13+: sem essa permissão a notificação não aparece (o
        serviço funciona do mesmo jeito)."""
        try:
            from android.permissions import check_permission, request_permissions
            p = "android.permission.POST_NOTIFICATIONS"
            if not check_permission(p):
                request_permissions([p])
        except Exception:
            pass


class SegundoPlano:
    def __init__(self, app, android=None):
        self.app = app
        self.android = android or _Android()
        self.minimizado = False
        self._thread = None
        self._parar = threading.Event()
        self._fila = []                 # respostas da internet chegando com o app minimizado
        self._trava = threading.Lock()
        self._t_aviso = 0.0
        self._ligado = False            # o serviço Android está no ar
        self.leituras_no_fundo = 0      # (diagnóstico e testes)

    # --- rota ou gravação começou / acabou -------------------------------------------
    def ativo(self):
        """Há o que manter vivo com o app minimizado: rota ativa OU viagem
        sendo gravada (pausada também: a pausa automática precisa do GPS
        para voltar a gravar). Até a 1.0.21 só a rota contava: gravando sem
        rota, apagar a tela parava a contagem."""
        v = getattr(self.app, "viagem", None)
        return self.app.nav is not None or (v is not None and v.estado != v.PARADA)

    def sincronizar(self):
        """Liga ou desliga o serviço Android conforme o estado do app.
        Chamar sempre que a rota ou a gravação começar/acabar."""
        deve = self.ativo() and bool(self.app.ajustes["segundo_plano"])
        if deve and not self._ligado:
            self._ligado = True
            self.android.iniciar()
            self.atualizar(forcar=True)
        elif not deve and self._ligado:
            self._ligado = False
            self.android.parar()
        elif deve:
            self.atualizar(forcar=True)

    def comecou(self):
        self.sincronizar()

    def terminou(self):
        """Desliga de vez (app fechando)."""
        self._ligado = False
        self.android.parar()

    def atualizar(self, forcar=False):
        """Notificação (e bolha, se minimizado) com km/minutos/próxima curva."""
        agora = time.monotonic()
        if not self._ligado or (not forcar and agora - self._t_aviso < AVISO_A_CADA_S):
            return
        self._t_aviso = agora
        titulo, texto, l1, l2 = textos(self.app)
        self.android.notificar(titulo, texto)
        if self.minimizado:
            self.android.atualizar_bolha(l1, l2)

    # --- app minimizado / de volta -------------------------------------------------
    def ao_pausar(self):
        self.sincronizar()  # garantia: se a gravação começou por um caminho que não avisou
        if not self._ligado:
            return
        self.minimizado = True
        if self.app.ajustes["bolha"] and self.android.bolha_permitida():
            _, _, l1, l2 = textos(self.app)
            self.android.mostrar_bolha(l1, l2)
        with self._trava:
            self._fila = []
            rede.desviar_respostas(self._receber)
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, name="segundo-plano", daemon=True)
        self._thread.start()
        print("[fundo] app minimizado: navegação segue em segundo plano")

    def ao_voltar(self):
        if not self.minimizado:
            return
        self.minimizado = False
        self.android.esconder_bolha()
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._trava:
            rede.desviar_respostas(None)
            pendentes, self._fila = self._fila, []
        from kivy.clock import Clock
        for fn, valor in pendentes:  # o que chegou da internet e não deu tempo de tratar
            Clock.schedule_once(lambda dt, f=fn, v=valor: f(v))
        print("[fundo] app de volta (%d leituras do GPS em segundo plano)" % self.leituras_no_fundo)

    def _receber(self, fn, valor):
        """Resposta da internet (ex.: rota recalculada) com o app minimizado:
        quem trata é a thread daqui, não o Clock (que está parado)."""
        with self._trava:
            if self.minimizado:
                self._fila.append((fn, valor))
                return
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: fn(valor))

    def _laco(self):
        t_vigia = time.monotonic()
        t_erro = 0.0
        try:
            while not self._parar.wait(INTERVALO_S):
                # um erro numa volta não pode acabar com a navegação em segundo
                # plano (antes a thread morria e a rota parava até reabrir o app)
                try:
                    with self._trava:
                        prontas, self._fila = self._fila, []
                    for fn, valor in prontas:
                        fn(valor)
                    d = self.app.gps.ler_direto()
                    if d is not None:
                        self.leituras_no_fundo += 1
                        self.app.processar_leitura(d)
                        self.atualizar()
                    self.app.voz.bombear()
                    self.app.conferir_fim()   # chegou com o app minimizado: encerra a rota daqui
                    if time.monotonic() - t_vigia >= VIGIA_A_CADA_S:
                        t_vigia = time.monotonic()
                        self.app.vigiar_gps()
                except Exception:
                    if time.monotonic() - t_erro > 10.0:   # o mesmo erro a cada volta: anota de vez em quando
                        t_erro = time.monotonic()
                        import traceback
                        print("[fundo] erro em segundo plano (segue rodando):\n" + traceback.format_exc())
        finally:
            try:  # thread que falou com o Java precisa se soltar da JVM antes de acabar
                import jnius
                jnius.detach()
            except Exception:
                pass
