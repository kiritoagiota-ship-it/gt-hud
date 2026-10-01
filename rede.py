"""Acesso à internet (mapa, rota, busca), sempre fora da thread da tela.

- Certificados do pacote certifi: o repositório do sistema (visto no Windows)
  falhou na cadeia nova da Let's Encrypt que os servidores do OpenStreetMap
  usam ("certificate has expired"); com o certifi funciona.
- User-Agent identificando o app: exigência das regras de uso do
  OpenStreetMap (mapa), Nominatim (busca) e Valhalla (rota).
"""
import json
import ssl
import threading
import urllib.request

from kivy.clock import Clock

USER_AGENT = "GT-HUD/1.0 (app pessoal de bike; github.com/kiritoagiota-ship-it/gt-hud)"


def _contexto():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_CTX = _contexto()


def baixar(url, timeout=20):
    """GET que espera a resposta (use numa thread). Levanta exceção se falhar."""
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, context=_CTX, timeout=timeout) as resposta:
        return resposta.read()


def url_final(url, timeout=15):
    """Para onde um link curto (ex.: maps.app.goo.gl) leva, seguindo os
    redirecionamentos. Use numa thread."""
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, context=_CTX, timeout=timeout) as resposta:
        return resposta.geturl()


def baixar_json(url, timeout=20):
    return json.loads(baixar(url, timeout).decode("utf-8"))


def enviar_json(url, corpo, cabecalhos=None, timeout=20):
    """POST com corpo JSON; devolve a resposta (JSON). Use numa thread."""
    pedido = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                    headers={"User-Agent": USER_AGENT,
                                             "Content-Type": "application/json",
                                             **(cabecalhos or {})})
    with urllib.request.urlopen(pedido, context=_CTX, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def em_segundo_plano(tarefa, ao_terminar, ao_falhar=None):
    """Roda tarefa() numa thread; ao_terminar(resultado) ou ao_falhar(erro)
    são chamados depois na thread do Kivy (onde pode mexer na tela)."""
    def rodar():
        try:
            resultado = tarefa()
        except Exception as erro:
            print("[rede]", erro)
            if ao_falhar is not None:
                Clock.schedule_once(lambda dt, e=erro: ao_falhar(e))
            return
        Clock.schedule_once(lambda dt: ao_terminar(resultado))
    threading.Thread(target=rodar, daemon=True).start()
