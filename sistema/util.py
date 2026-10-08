"""Formatação de números para as telas."""
import time


def fmt_tempo(segundos):
    s = int(segundos or 0)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


def fmt_dist(metros):
    metros = metros or 0
    if metros < 1000:
        return "%d m" % metros
    return "%.2f km" % (metros / 1000.0)


def fmt_vel(kmh):
    return "%.0f" % (kmh or 0)


def fmt_data(ts):
    return time.strftime("%d/%m/%Y  %H:%M", time.localtime(ts))


def fmt_dist_nav(metros):
    """Distância da navegação: "250 m" (de 10 em 10) ou "1,2 km"."""
    metros = max(0.0, metros or 0.0)
    if metros < 950:
        return "%d m" % (int(round(metros / 10.0)) * 10)
    return ("%.1f km" % (metros / 1000.0)).replace(".", ",")


def fmt_duracao(segundos):
    """Tempo que falta: "14 min" ou "1 h 05"."""
    minutos = int(round((segundos or 0) / 60.0))
    if minutos < 60:
        return "%d min" % max(1, minutos)
    return "%d h %02d" % divmod(minutos, 60)


def fmt_hora_chegada(segundos_restantes):
    return time.strftime("%H:%M", time.localtime(time.time() + (segundos_restantes or 0)))
