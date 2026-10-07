"""Compartilhar a corrida ao vivo (pedido do dono: mandar um link no
WhatsApp e a pessoa acompanhar numa página da web).

Como funciona:
- O dono tem um banco gratuito (Firebase Realtime Database, plano Spark, na
  conta Google dele); o endereço fica nos Ajustes do app, nunca no código
  (o repositório é público).
- Ao compartilhar, o app cria uma corrida com um código sorteado, impossível
  de adivinhar, e manda por HTTPS, a cada ENVIAR_A_CADA_S: posição,
  velocidade, quanto falta, e o caminho já feito. A rota vai uma vez (e de
  novo se for recalculada).
- A página (docs/acompanhar/index.html, no GitHub Pages) recebe no link o
  endereço do banco e o código, e fica lendo.
- Chegou ou encerrou: o app troca tudo por um aviso de fim. A posição e o
  caminho SOMEM do banco: o link antigo não mostra mais nada.

O que fica no banco:  corridas/<código>/s           senha da corrida (só o app sabe;
                                                     ninguém consegue ler)
                      corridas/<código>/pub/...     o que a página lê
As regras do banco (ver README) só deixam escrever numa corrida quem manda a
mesma senha que a criou, e não deixam listar as corridas.

Roda numa thread própria (a internet nunca trava a tela) e funciona com o
app minimizado. Sem internet por um tempo: o caminho acumulado segue no
próximo envio que der certo.
"""
import http.client
import json
import re
import secrets
import urllib.parse
import threading
import time

import rede
from rota import codificar_polyline, distancia_m

PAGINA = "https://kiritoagiota-ship-it.github.io/gt-hud/acompanhar/"
ENVIAR_A_CADA_S = 2.5        # (era 5 s: quem acompanhava via a posição bem atrasada)
PARADO_A_CADA_S = 20.0       # parado, não precisa mandar a mesma posição toda hora
TRILHA_PASSO_M = 12.0        # ponto novo no caminho feito a cada isso
TEMPO_REDE_S = 10
_ENDERECO = re.compile(r"^https://[a-z0-9-]+(\.[a-z0-9-]+)*\.(firebaseio\.com|firebasedatabase\.app)$")
_LOCAL = re.compile(r"^http://(localhost|127\.0\.0\.1):\d+$")   # servidor de teste no PC


def limpar_endereco(texto):
    """Endereço do banco como a pessoa colou -> "https://....firebaseio.com"
    (ou None se não é um endereço de Realtime Database)."""
    t = (texto or "").strip().lower().rstrip("/")
    if t and "://" not in t:
        t = "https://" + t
    if t.endswith(".json"):
        t = t[:-5].rstrip("/")
    return t if (_ENDERECO.match(t) or _LOCAL.match(t)) else None


def link(base, codigo):
    """Link que vai no WhatsApp. O que vem depois do "#" não é enviado ao
    servidor da página: só o navegador de quem abre lê."""
    return "%s#%s/%s" % (PAGINA, base.split("://", 1)[1], codigo)


def testar(base):
    """Escreve e lê uma corrida de teste: confere endereço e regras do
    banco. Devolve None se deu certo, ou o texto do problema."""
    codigo, senha = "teste-" + secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    url = "%s/corridas/%s" % (base, codigo)
    try:
        rede.enviar(url + ".json", {"s": senha, "pub": {"e": "teste", "fim": int(time.time())}}, "PUT", TEMPO_REDE_S)
        if (rede.baixar_json(url + "/pub.json", TEMPO_REDE_S) or {}).get("e") != "teste":
            return "O banco aceitou, mas não devolveu o que foi gravado."
    except Exception as e:
        codigo_http = getattr(e, "code", None)
        if codigo_http in (401, 403):
            return "O banco recusou: confira as regras (passo das regras no guia)."
        if codigo_http == 404:
            return "Endereço não encontrado: confira se copiou o do Realtime Database."
        return "Não consegui falar com o banco: confira a internet e o endereço."
    try:  # as regras não podem deixar ninguém ler a senha nem listar as corridas
        rede.baixar_json(url + "/s.json", TEMPO_REDE_S)
        return "As regras estão abertas demais (dá para ler a senha da corrida): cole as regras do guia."
    except Exception:
        return None


def encerrar_esquecida(base, codigo, senha):
    """Corrida que ficou aberta (o app fechou no meio): apaga posição e caminho."""
    rede.enviar("%s/corridas/%s.json" % (base, codigo),
                {"s": senha, "pub": {"fim": int(time.time()), "pos": {"e": "encerrou", "t": int(time.time())}}},
                "PUT", TEMPO_REDE_S)


class _Linha:
    """Conexão que fica ABERTA com o banco: cada envio aproveita a mesma, em
    vez de abrir uma nova (o aperto de mão de segurança custava meio segundo
    ou mais a cada posição, na rede do celular). Caiu? Abre outra e repete."""

    def __init__(self, base):
        u = urllib.parse.urlsplit(base)
        self._https, self._host = u.scheme == "https", u.netloc
        self._con = None

    def _abrir(self):
        if self._https:
            return http.client.HTTPSConnection(self._host, timeout=TEMPO_REDE_S, context=rede._CTX)
        return http.client.HTTPConnection(self._host, timeout=TEMPO_REDE_S)

    def enviar(self, caminho, corpo, metodo):
        dados = json.dumps(corpo).encode("utf-8")
        cabecalhos = {"User-Agent": rede.USER_AGENT, "Content-Type": "application/json"}
        for tentativa in (1, 2):
            try:
                if self._con is None:
                    self._con = self._abrir()
                self._con.request(metodo, caminho, body=dados, headers=cabecalhos)
                resposta = self._con.getresponse()
                texto = resposta.read()
                if resposta.status >= 400:
                    raise OSError("o banco respondeu %d: %s" % (resposta.status, texto[:120]))
                return
            except Exception:
                self.fechar()
                if tentativa == 2:
                    raise   # a conexão parada pode ter sido fechada pelo servidor: tentou de novo com uma nova

    def fechar(self):
        try:
            if self._con is not None:
                self._con.close()
        except Exception:
            pass
        self._con = None


class AoVivo:
    def __init__(self, base, relogio=time.time):
        self.base = base
        self._relogio = relogio
        self.codigo = secrets.token_urlsafe(16)
        self.senha = secrets.token_urlsafe(16)
        self.ativo = False
        self.enviados = 0            # envios que deram certo (diagnóstico e testes)
        self.ultimo_erro = None
        self._trava = threading.Lock()
        self._acordar = threading.Event()
        self._thread = None
        self._criada = False
        self._destino = ""
        self._rota = None            # (versão, polyline, lat e lon do destino)
        self._rota_enviada = 0
        self._pos = None             # última posição ainda não enviada
        self._t_envio = 0.0
        self._trilha_nova = []       # pontos do caminho ainda não enviados
        self._ultimo_ponto = None
        self._pedacos = 0            # pedaços de caminho já no banco
        self._fim = None             # "chegou" ou "encerrou"
        self._linha = _Linha(base)
        self.fim_avisado = False     # o aviso de fim chegou ao banco (posição apagada)

    @property
    def link(self):
        return link(self.base, self.codigo)

    def _url(self):
        return "%s/corridas/%s.json" % (self.base, self.codigo)

    def _mandar(self, corpo, metodo):
        self._linha.enviar("/corridas/%s.json" % self.codigo, corpo, metodo)

    # --- chamados pelo app (qualquer thread) ---------------------------------------
    def comecar(self, rota, destino_nome):
        self._destino = (destino_nome or "")[:80]
        self.trocar_rota(rota)
        self.ativo = True
        self._thread = threading.Thread(target=self._laco, name="ao-vivo", daemon=True)
        self._thread.start()
        return self.link

    def trocar_rota(self, rota):
        with self._trava:
            versao = (self._rota[0] if self._rota else 0) + 1
            fim = rota.pontos[-1] if rota.pontos else (0.0, 0.0)
            self._rota = (versao, codificar_polyline(rota.pontos, 1e5), fim[0], fim[1])
        self._acordar.set()

    def leitura(self, lat, lon, vel_kmh, rumo, restante_m, restante_s, dist_m=None, fora=False):
        """A cada posição boa do GPS durante a navegação. dist_m: metros já
        andados na rota (a página usa para a seta deslizar pela linha, em vez
        de pular de ponto em ponto); fora: saiu da rota."""
        if not self.ativo:
            return
        agora = self._relogio()
        with self._trava:
            if self._ultimo_ponto is None or distancia_m(self._ultimo_ponto, (lat, lon)) >= TRILHA_PASSO_M:
                self._ultimo_ponto = (lat, lon)
                self._trilha_nova.append((lat, lon))
            self._pos = {"lat": round(lat, 6), "lon": round(lon, 6), "v": int(round(vel_kmh or 0)),
                         "r": None if rumo is None else int(rumo) % 360,
                         "fm": int(restante_m or 0), "fs": int(restante_s or 0), "t": int(agora)}
            if dist_m is not None and not fora:
                self._pos["d"] = int(dist_m)
            espera = ENVIAR_A_CADA_S if (vel_kmh or 0) >= 2 else PARADO_A_CADA_S
            devido = agora - self._t_envio >= espera
        if devido:
            self._acordar.set()

    def terminar(self, chegou=False):
        if not self.ativo:
            return
        self.ativo = False
        self._fim = "chegou" if chegou else "encerrou"
        self._acordar.set()

    def esperar_fim(self, segundos=5.0):
        if self._thread is not None:
            self._thread.join(segundos)

    # --- thread de envio ---------------------------------------------------------------
    def _laco(self):
        de_novo = False
        while True:
            chamado = self._acordar.wait(3.0)   # leitura() acorda quando é hora de enviar
            self._acordar.clear()
            fim = self._fim
            if not (chamado or de_novo or fim is not None):
                continue
            try:
                if fim is not None:
                    self._enviar_fim(fim)
                    return
                self._enviar()
                self.ultimo_erro, de_novo = None, False
            except Exception as e:
                self.ultimo_erro = e
                if fim is not None:
                    print("[ao vivo] nao consegui avisar o fim:", e)
                    return
                de_novo = True  # sem internet agora: tenta de novo daqui a pouco

    def _enviar(self):
        with self._trava:
            pos, self._pos = self._pos, None
            trilha, self._trilha_nova = self._trilha_nova, []
            rota = self._rota if self._rota and self._rota[0] != self._rota_enviada else None
        if pos is None and rota is None and not trilha and self._criada:
            return
        try:
            if not self._criada:
                corpo = {"s": self.senha, "pub": {"v": 1, "destino": self._destino,
                                                  "inicio": int(self._relogio())}}
                self._mandar(corpo, "PUT")
                self._criada = True
            corpo = {"s": self.senha}
            n = self._pedacos
            if trilha:
                # pedaços numerados: a página só baixa os que ainda não tem
                corpo["pub/tr/%05d" % n] = codificar_polyline(trilha, 1e5)
                n += 1
            if rota is not None:
                corpo["pub/rota"] = {"rv": rota[0], "linha": rota[1], "dlat": round(rota[2], 6),
                                     "dlon": round(rota[3], 6)}
            if pos is not None:
                corpo["pub/pos"] = dict(pos, n=n, rv=self._rota[0] if self._rota else 0, e="indo")
            self._mandar(corpo, "PATCH")
        except Exception:
            with self._trava:  # não foi: o caminho volta para a fila (a posição velha não)
                self._trilha_nova = trilha + self._trilha_nova
                if self._pos is None:
                    self._pos = pos
            raise
        self._pedacos = n
        if rota is not None:
            self._rota_enviada = rota[0]
        if pos is not None:
            self._t_envio = self._relogio()
        self.enviados += 1

    def _enviar_fim(self, fim):
        """Troca a corrida inteira pelo aviso de fim: posição e caminho somem."""
        self._mandar({"s": self.senha, "pub": {
            "v": 1, "destino": self._destino, "fim": int(self._relogio()),
            "pos": {"e": fim, "t": int(self._relogio())}}}, "PUT")
        self.enviados += 1
        self.fim_avisado = True
        self._linha.fechar()
