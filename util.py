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
