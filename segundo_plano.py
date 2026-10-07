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
import math
import threading
import time

import rede
import tema
from falas import texto_manobra
from util import fmt_dist, fmt_dist_nav, fmt_duracao, fmt_hora_chegada, fmt_tempo

PAINEL_A_CADA_S = 0.9      # painel flutuante: acompanha cada leitura do GPS
DESENHO_FRENTE_M = 280     # quanto de rota à frente vai no desenho do painel
DESENHO_ATRAS_M = 60
DESENHO_PASSO_M = 12
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


def desenho_da_rota(nav):
    """O caminho dos próximos metros visto de cima, com a FRENTE para cima e
    a pessoa na origem: "x,y;x,y;..." em metros inteiros (x = direita, y =
    frente). É o que o painel flutuante desenha no lugar do mapa."""
    rota = nav.rota
    if rota is None or len(rota.pontos) < 2 or rota.total_m <= 0:
        return ""
    aqui = max(0.0, min(rota.total_m, nav.dist_feita))
    lat0, lon0, rumo = rota.ponto_em(aqui, nav.seg)
    r = math.radians(rumo)
    sen, cos = math.sin(r), math.cos(r)
    k = math.cos(math.radians(lat0)) * 111320.0
    pontos = []
    d = max(0.0, aqui - DESENHO_ATRAS_M)
    fim = min(rota.total_m, aqui + DESENHO_FRENTE_M)
    while True:
        lat, lon, _ = rota.ponto_em(d, nav.seg if d >= aqui else 0)
        leste, norte = (lon - lon0) * k, (lat - lat0) * 110540.0
        pontos.append("%d,%d" % (round(leste * cos - norte * sen), round(leste * sen + norte * cos)))
        if d >= fim:
            break
        d = min(fim, d + DESENHO_PASSO_M)
    return ";".join(pontos)


def dados_do_painel(app):
    """(distância, instrução, rua, velocidade, resto, desenho, nível de alerta)
    para o painel flutuante; None se não há rota."""
    nav, e = app.nav, app.estado_nav
    if nav is None:
        return None
    vel = "%d" % round(app.filtro.previsto()) if getattr(app, "filtro", None) is not None else "0"
    if nav.chegou:
        return ("Chegou", "Você chegou ao destino", "", vel, "", "", 0)
    if not e:
        return ("...", "Esperando o GPS", "", vel, "", desenho_da_rota(nav), 0)
    resto = "%s · %s · %s" % (fmt_duracao(e["restante_s"]), fmt_dist_nav(e["restante_m"]),
                              fmt_hora_chegada(e["restante_s"]))
    m = e.get("manobra")
    alerta = 0
    a = e.get("alerta")
    if a is not None and a.get("tipo") == "avenida" and a.get("em_m", 1) <= 0:
        alerta = 2 if a.get("nivel", 2) >= 3 else 1      # andando numa avenida
    if e.get("fora_da_rota"):
        return ("Fora da rota", "Recalculando..." if app.recalculando else "Volte para a rota", "",
                vel, resto, desenho_da_rota(nav), 2)
    if m is None:
        return ("", "Siga em frente", "", vel, resto, desenho_da_rota(nav), alerta)
    return (fmt_dist_nav(e["dist_manobra"]), texto_manobra(m["acao"], m.get("saida")), m.get("ruas") or "",
            vel, resto, desenho_da_rota(nav), alerta)


def feito(app):
    """Quanto da rota já foi, de 0 a 100 (-1 sem rota)."""
    nav = app.nav
    rota = getattr(nav, "rota", None)
    if rota is None or not getattr(rota, "total_m", 0):
        return -1
    return int(max(0.0, min(1.0, nav.dist_feita / rota.total_m)) * 100)


class _Android:
    """Ponte para o Java (serviço, notificação, bolha). No PC não faz nada
    (só escreve no registro, para os testes)."""

    def __init__(self):
        self.servico = self.bolha = self.painel = self.ctx = None
        try:
            from jnius import autoclass
            self.ctx = autoclass("org.kivy.android.PythonActivity").mActivity
            self.servico = autoclass("org.kirito.gthud.ServicoNavegacao")
            self.bolha = autoclass("org.kirito.gthud.Bolha")
            self.painel = autoclass("org.kirito.gthud.PainelFlutuante")
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
        self.esconder_painel()

    def estilo(self, claro, feito):
        """Tema do app e % da rota já feita (-1 = sem barra): pintam a
        notificação e a bolha."""
        if self.servico is not None:
            self._chamar(self.servico.estilo, bool(claro), int(feito))

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

    # painel flutuante (retângulo com o caminho à frente e a velocidade)
    def mostrar_painel(self, dados, claro):
        if self.painel is not None:
            self.atualizar_painel(dados, claro)
            self._chamar(self.painel.mostrar, self.ctx)

    def atualizar_painel(self, dados, claro):
        if self.painel is not None and dados is not None:
            distancia, instrucao, rua, vel, resto, desenho, alerta = dados
            self._chamar(self.painel.atualizar, distancia, instrucao, rua, vel, resto, desenho,
                         bool(claro), int(alerta))

    def esconder_painel(self):
        if self.painel is not None:
            self._chamar(self.painel.esconder)

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
        self._t_painel = 0.0
        self._painel_a_vista = False
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
        self.android.estilo(tema.claro(), feito(self.app))
        self.android.notificar(titulo, texto)
        if self.minimizado and not self._painel_a_vista:
            self.android.atualizar_bolha(l1, l2)

    def _tipo_flutuante(self):
        """ "painel", "bolha" ou None (desligado nos Ajustes)."""
        if not self.app.ajustes["bolha"]:
            return None
        try:
            return self.app.ajustes["flutuante_tipo"]
        except KeyError:
            return "bolha"

    def atualizar_painel(self):
        """O painel flutuante acompanha cada leitura (a notificação, não)."""
        if not (self.minimizado and self._painel_a_vista):
            return
        agora = time.monotonic()
        if agora - self._t_painel < PAINEL_A_CADA_S:
            return
        self._t_painel = agora
        self.android.atualizar_painel(dados_do_painel(self.app), tema.claro())

    # --- app minimizado / de volta -------------------------------------------------
    def ao_pausar(self):
        self.sincronizar()  # garantia: se a gravação começou por um caminho que não avisou
        if not self._ligado:
            return
        self.minimizado = True
        tipo = self._tipo_flutuante()
        self._painel_a_vista = False
        if tipo is not None and self.android.bolha_permitida():
            dados = dados_do_painel(self.app) if tipo == "painel" else None
            if dados is not None:
                # retângulo no meio da tela com o caminho à frente e a velocidade
                self._painel_a_vista = True
                self.android.mostrar_painel(dados, tema.claro())
            else:
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
        self._painel_a_vista = False
        self.android.esconder_bolha()
        self.android.esconder_painel()
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
                    self.atualizar_painel()   # (a velocidade prevista anda entre as leituras)
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
