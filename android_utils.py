"""Partes específicas do Android: permissões, tela ligada, orientação e
vibração.

No PC tudo aqui vira "não faz nada" (a orientação só gira a janela, para
testar o layout deitado), para o app rodar no desktop.
"""
from kivy.clock import mainthread
from kivy.utils import platform

NO_ANDROID = platform == "android"

# ActivityInfo.SCREEN_ORIENTATION_*: deitada usa o sensor para aceitar o
# celular virado para qualquer um dos dois lados no suporte
_EM_PE, _DEITADA = 1, 6

if NO_ANDROID:
    from android.permissions import Permission, check_permission, request_permissions
    from android.runnable import run_on_ui_thread
    from jnius import autoclass, cast

    _PythonActivity = autoclass("org.kivy.android.PythonActivity")
    _LayoutParams = autoclass("android.view.WindowManager$LayoutParams")

    @run_on_ui_thread
    def _flag_tela(ligar):
        janela = _PythonActivity.mActivity.getWindow()
        if ligar:
            janela.addFlags(_LayoutParams.FLAG_KEEP_SCREEN_ON)
        else:
            janela.clearFlags(_LayoutParams.FLAG_KEEP_SCREEN_ON)

    @run_on_ui_thread
    def _orientacao(deitada):
        _PythonActivity.mActivity.setRequestedOrientation(_DEITADA if deitada else _EM_PE)

    @run_on_ui_thread
    def _barras(cor, claro):
        """Barra de status e de navegação do Android na cor do tema (com o
        tema claro ficavam pretas em cima de uma tela branca)."""
        try:
            sdk = autoclass("android.os.Build$VERSION").SDK_INT
            janela = _PythonActivity.mActivity.getWindow()
            argb = (255 << 24) | (int(cor[0] * 255) << 16) | (int(cor[1] * 255) << 8) | int(cor[2] * 255)
            if argb >= 1 << 31:
                argb -= 1 << 32   # o Java quer um inteiro com sinal
            janela.setStatusBarColor(argb)
            janela.setNavigationBarColor(argb)
            if sdk >= 23:
                vista = janela.getDecorView()
                marcas = vista.getSystemUiVisibility()
                icones_escuros = 0x2000 | (0x10 if sdk >= 26 else 0)   # status + navegação
                vista.setSystemUiVisibility(marcas | icones_escuros if claro else marcas & ~icones_escuros)
        except Exception as e:
            print("[tema] barras do sistema:", e)
else:
    def _barras(cor, claro):
        pass

    def _flag_tela(ligar):
        pass

    def _orientacao(deitada):
        from kivy.core.window import Window
        w, h = Window.size
        if (w > h) != deitada:
            Window.size = (h, w)


def manter_tela_ligada(ligar):
    _flag_tela(bool(ligar))


def definir_orientacao(deitada):
    _orientacao(bool(deitada))


def cores_do_sistema(cor_fundo, claro):
    _barras(tuple(cor_fundo), bool(claro))


_vibrador = None  # (vibrador, VibrationEffect ou None, versão do Android); False = sem


def _obter_vibrador():
    global _vibrador
    if _vibrador is None:
        _vibrador = False
        if not NO_ANDROID:
            return None
        try:
            Context = autoclass("android.content.Context")
            sdk = autoclass("android.os.Build$VERSION").SDK_INT
            vib = cast("android.os.Vibrator",
                       _PythonActivity.mActivity.getSystemService(Context.VIBRATOR_SERVICE))
            if vib is not None and vib.hasVibrator():
                efeito = autoclass("android.os.VibrationEffect") if sdk >= 26 else None
                _vibrador = (vib, efeito, sdk)
        except Exception as e:
            print("[vibrar] sem vibrador:", e)
    return _vibrador or None


def vibrar(tempos, forcas):
    """Sequência de pulsos: tempos = [espera, liga, espera, liga, ...] em ms,
    forcas = intensidade de cada trecho (0..255). Nunca derruba o app."""
    v = _obter_vibrador()
    if v is None:
        return
    vib, efeito, sdk = v
    try:
        if sdk >= 26:
            vib.vibrate(efeito.createWaveform([int(t) for t in tempos],
                                              [int(f) for f in forcas], -1))
        else:
            vib.vibrate([int(t) for t in tempos], -1)
    except Exception as e:
        print("[vibrar]", e)


def pedir_permissoes(callback):
    """Chama callback(True/False) na thread do Kivy.

    True só se a localização PRECISA foi liberada (a aproximada não serve
    para velocímetro).
    """
    cb = mainthread(callback)
    if not NO_ANDROID:
        cb(True)
        return
    fina = Permission.ACCESS_FINE_LOCATION
    if check_permission(fina):
        cb(True)
        return

    def _resposta(permissoes, resultados):
        cb(bool(resultados) and bool(resultados[0]))

    request_permissions([fina, Permission.ACCESS_COARSE_LOCATION], _resposta)
