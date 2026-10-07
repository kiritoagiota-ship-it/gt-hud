"""Navegação curva a curva (lógica pura, sem tela: dá para testar no PC).

A cada leitura do GPS: acha o ponto da rota mais perto (procurando perto de
onde estava, para não "pular" para outro trecho que passe pela mesma rua),
calcula o quanto já andou, a próxima manobra, e decide o que falar:
  - aviso de longe ("Em trezentos metros, vire à esquerda") uma vez;
  - aviso na hora (~6 s antes, pela velocidade) uma vez;
  - subida chegando ("Senhor, em duzentos metros, subida de 8%");
  - saiu da rota por FORA_DA_ROTA_S -> pede para recalcular;
  - chegou.
"""
import math

import falas
import sinais

FORA_DA_ROTA_M = 35
FORA_DA_ROTA_S = 4.0
CHEGADA_M = 25
AVISO_LONGE_M = (250, 450)   # faixa em que sai o "Em X metros, ..."
AVISO_PERTO_S = 6.0          # o aviso "na hora" sai uns 6 s antes da curva
AVISO_PERTO_MIN_M = 35
AVISO_SUBIDA_M = 220
AVISO_DESCIDA_M = 180
DESCIDA_FALADA_MIN = 5.0     # descida mais leve que isso só aparece na tela
AVISO_SINAL_S = 7.0          # semáforo/lombada: avisa uns 7 s antes (pela velocidade)
AVISO_SINAL_MIN_M = 50
SINAL_COM_MANOBRA_M = 60     # semáforo colado numa curva: a fala da curva já basta
SEMAFORO_FALADO_A_CADA_M = 400   # avenida com semáforo em todo quarteirão: fala 1 a cada 400 m
DEPOIS_M = 120               # manobra logo depois da próxima: mostra "Depois"
SEGUE_LINHA_M = 20           # até isso da rota, a seta anda EM CIMA da linha
_M_POR_GRAU = 111320.0

# prioridade das falas (a mais alta passa na frente da fila)
P_INFO, P_AVISO, P_MANOBRA, P_CHEGADA = 0, 1, 2, 3


def _projecao(p, a, b):
    """(distância em m do ponto p ao segmento ab, fração 0..1 no segmento)."""
    k = math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * k * _M_POR_GRAU, (a[0] - p[0]) * _M_POR_GRAU
    bx, by = (b[1] - p[1]) * k * _M_POR_GRAU, (b[0] - p[0]) * _M_POR_GRAU
    dx, dy = bx - ax, by - ay
    comp2 = dx * dx + dy * dy
    t = 0.0 if comp2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / comp2))
    return math.hypot(ax + t * dx, ay + t * dy), t


class Navegacao:
    def __init__(self, rota, falar, avisar_subidas=True, avisar_semaforos=True):
        self.falar = falar  # falar(pedaços, prioridade[, texto pronto])
        self.avisar_subidas = avisar_subidas
        self.avisar_semaforos = avisar_semaforos
        self.chegou = False
        self._vel_ms = 0.0
        self._iniciar_rota(rota)
        primeira = self._proxima_manobra()
        pedacos = ["rota_calculada"]
        texto = falas.resumo_rota(rota.total_m, rota.tempo_s, rota.subida_total_m)
        if primeira is None or primeira[1]["dist_m"] > AVISO_LONGE_M[1]:
            pedacos.append("em_frente")
            texto += " Siga em frente."
        self.falar(pedacos, P_INFO, texto)

    def _iniciar_rota(self, rota):
        self.rota = rota
        self.seg = 0
        self.dist_feita = 0.0
        self.dist_da_linha = 0.0
        self.recalcular_pedido = False
        self._fora_desde = None
        self._faladas = set()
        self._subidas_avisadas = set()
        self._descidas_avisadas = set()
        self._subida_atual = None
        self.alertas = sinais.ao_longo(rota)   # [(dist_m, "semaforo"/"lombada")]
        self._alertas_ditos = set()
        self._ultimo_semaforo_m = -1e9

    def trocar_rota(self, rota):
        """Rota nova depois de recalcular (começa do ponto atual)."""
        self._iniciar_rota(rota)

    def desistir_de_recalcular(self):
        """O recálculo falhou (sem internet): tenta de novo mais tarde."""
        self.recalcular_pedido = False
        self._fora_desde = None

    # --- onde está na rota ---------------------------------------------------
    def _melhor(self, p, i0, i1):
        pts = self.rota.pontos
        melhor = (float("inf"), 0, 0.0)
        for i in range(i0, i1):
            d, t = _projecao(p, pts[i], pts[i + 1])
            if d < melhor[0]:
                melhor = (d, i, t)
        return melhor

    def _projetar(self, lat, lon):
        ultimo = len(self.rota.pontos) - 1
        d, i, t = self._melhor((lat, lon), max(0, self.seg - 3), min(ultimo, self.seg + 80))
        if d > 60:  # perdeu a referência (ex.: GPS pulou): procura na rota toda
            d, i, t = self._melhor((lat, lon), 0, ultimo)
        return d, i, t

    def _proxima_manobra(self):
        for n, m in enumerate(self.rota.manobras):
            if m["dist_m"] > self.dist_feita + 3:
                return n, m
        return None

    # --- chamado a cada leitura boa do GPS ---------------------------------
    def atualizar(self, lat, lon, vel_kmh, agora):
        rota = self.rota
        if len(rota.pontos) < 2:
            return self._estado(None)
        d, i, t = self._projetar(lat, lon)
        self._vel_ms = max(0.0, vel_kmh or 0.0) / 3.6
        self.seg = i
        self.dist_feita = rota.acumulado[i] + t * (rota.acumulado[i + 1] - rota.acumulado[i])
        self.dist_da_linha = d
        restante = rota.total_m - self.dist_feita

        if not self.chegou and restante < CHEGADA_M and d < FORA_DA_ROTA_M * 2:
            self.chegou = True
            self.falar(["senhor", "chegou"], P_CHEGADA)
            return self._estado(None)

        if d > FORA_DA_ROTA_M:
            if self._fora_desde is None:
                self._fora_desde = agora
            elif agora - self._fora_desde >= FORA_DA_ROTA_S:
                self.recalcular_pedido = True
            return self._estado(self._proxima_manobra())
        self._fora_desde = None

        proxima = self._proxima_manobra()
        if proxima is not None:
            self._avisar_manobra(proxima, vel_kmh)
        if self.avisar_subidas:
            self._avisar_subidas()
        self._avisar_alertas(vel_kmh, proxima)
        return self._estado(proxima)

    def _avisar_alertas(self, vel_kmh, proxima):
        """Lombada sempre (segurança); semáforo se ligado nos Ajustes e se não
        estiver colado numa curva (aí a fala da curva já chama a atenção)."""
        janela = max(AVISO_SINAL_MIN_M, vel_kmh / 3.6 * AVISO_SINAL_S)
        for k, (dist, tipo) in enumerate(self.alertas):
            falta = dist - self.dist_feita
            if falta < 0 or k in self._alertas_ditos:
                continue
            if falta > janela:
                break
            self._alertas_ditos.add(k)
            if sinais.e_radar(tipo):
                # radar sempre (multa): com o limite, se o mapa informa; e manda
                # reduzir se a pessoa está acima dele
                limite = sinais.limite_do_radar(tipo)
                texto = "Radar de %d à frente." % limite if limite else "Radar à frente."
                if limite and vel_kmh > limite:
                    texto = "Radar de %d à frente, reduza." % limite
                self.falar(["radar"], P_AVISO, texto)
            elif tipo == "lombada":
                self.falar(["lombada"], P_AVISO)
            elif (self.avisar_semaforos
                  and dist - self._ultimo_semaforo_m >= SEMAFORO_FALADO_A_CADA_M
                  and not (proxima is not None
                           and abs(proxima[1]["dist_m"] - dist) < SINAL_COM_MANOBRA_M)):
                self._ultimo_semaforo_m = dist
                self.falar(["semaforo"], P_INFO)

    def _avisar_manobra(self, proxima, vel_kmh):
        n, m = proxima
        falta = m["dist_m"] - self.dist_feita
        chave = falas.chave_manobra(m["acao"], m.get("saida"))
        perto = max(AVISO_PERTO_MIN_M, vel_kmh / 3.6 * AVISO_PERTO_S)
        chegada = m["acao"].startswith("chegada")
        if falta <= perto and (n, "perto") not in self._faladas:
            self._faladas.update({(n, "perto"), (n, "longe")})
            if chegada:
                return  # a própria chegada já é anunciada
            pedacos = [chave] if falta < 40 else ["em_%d" % falas.distancia_falada(falta), chave]
            self.falar(pedacos + self._logo_depois(n), P_MANOBRA)
        elif (AVISO_LONGE_M[0] < falta <= AVISO_LONGE_M[1]
              and (n, "longe") not in self._faladas):
            self._faladas.add((n, "longe"))
            self.falar(["em_%d" % falas.distancia_falada(falta), chave] + self._logo_depois(n),
                       P_AVISO)

    def _logo_depois(self, n):
        """Curva colada na próxima (como o Waze): "... E logo depois, vire à
        esquerda." Ela ainda ganha o próprio aviso na hora."""
        manobras = self.rota.manobras
        if n + 1 >= len(manobras):
            return []
        seguinte = manobras[n + 1]
        if seguinte["dist_m"] - manobras[n]["dist_m"] >= DEPOIS_M:
            return []
        self._faladas.add((n + 1, "longe"))
        return ["logo_depois", falas.chave_manobra(seguinte["acao"], seguinte.get("saida"))]

    def _avisar_subidas(self):
        atual = None
        for k, s in enumerate(self.rota.subidas):
            falta = s["inicio_m"] - self.dist_feita
            if k not in self._subidas_avisadas and -20 < falta <= AVISO_SUBIDA_M:
                self._subidas_avisadas.add(k)
                pedacos = ["senhor"]
                if falta > 40:
                    pedacos.append("em_%d" % falas.distancia_falada(falta))
                pedacos.append(falas.chave_subida(s["grau"]))
                self.falar(pedacos, P_AVISO)
            if s["inicio_m"] <= self.dist_feita < s["fim_m"]:
                atual = k
        for k, s in enumerate(self.rota.descidas):
            falta = s["inicio_m"] - self.dist_feita
            if (k not in self._descidas_avisadas and -20 < falta <= AVISO_DESCIDA_M
                    and s["grau"] >= DESCIDA_FALADA_MIN):
                self._descidas_avisadas.add(k)
                pedacos = ["senhor"]
                if falta > 40:
                    pedacos.append("em_%d" % falas.distancia_falada(falta))
                pedacos.append(falas.chave_descida(s["grau"]))
                self.falar(pedacos, P_AVISO)
        if self._subida_atual is not None and atual is None:
            s = self.rota.subidas[self._subida_atual]
            # "Fim da subida" só depois de subida que cansa (forte ou longa)
            if self.dist_feita >= s["fim_m"] and (s["grau"] >= 5 or s["fim_m"] - s["inicio_m"] >= 200):
                self.falar(["fim_subida"], P_INFO)
        self._subida_atual = atual

    def prever(self, segundos):
        """Onde a seta deve estar `segundos` depois da última leitura do GPS,
        andando pela rota na velocidade atual: (lat, lon, rumo), ou None se
        está fora da linha. O GPS dá 1 posição por segundo; com isso a seta
        desliza entre uma e outra (e faz as curvas da rota) como no Waze."""
        if self.chegou or self.dist_da_linha > SEGUE_LINHA_M or len(self.rota.pontos) < 2:
            return None
        return self.rota.ponto_em(self.dist_feita + self._vel_ms * segundos, self.seg)

    # --- o que a tela mostra ---------------------------------------------------
    def _estado(self, proxima):
        rota = self.rota
        restante = max(0.0, rota.total_m - self.dist_feita)
        estado = {
            "manobra": None, "dist_manobra": None, "depois": None,
            "restante_m": restante,
            "restante_s": rota.tempo_s * restante / rota.total_m if rota.total_m else 0,
            "subida_restante_m": rota.subida_restante_m(self.dist_feita),
            "subida": None,
            "alerta": None,
            "fora_da_rota": self.dist_da_linha > FORA_DA_ROTA_M,
            "chegou": self.chegou,
        }
        if proxima is not None:
            n, m = proxima
            estado["manobra"] = m
            estado["dist_manobra"] = max(0.0, m["dist_m"] - self.dist_feita)
            if n + 1 < len(rota.manobras):
                seguinte = rota.manobras[n + 1]
                if seguinte["dist_m"] - m["dist_m"] < DEPOIS_M:
                    estado["depois"] = seguinte
        # chip de subida/descida: a que está acontecendo, senão a mais perto à frente
        trechos = [("subida", s) for s in rota.subidas] + [("descida", s) for s in rota.descidas]
        melhor = None
        for tipo, s in trechos:
            if s["inicio_m"] <= self.dist_feita < s["fim_m"]:
                melhor = (-1, {"tipo": tipo, "grau": s["grau"], "falta_m": s["fim_m"] - self.dist_feita,
                               "em_m": 0})
                break
            em = s["inicio_m"] - self.dist_feita
            if 0 < em <= 400 and (melhor is None or em < melhor[0]):
                melhor = (em, {"tipo": tipo, "grau": s["grau"], "falta_m": s["fim_m"] - s["inicio_m"],
                               "em_m": em})
        if melhor is not None:
            estado["subida"] = melhor[1]
        for dist, tipo in self.alertas:
            em = dist - self.dist_feita
            if 0 <= em <= (350 if sinais.e_radar(tipo) else 200):   # radar aparece de mais longe
                estado["alerta"] = {"tipo": tipo, "em_m": em}
                break
        return estado
