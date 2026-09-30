"""Hook do python-for-android: remove kivy/tests antes de montar o APK.

Se o hooks.py do TraveteFocus for diferente, pode usar o dele no lugar.
"""
import os
import shutil


def before_apk_build(toolchain):
    raiz = getattr(getattr(toolchain, "_dist", None), "dist_dir", None)
    if not raiz or not os.path.isdir(raiz):
        return
    for pasta, subpastas, _ in os.walk(raiz):
        if "tests" in subpastas and os.path.basename(pasta) == "kivy":
            alvo = os.path.join(pasta, "tests")
            print("[hooks] removendo", alvo)
            shutil.rmtree(alvo, ignore_errors=True)
