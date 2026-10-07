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

import mini_mapa
import rede
import tema
from rota import distancia_m
from falas import texto_manobra
from util import fmt_dist, fmt_dist_nav, fmt_duracao, fmt_hora_chegada, fmt_tempo

ANCORA_MAX_M = 1200        # longe disso da âncora, o painel ganha uma âncora nova (números pequenos)
RUAS_A_CADA_M = 140        # o mini mapa do painel busca as ruas de novo a cada isso andado
PAINEL_A_CADA_S = 0.9      # painel flutuante: acompanha cada leitura do GPS
DESENHO_FRENTE_M = 420     # quanto de rota à frente vai para o painel (ele mostra ~260 m e anda sozinho)
DESENHO_ATRAS_M = 70
DESENHO_PASSO_M = 10
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


def desenho_da_rota(nav, ancora=None):
    """O trecho da rota em volta da pessoa, para o painel flutuante desenhar
    no lugar do mapa: ("x,y;x,y;...", início m, aqui m).
    Os pontos são metros (leste, norte) a partir da `ancora` (lat, lon), a
    mesma das ruas do mini mapa (sem âncora: a partir do primeiro), tirados da rota
    a cada DESENHO_PASSO_M em distâncias "redondas" (os mesmos pontos a cada
    envio: o desenho não treme); o primeiro fica a `início` metros do começo
    da rota e a pessoa está em `aqui`. Quem gira (frente para cima) e faz o
    desenho andar entre uma posição e outra é o painel."""
    rota = nav.rota
    if rota is None or len(rota.pontos) < 2 or rota.total_m <= 0:
        return "", 0.0, 0.0
    aqui = max(0.0, min(rota.total_m, nav.dist_feita))
    inicio = max(0.0, math.floor((aqui - DESENHO_ATRAS_M) / DESENHO_PASSO_M) * DESENHO_PASSO_M)
    fim = min(rota.total_m, aqui + DESENHO_FRENTE_M)
    lat0, lon0 = ancora if ancora is not None else rota.ponto_em(inicio)[:2]
    grau = 111195.0   # metros por grau na mesma esfera das distâncias da rota (o painel soma os trechos)
    k = math.cos(math.radians(lat0)) * grau
    pontos = []
    d = inicio
    while True:
        lat, lon, _ = rota.ponto_em(d)
        pontos.append("%.1f,%.1f" % ((lon - lon0) * k, (lat - lat0) * grau))
        if d >= fim:
            break
        d = min(fim, d + DESENHO_PASSO_M)
    return ";".join(pontos), inicio, aqui


def dados_do_painel(app, ancora=None):
    """(distância, instrução, rua, velocidade, resto, desenho, nível de alerta,
    início m, aqui m, velocidade m/s) para o painel flutuante; None se não há
    rota. Os três últimos servem para o desenho andar entre as posições."""
    nav, e = app.nav, app.estado_nav
    if nav is None:
        return None
    vel = "%d" % round(app.filtro.previsto()) if getattr(app, "filtro", None) is not None else "0"
    if nav.chegou:
        return ("Chegou", "Você chegou ao destino", "", vel, "", "", 0, 0.0, 0.0, 0.0)
    pontos, inicio, aqui = desenho_da_rota(nav, ancora)
    fora = bool(e and e.get("fora_da_rota"))
    andar = (pontos, 0, inicio, aqui, 0.0 if fora else float(getattr(nav, "_vel_ms", 0.0)))

    def desenho_da_rota_(nivel):   # (desenho, alerta, início, aqui, m/s)
        return (andar[0], nivel) + andar[2:]
    if not e:
        return ("...", "Esperando o GPS", "", vel, "") + desenho_da_rota_(0)
    resto = "%s · %s · %s" % (fmt_duracao(e["restante_s"]), fmt_dist_nav(e["restante_m"]),
                              fmt_hora_chegada(e["restante_s"]))
    m = e.get("manobra")
    alerta = 0
    a = e.get("alerta")
    if a is not None and a.get("tipo") == "avenida" and a.get("em_m", 1) <= 0:
        alerta = 2 if a.get("nivel", 2) >= 3 else 1      # andando numa avenida
    if e.get("fora_da_rota"):
        return ("Fora da rota", "Recalculando..." if app.recalculando else "Volte para a rota", "",
                vel, resto) + desenho_da_rota_(2)
    if m is None:
        return ("", "Siga em frente", "", vel, resto) + desenho_da_rota_(alerta)
    return (fmt_dist_nav(e["dist_manobra"]), texto_manobra(m["acao"], m.get("saida")), m.get("ruas") or "",
            vel, resto) + desenho_da_rota_(alerta)


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
            try:   # separado: sem o painel, a bolha e o serviço continuam valendo
                self.painel = autoclass("org.kirito.gthud.PainelFlutuante")
            except Exception as e:
                print("[fundo] sem o painel flutuante:", e)
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
        """True se o pedido foi feito (se abriu mesmo, ver estado_painel)."""
        if self.painel is None:
            return False
        self.atualizar_painel(dados, claro)
        self._chamar(self.painel.mostrar, self.ctx)
        return True

    def estado_painel(self):
        """(estado, erro): 1 na tela, 0 fechado/ainda abrindo, -1 não abriu."""
        if self.painel is None:
            return -1, "sem a classe do painel"
        try:
            return int(self.painel.estado), str(self.painel.erro)
        except Exception as e:
            return -1, str(e)

    def atualizar_painel(self, dados, claro):
        if self.painel is not None and dados is not None:
            distancia, instrucao, rua, vel, resto, desenho, alerta, inicio, aqui, vel_ms = dados
            self._chamar(self.painel.atualizar, distancia, instrucao, rua, vel, resto, desenho,
                         bool(claro), int(alerta), float(inicio), float(aqui), float(vel_ms))

    def ruas_painel(self, texto):
        """As ruas de perto para o mini mapa do painel (mini_mapa.em_texto)."""
        if self.painel is not None:
            self._chamar(self.painel.ruas, texto)

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
        self._conferir_painel_em = None
        # mini mapa do painel: âncora das coordenadas e as ruas de perto
        self._ancora = None             # (lat, lon): origem dos metros mandados ao painel
        self._ruas_centro = None        # onde as ruas foram tiradas pela última vez
        self._ruas_prontas = None       # (texto, âncora) esperando para ir ao painel
        self._ruas_buscando = False
        self._ler_tile = None           # função que lê um arquivo do mapa (z, x, y)
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
        if self._conferir_painel_em is not None and agora >= self._conferir_painel_em:
            # abriu mesmo? Se o Android recusou, cai para a bolha e anota o motivo
            self._conferir_painel_em = None
            estado, erro = self.android.estado_painel()
            print("[fundo] painel flutuante: estado=%s %s" % (estado, erro))
            if estado == -1:
                self._painel_a_vista = False
                _, _, l1, l2 = textos(self.app)
                self.android.mostrar_bolha(l1, l2)
                return
        if agora - self._t_painel < PAINEL_A_CADA_S:
            return
        self._t_painel = agora
        self._cuidar_das_ruas()
        self.android.atualizar_painel(dados_do_painel(self.app, self._ancora), tema.claro())

    # --- mini mapa do painel: as ruas de perto ---------------------------------------
    def _preparar_mini_mapa(self):
        """Ao minimizar (thread da tela): pega com o mapa do app a função que
        lê os arquivos de mapa e zera a âncora."""
        self._ancora = self._ruas_centro = self._ruas_prontas = None
        self._ler_tile = None
        try:
            self._ler_tile = self.app.sm.get_screen("mapa").mapa.fonte._ler_ou_baixar
        except Exception:
            pass                       # sem o mapa (testes): o painel fica só com a rota
        self._cuidar_das_ruas()

    def _cuidar_das_ruas(self):
        """Mantém a âncora perto da pessoa e as ruas em dia: a cada
        RUAS_A_CADA_M andados, tira de novo (numa thread à parte: ler o arquivo
        do mapa pode demorar) e manda ao painel quando ficar pronto."""
        nav = self.app.nav
        if nav is None or nav.rota is None or len(nav.rota.pontos) < 2:
            return
        lat, lon, _ = nav.rota.ponto_em(max(0.0, min(nav.rota.total_m, nav.dist_feita)))
        aqui = (lat, lon)
        if self._ancora is None or distancia_m(self._ancora, aqui) > ANCORA_MAX_M:
            self._ancora, self._ruas_centro, self._ruas_prontas = aqui, None, None
            self.android.ruas_painel("")       # as ruas antigas estavam na outra âncora
        pronto = self._ruas_prontas
        if pronto is not None:
            self._ruas_prontas = None
            if pronto[1] == self._ancora:
                self.android.ruas_painel(pronto[0])
        if (self._ler_tile is None or self._ruas_buscando
                or (self._ruas_centro is not None and distancia_m(self._ruas_centro, aqui) < RUAS_A_CADA_M)):
            return
        self._ruas_buscando = True
        self._ruas_centro = aqui
        ancora, ler = self._ancora, self._ler_tile

        def buscar():
            try:
                texto = mini_mapa.em_texto(mini_mapa.ruas_perto(ler, lat, lon, ancora))
                self._ruas_prontas = (texto, ancora)
            except Exception as e:
                print("[fundo] ruas do mini mapa:", e)
            finally:
                self._ruas_buscando = False
        threading.Thread(target=buscar, name="mini-mapa", daemon=True).start()

    # --- app minimizado / de volta -------------------------------------------------
    def ao_pausar(self):
        self.sincronizar()  # garantia: se a gravação começou por um caminho que não avisou
        if not self._ligado:
            return
        self.minimizado = True
        tipo = self._tipo_flutuante()
        self._painel_a_vista = False
        self._conferir_painel_em = None
        permitida = self.android.bolha_permitida()
        # (no diagnóstico: por que a janela apareceu ou não)
        print("[fundo] janela ao minimizar: tipo=%s, permissao de sobrepor=%s" % (tipo, permitida))
        if tipo is not None and permitida:
            dados = None
            if tipo == "painel":
                try:
                    self._preparar_mini_mapa()
                    dados = dados_do_painel(self.app, self._ancora)
                except Exception as e:
                    print("[fundo] dados do painel:", e)
            if dados is not None and self.android.mostrar_painel(dados, tema.claro()):
                # retângulo no meio da tela com o caminho à frente e a velocidade
                self._painel_a_vista = True
                self._conferir_painel_em = time.monotonic() + 1.5
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
