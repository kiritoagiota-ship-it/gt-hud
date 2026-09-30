"""Partes específicas do Android: permissões e tela sempre ligada.

No PC tudo aqui vira "não faz nada", para o app rodar no desktop.
"""
from kivy.clock import mainthread
from kivy.utils import platform

NO_ANDROID = platform == "android"

if NO_ANDROID:
    from android.permissions import Permission, check_permission, request_permissions
    from android.runnable import run_on_ui_thread
    from jnius import autoclass

    _PythonActivity = autoclass("org.kivy.android.PythonActivity")
    _LayoutParams = autoclass("android.view.WindowManager$LayoutParams")

    @run_on_ui_thread
    def _flag_tela(ligar):
        janela = _PythonActivity.mActivity.getWindow()
        if ligar:
            janela.addFlags(_LayoutParams.FLAG_KEEP_SCREEN_ON)
        else:
            janela.clearFlags(_LayoutParams.FLAG_KEEP_SCREEN_ON)
else:
    def _flag_tela(ligar):
        pass


def manter_tela_ligada(ligar):
    _flag_tela(bool(ligar))


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
