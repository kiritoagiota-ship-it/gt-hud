"""Diagnóstico: registro do que o app faz e dos erros, para o dono mandar
quando algo der errado no celular (sem cabo nem programa de computador).

- Tudo o que o app escreve com print() (ex.: "[voz] ...", "[rota] ...") e
  qualquer erro não tratado vão para diagnostico.txt (na pasta do app),
  com hora. O arquivo é cortado para não crescer sem fim.
- Se o app fechou com ERRO da última vez, fechou_com_erro() avisa (a tela
  do mapa mostra a mensagem).
- texto_para_enviar(): cabeçalho (versão, celular, Android) + o fim do
  registro; os Ajustes mandam pelo "Compartilhar" do Android (WhatsApp...).
"""
import io
import os
import sys
import threading
import time
import traceback

MAX_BYTES = 400_000          # passou disso ao abrir o app: fica só a metade final
ENVIAR_CARACTERES = 60_000   # cabe numa mensagem de WhatsApp
INICIO = "===== app aberto "

_caminho = None
_trava = threading.Lock()
_fechou_com_erro = False


def _escrever(texto):
    if _caminho is None:
        return
    with _trava:
        try:
            with open(_caminho, "a", encoding="utf-8") as f:
                f.write(texto)
        except OSError:
            pass


class _Copia(io.TextIOBase):
    """stdout/stderr: continua saindo onde saía (logcat, terminal) e vai
    também para o arquivo, linha a linha, com a hora."""

    def __init__(self, original):
        self.original = original
        self._pedaco = ""

    def write(self, texto):
        try:
            if self.original is not None:
                self.original.write(texto)
        except Exception:
            pass
        self._pedaco += texto
        if "\n" in self._pedaco:
            linhas, self._pedaco = self._pedaco.rsplit("\n", 1)
            hora = time.strftime("%H:%M:%S")
            _escrever("".join("%s %s\n" % (hora, l) for l in linhas.split("\n")))
        return len(texto)

    def flush(self):
        try:
            if self.original is not None:
                self.original.flush()
        except Exception:
            pass


def registrar_erro(tipo, valor, tb, onde="erro"):
    _escrever("%s !!! %s:\n%s" % (time.strftime("%H:%M:%S"), onde,
                                  "".join(traceback.format_exception(tipo, valor, tb))))


def iniciar(pasta, versao=""):
    """Chamar o quanto antes (no build do app)."""
    global _caminho, _fechou_com_erro
    os.makedirs(pasta, exist_ok=True)
    _caminho = os.path.join(pasta, "diagnostico.txt")
    try:
        if os.path.getsize(_caminho) > MAX_BYTES:
            with open(_caminho, encoding="utf-8", errors="replace") as f:
                resto = f.read()[-MAX_BYTES // 2:]
            with open(_caminho, "w", encoding="utf-8") as f:
                f.write(resto)
    except OSError:
        pass
    _fechou_com_erro = "!!! " in _ultima_sessao()
    _escrever("\n%s%s  versão %s =====\n" % (INICIO, time.strftime("%d/%m/%Y %H:%M:%S"), versao))
    _escrever(info_aparelho() + "\n")
    sys.stdout = _Copia(sys.stdout)
    sys.stderr = _Copia(sys.stderr)
    original_hook = sys.excepthook

    def gancho(tipo, valor, tb):
        registrar_erro(tipo, valor, tb, "erro que fechou o app")
        original_hook(tipo, valor, tb)
    sys.excepthook = gancho

    def gancho_thread(args):
        registrar_erro(args.exc_type, args.exc_value, args.exc_traceback,
                       "erro numa thread (%s)" % getattr(args.thread, "name", "?"))
    threading.excepthook = gancho_thread


def _ultima_sessao():
    try:
        with open(_caminho, encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except OSError:
        return ""
    i = texto.rfind(INICIO)
    return texto[i:] if i >= 0 else texto


def fechou_com_erro():
    return _fechou_com_erro


def info_aparelho():
    try:
        from jnius import autoclass
        build = autoclass("android.os.Build")
        versao = autoclass("android.os.Build$VERSION")
        return "Celular: %s %s, Android %s (API %d)" % (build.MANUFACTURER, build.MODEL,
                                                       versao.RELEASE, versao.SDK_INT)
    except Exception:
        return "Computador (%s)" % sys.platform


def texto_para_enviar():
    try:
        with open(_caminho, encoding="utf-8", errors="replace") as f:
            registro = f.read()[-ENVIAR_CARACTERES:]
    except (OSError, TypeError):
        registro = "(sem registro)"
    return "Diagnóstico do GT-HUD\n%s\n\n%s" % (info_aparelho(), registro)


def compartilhar(texto):
    """Abre o "Compartilhar" do Android com o texto. No PC: copia para a área
    de transferência. Devolve True se deu."""
    try:
        from jnius import autoclass, cast
        Intent = autoclass("android.content.Intent")
        String = autoclass("java.lang.String")
        intent = Intent(Intent.ACTION_SEND)
        intent.setType("text/plain")
        intent.putExtra(Intent.EXTRA_SUBJECT, cast("java.lang.CharSequence", String("Diagnóstico GT-HUD")))
        intent.putExtra(Intent.EXTRA_TEXT, cast("java.lang.CharSequence", String(texto)))
        escolha = Intent.createChooser(intent, cast("java.lang.CharSequence", String("Enviar diagnóstico")))
        atividade = autoclass("org.kivy.android.PythonActivity").mActivity
        from android.runnable import run_on_ui_thread
        run_on_ui_thread(lambda: atividade.startActivity(escolha))()
        return True
    except ImportError:
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(texto)
            return True
        except Exception:
            return False
    except Exception as e:
        print("[diagnostico] compartilhar falhou:", e)
        return False
