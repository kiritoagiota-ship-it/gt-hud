"""As camadas que ficam POR CIMA das ruas no mapa (separadas de widgets/mapa.py
em 07/10/2026, na organização do código pedida pelo dono; o texto dos
métodos é o mesmo de antes):

- ruas coloridas pela velocidade de agora (fluxo.py, TomTom);
- ocorrências de trânsito da cidade: trecho pintado + ícone tocável (transito.py);
- semáforos, lombadas, radares e os pinos de Casa/Trabalho (sinais.py);
- qual lugar (emblema ou nome) está num ponto da tela.

CamadasDoMapa é a "metade" de MapaHUD que cuida disso: usa o que MapaHUD
guarda (self._local, self._para_tela, self.zoom, os grupos de desenho...).
"""
import math
import time

from kivy.core.text import Label as CoreLabel
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Mesh, PopMatrix, PushMatrix, Rectangle,
                           RoundedRectangle, Scale, Translate)
from kivy.metrics import dp, sp

import rede
import sinais
import tema
from mapa_vetor import _Malha

# (16 enchia a tela de semáforos no centro da cidade, andando livre)
# faixa de trânsito por baixo da rota, pela gravidade (1 leve ... 3 parado, 4 via interditada)
CORES_TRANSITO = {1: (1.0, 0.84, 0.16, 0.92), 2: (1.0, 0.52, 0.10, 0.92), 3: (0.92, 0.13, 0.13, 0.95),
                  4: (0.52, 0.05, 0.22, 1.0)}
# ruas coloridas pela velocidade de agora (fluxo.py): 0 livre ... 3 parado, 4 via fechada
CORES_FLUXO = {0: (0.18, 0.80, 0.44, 0.62), 1: (1.0, 0.84, 0.16, 0.90), 2: (1.0, 0.52, 0.10, 0.92),
               3: (0.92, 0.13, 0.13, 0.95), 4: (0.52, 0.05, 0.22, 1.0)}
LARGURA_FLUXO_DP = {0: 2.2, 1: 3.4, 2: 3.8, 3: 4.2, 4: 4.2}   # o livre é só um fio; o parado chama a atenção
ZOOM_FLUXO = 12.5          # de mais longe as cores virariam um borrão
ZOOM_OCORRENCIAS = 12.0    # acidente, obra, via interditada (trânsito ao vivo): desde bem longe
ZOOM_LENTOS = 13.5         # o ícone de trânsito lento, um pouco mais de perto (o trecho pintado, sempre)
TOQUE_OCORRENCIA_DP = 30   # tocou até isso do ícone: abre o que é
SALTO_S = 0.32             # o "pulo" do ícone tocado
ZOOM_RADARES = 14.5        # radares aparecem bem antes
ZOOM_SINAIS = 17.0         # fora da navegação, semáforos e lombadas a partir desse zoom
MAX_SINAIS = 40
# o Kivy faz cada curva e cada ponta da linha com 10 triângulos; 4 já ficam
# redondos nessas larguras e a linha da rota (centenas de pontos) pesa bem menos
LINHA_LEVE = {"joint_precision": 4, "cap_precision": 5}


class CamadasDoMapa:
    def definir_fluxo(self, segmentos):
        """As ruas pela velocidade de agora: [(pontos (lat, lon), nível 0..4)]
        (fluxo.py). Verde fino = livre; amarelo, laranja e vermelho = cada
        vez mais lento; vinho = via fechada."""
        self._fluxo = list(segmentos)
        self._fluxo_rz = None
        self._desenhar_fluxo()

    def _desenhar_fluxo(self):
        """Uma malha por cor (centenas de trechos viram 5 desenhos), com as pontas e as
        curvas ARREDONDADAS (retas, cada trecho terminava num retângulo: o dono estranhou
        no print de 08/10/2026). A largura é feita para o zoom de agora (de meio em meio
        nível) e refeita quando ele muda: antes era fixa no nível de desenho e, bem de
        perto, as faixas ficavam com o dobro ou o triplo da largura."""
        rz = round(max(11.0, min(19.0, self.zoom)) * 2.0) / 2.0
        visivel = self.zoom >= ZOOM_FLUXO and bool(self._fluxo)
        if self._fluxo_rz == (rz, visivel):
            return
        self._fluxo_rz = pedido = (rz, visivel)
        if not visivel:
            self._g_fluxo.clear()
            return
        px_por_local = self._escala * 2.0 ** (rz - 14)
        segmentos, local = self._fluxo, self._local
        larguras = {n: dp(LARGURA_FLUXO_DP[n]) / 2.0 / px_por_local for n in CORES_FLUXO}

        def montar():
            # (numa thread: uma avenida inteira são milhares de pontos; na tela daria um engasgo)
            malhas = {n: _Malha() for n in CORES_FLUXO}
            for pontos, nivel in segmentos:
                malhas[nivel].faixa([local(lat, lon) for lat, lon in pontos], larguras[nivel], 6)
            return [(nivel, malhas[nivel].listas()) for nivel in sorted(malhas)]

        def desenhar(prontas):
            if self._fluxo_rz != pedido or self._fluxo is not segmentos:
                return   # o zoom ou os dados mudaram enquanto montava: vale o pedido mais novo
            self._g_fluxo.clear()
            for nivel, listas in prontas:   # o mais lento por último: fica por cima
                if listas:
                    self._g_fluxo.add(Color(*CORES_FLUXO[nivel]))
                    for vertices, indices in listas:
                        self._g_fluxo.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))
        rede.em_segundo_plano(montar, desenhar, lambda e: None)

    def caixa_da_vista(self):
        """(lat mín, lon mín, lat máx, lon máx) do que está na tela (None sem tamanho)."""
        if self.width < 2 or self.height < 2:
            return None
        cantos = [self._local_para_geo(*self._tela_para_local(px, py))
                  for px, py in ((self.x, self.y), (self.right, self.y), (self.x, self.top), (self.right, self.top))]
        return (min(c[0] for c in cantos), min(c[1] for c in cantos),
                max(c[0] for c in cantos), max(c[1] for c in cantos))

    def lugar_em(self, sx, sy):
        """O lugar (comércio, praça...) desenhado no ponto (sx, sy) da tela, ou None."""
        achado = None
        for rot in self._rotulos:
            r = rot.info
            if r.get("tipo") != "poi":
                continue
            x, y = self._local_para_tela(r["x"], r["y"])
            x0, y0, x1, y1 = rot.caixa_nome
            d = math.hypot(sx - x, sy - y)
            no_nome = x + x0 - dp(4) <= sx <= x + x1 + dp(4) and y + y0 - dp(8) <= sy <= y + y1 + dp(8)
            if d <= dp(22) or no_nome:
                if achado is None or d < achado[0]:
                    achado = (d, rot)
        if achado is None:
            return None
        rot = achado[1]
        partes = rot.info["texto"].split(" · ")
        lat, lon = self._local_para_geo(rot.info["x"], rot.info["y"])
        return {"nome": partes[0], "legenda": partes[1] if len(partes) > 1 else "",
                "icone": rot.icone, "lat": lat, "lon": lon, "_rot": rot}

    def definir_ocorrencias(self, ocorrencias):
        """O trânsito de Goiânia agora, mesmo sem rota (pedido do dono, 07/10/2026:
        \"não vi nada de diferente no mapa\"): trecho lento pintado por magnitude
        e um ícone por ocorrência (tocar nele abre o que é)."""
        self.ocorrencias = list(ocorrencias or [])
        self._g_transito.clear()
        self._larg_geral = []
        self._ocorr_icones = []
        for o in self.ocorrencias:
            pontos = o["pontos"]
            magnitude = 4 if o["categoria"] == 8 else max(1, min(4, o["magnitude"] or 1))
            if len(pontos) >= 2:
                plano = []
                for lat, lon in pontos:
                    plano.extend(self._local(lat, lon))
                self._g_transito.add(Color(*CORES_TRANSITO[magnitude]))
                linha = Line(points=plano, width=1, joint="round", cap="round", **LINHA_LEVE)
                self._g_transito.add(linha)
                self._larg_geral.append(linha)
            lat, lon = pontos[len(pontos) // 2]
            self._ocorr_icones.append((lat, lon, "transito:%d:%d" % (o["categoria"], magnitude), o))
        # o que mais importa primeiro (se houver ícones demais na tela, os lentos é que ficam de fora)
        self._ocorr_icones.sort(key=lambda i: (i[3]["categoria"] == 6, -(i[3]["magnitude"] or 0)))
        self._larg_usada = None
        self._ajustar_larguras(self._escala_tela())
        self._escolher_sinais()

    # --- semáforos e lombadas -------------------------------------------------------
    @staticmethod
    def _icone(tipo):
        """(grupo, Translate, Scale) do ícone: o Scale faz a placa crescer quando a
        pessoa chega perto dela na navegação (destacar_alerta)."""
        g, tr, sc = InstructionGroup(), Translate(0, 0), Scale(1, 1, 1)
        g.add(PushMatrix())
        g.add(tr)
        g.add(sc)
        if tipo in ("casa", "trabalho"):
            # pino do atalho (como o da casa no Waze): gota na cor do app com o desenho dentro
            cor, fundo = tema.CIANO, tema.FUNDO
            g.add(Color(*tema.com_alfa(fundo, 0.9)))
            g.add(Ellipse(pos=(-dp(17), -dp(3)), size=(dp(34), dp(34))))
            g.add(Color(*cor))
            g.add(Ellipse(pos=(-dp(14.5), -dp(0.5)), size=(dp(29), dp(29))))
            g.add(Mesh(vertices=[-dp(7), dp(3), 0, 0, dp(7), dp(3), 0, 0, 0, -dp(9), 0, 0],
                       indices=[0, 1, 2], mode="triangles"))                 # a ponta da gota
            g.add(Color(*fundo))
            if tipo == "casa":
                g.add(Mesh(vertices=[-dp(8), dp(14), 0, 0, dp(8), dp(14), 0, 0, 0, dp(22), 0, 0],
                           indices=[0, 1, 2], mode="triangles"))             # telhado
                g.add(Rectangle(pos=(-dp(5.5), dp(6)), size=(dp(11), dp(8.5))))
            else:
                g.add(Rectangle(pos=(-dp(8), dp(7)), size=(dp(16), dp(11))))  # maleta
                g.add(Line(points=[-dp(3.5), dp(18), -dp(3.5), dp(21.5), dp(3.5), dp(21.5), dp(3.5), dp(18)],
                           width=dp(1.3)))
        elif tipo.startswith("transito:"):
            _, categoria, magnitude = tipo.split(":")
            categoria, magnitude = int(categoria), int(magnitude)
            borda = (0.04, 0.05, 0.08, 0.95)
            if categoria == 8:      # via interditada: placa de "proibido" (disco vermelho, barra branca)
                g.add(Color(*borda))
                g.add(Ellipse(pos=(-dp(14), -dp(14)), size=(dp(28), dp(28))))
                g.add(Color(0.86, 0.10, 0.14, 1))
                g.add(Ellipse(pos=(-dp(12), -dp(12)), size=(dp(24), dp(24))))
                g.add(Color(1, 1, 1, 1))
                g.add(Rectangle(pos=(-dp(8), -dp(2.5)), size=(dp(16), dp(5))))
            elif categoria == 6:    # trânsito lento: disco na cor do trecho com três "carros" em fila
                g.add(Color(*borda))
                g.add(Ellipse(pos=(-dp(12), -dp(12)), size=(dp(24), dp(24))))
                g.add(Color(*CORES_TRANSITO[magnitude][:3], 1))
                g.add(Ellipse(pos=(-dp(10), -dp(10)), size=(dp(20), dp(20))))
                g.add(Color(*borda))
                for k in (-1, 0, 1):
                    g.add(Rectangle(pos=(-dp(2) + k * dp(5.5), -dp(4)), size=(dp(4), dp(8))))
            else:                   # acidente (vermelho), obras e o resto (laranja): triângulo com "!"
                cor = (0.90, 0.12, 0.14, 1) if categoria == 1 else tuple(tema.LARANJA)
                fora = [(0, dp(16)), (dp(16), -dp(11)), (-dp(16), -dp(11))]
                dentro = [(0, dp(12)), (dp(12.5), -dp(9)), (-dp(12.5), -dp(9))]
                for pts, c in ((fora, borda), (dentro, cor)):
                    g.add(Color(*c))
                    g.add(Mesh(vertices=[v for x, y in pts for v in (x, y, 0, 0)], indices=[0, 1, 2],
                               mode="triangles"))
                g.add(Color(1, 1, 1, 1))
                g.add(Rectangle(pos=(-dp(1.5), -dp(2)), size=(dp(3), dp(9))))
                g.add(Rectangle(pos=(-dp(1.5), -dp(6.5)), size=(dp(3), dp(3))))
        elif sinais.e_radar(tipo):
            # placa de limite: disco branco, aro vermelho e o número (ou "R" sem limite informado)
            g.add(Color(0, 0, 0, 0.30))                                   # sombra
            g.add(Ellipse(pos=(-dp(15.5), -dp(17.5)), size=(dp(31), dp(31))))
            g.add(Color(0.05, 0.06, 0.09, 1))                             # contorno escuro
            g.add(Ellipse(pos=(-dp(16), -dp(16)), size=(dp(32), dp(32))))
            g.add(Color(0.88, 0.10, 0.16, 1))
            g.add(Ellipse(pos=(-dp(14.5), -dp(14.5)), size=(dp(29), dp(29))))
            g.add(Color(1, 1, 1, 1))
            g.add(Ellipse(pos=(-dp(10.5), -dp(10.5)), size=(dp(21), dp(21))))
            limite = sinais.limite_do_radar(tipo)
            rotulo = CoreLabel(text=str(limite) if limite else "R", font_size=sp(12.5), bold=True,
                               color=(0.05, 0.07, 0.10, 1))
            rotulo.refresh()
            tw, th = rotulo.texture.size
            g.add(Color(1, 1, 1, 1))
            g.add(Rectangle(texture=rotulo.texture, size=(tw, th), pos=(-tw / 2.0, -th / 2.0)))
        elif tipo == "semaforo":  # caixa escura com aro claro e as três luzes acesas
            g.add(Color(0, 0, 0, 0.30))                                   # sombra
            g.add(RoundedRectangle(pos=(-dp(7.5), -dp(16)), size=(dp(15), dp(30)), radius=[dp(5)]))
            g.add(Color(0.80, 0.84, 0.90, 1))                             # aro claro: destaca no mapa escuro e no claro
            g.add(RoundedRectangle(pos=(-dp(8), -dp(14.5)), size=(dp(16), dp(29)), radius=[dp(5)]))
            g.add(Color(0.05, 0.06, 0.09, 1))
            g.add(RoundedRectangle(pos=(-dp(6.5), -dp(13)), size=(dp(13), dp(26)), radius=[dp(4)]))
            for k, cor in enumerate(((0.98, 0.24, 0.24, 1), (1.0, 0.80, 0.18, 1), (0.22, 0.92, 0.46, 1))):
                g.add(Color(*cor))
                g.add(Ellipse(pos=(-dp(3.6), dp(4.6) - k * dp(8.1)), size=(dp(7.2), dp(7.2))))
        else:  # lombada: placa de advertência (losango amarelo) com o desenho da lombada
            def losango(r):
                return [(0, r), (r, 0), (0, -r), (-r, 0)]

            def cheio(pontos, cor):
                g.add(Color(*cor))
                g.add(Mesh(vertices=[v for x, y in pontos for v in (x, y, 0, 0)], indices=[0, 1, 2, 3],
                           mode="triangle_fan"))
            cheio([(x, y - dp(2)) for x, y in losango(dp(16.5))], (0, 0, 0, 0.30))     # sombra
            cheio(losango(dp(16.5)), (0.05, 0.06, 0.09, 1))                            # contorno
            cheio(losango(dp(14.5)), (1.0, 0.80, 0.10, 1))
            g.add(Color(0.05, 0.06, 0.09, 1))
            g.add(Rectangle(pos=(-dp(8), -dp(4.5)), size=(dp(16), dp(2.2))))                 # o chão
            g.add(Ellipse(pos=(-dp(5.5), -dp(4.5)), size=(dp(11), dp(9)), angle_start=-90, angle_end=90))   # a lombada
        g.add(PopMatrix())
        return g, tr, sc

    def _escolher_sinais(self):
        """Ícones dos semáforos/lombadas à vista (de perto: de longe poluiria)."""
        self._g_sinais.clear()
        self._sinais = []
        self._ocorr_na_tela = []
        ocorrencias = self._ocorr_icones if self.zoom >= ZOOM_OCORRENCIAS else []
        if self.sinais_rota is None and self.zoom < ZOOM_RADARES and not self.marcos and not ocorrencias:
            return
        cantos = [self._local_para_geo(*self._tela_para_local(px, py))
                  for px, py in ((self.x, self.y), (self.right, self.y), (self.x, self.top),
                                 (self.right, self.top))]
        lats, lons = [c[0] for c in cantos], [c[1] for c in cantos]
        if len(self._icones) > 400:
            self._icones.clear()
        postos = []
        la0, la1, lo0, lo1 = min(lats), max(lats), min(lons), max(lons)
        if self.sinais_rota is not None:
            fonte = [p for p in self.sinais_rota if la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1]
        elif self.zoom < ZOOM_RADARES:
            fonte = []
        else:
            # de mais longe só os radares (são poucos e importam); semáforo e lombada, de perto
            fonte = sinais.na_caixa(min(lats), min(lons), max(lats), max(lons), 300,
                                    so_radares=self.zoom < ZOOM_SINAIS)
        # Casa e Trabalho: sempre à vista (são referência), por cima dos outros
        fonte = list(fonte) + [p for p in self.marcos if la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1]
        # trânsito ao vivo: antes dos outros (cabe pouco ícone na tela e este é o que muda o caminho)
        de_quem = {}
        transito_a_vista = []
        for lat, lon, tipo, o in ocorrencias:
            if la0 <= lat <= la1 and lo0 <= lon <= lo1 and (o["categoria"] != 6 or self.zoom >= ZOOM_LENTOS):
                transito_a_vista.append((lat, lon, tipo))
                de_quem[(lat, lon, tipo)] = o
        fonte = transito_a_vista[:MAX_SINAIS // 2] + fonte
        eu_na_tela = self._para_tela(self.eu[0], self.eu[1]) if self.eu else None
        for lat, lon, tipo in fonte:
            if len(postos) >= MAX_SINAIS:
                break
            sx, sy = self._para_tela(lat, lon)
            if (tipo in ("casa", "trabalho") and eu_na_tela is not None
                    and abs(sx - eu_na_tela[0]) < dp(36) and abs(sy - eu_na_tela[1]) < dp(44)):
                continue   # a pessoa está em cima do pino: ele taparia a seta
            # cruzamento com vários semáforos mapeados: um ícone só
            if any(t == tipo and abs(sx - x) < dp(30) and abs(sy - y) < dp(30) for x, y, t in postos):
                continue
            postos.append((sx, sy, tipo))
            item = self._icones.get((lat, lon, tipo))
            if item is None:
                item = self._icones[(lat, lon, tipo)] = self._icone(tipo)
            self._g_sinais.add(item[0])
            lx, ly = self._local(lat, lon)
            self._sinais.append((lx, ly, item[1], item[2], (lat, lon)))
            if (lat, lon, tipo) in de_quem:
                self._ocorr_na_tela.append((lx, ly, de_quem[(lat, lon, tipo)]))
        self._mover_sinais()

    def destacar_alerta(self, lat_lon, cor=None):
        """Navegando, o alerta que está chegando (radar, lombada, semáforo, ocorrência):
        a placa dele cresce e um anel pulsa em volta. None = nenhum."""
        novo = None if lat_lon is None else (tuple(lat_lon[:2]), tuple(cor or tema.LARANJA)[:3])
        if novo == self._destaque:
            return
        self._destaque = novo
        self._mover_sinais()
        self._desenhar_tela()
        if novo is not None:
            self._ligar_animacao()

    def saltar_icone(self, lat_lon):
        """O ícone tocado dá um \"pulo\" (cresce e volta) e uma onda sai dele."""
        self._salto = (time.monotonic(), tuple(lat_lon[:2]))
        self._onda_toque = (time.monotonic(), self._local(lat_lon[0], lat_lon[1]))
        self._ligar_animacao()

    def _mover_sinais(self):
        alvo = self._destaque[0] if self._destaque else None
        salto, pulo = self._salto, 0.0
        if salto is not None:
            f = (time.monotonic() - salto[0]) / SALTO_S
            if f >= 1.0:
                self._salto = salto = None
            else:
                pulo = 0.42 * math.sin(math.pi * f)     # cresce e volta
        for lx, ly, tr, sc, onde in self._sinais:
            # (a placa do alerta que está chegando fica 40% maior; ~25 m de folga na posição)
            perto = alvo is not None and abs(onde[0] - alvo[0]) < 0.00025 and abs(onde[1] - alvo[1]) < 0.00025
            tocado = salto is not None and abs(onde[0] - salto[1][0]) < 1e-6 and abs(onde[1] - salto[1][1]) < 1e-6
            sc.x = sc.y = (1.4 if perto else 1.0) + (pulo if tocado else 0.0)
            tr.xy = self._local_para_tela(lx, ly)
