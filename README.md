# GT-HUD

Navegacao de bike no estilo Waze (mapa, rota, curva a curva, avisos de
subida, voz de assistente) e velocimetro GPS com registro de viagens, para a
Ouxi GT20.

## Testar no PC
    pip install kivy
    python main.py
No PC o app usa o simulador (GPS falso em Goiania). Com uma rota ativa, o
simulador pedala POR ELA: da para testar a navegacao inteira sem sair de casa
(no celular: Ajustes > Modo simulador).

## Baixar o APK
O build roda sozinho a cada push (GitHub Actions). O APK mais novo fica em
https://github.com/kiritoagiota-ship-it/gt-hud/releases/latest
(arquivo GT-HUD-1.0.N.apk; instale por cima do app, as viagens continuam).

O secret DEBUG_KEYSTORE_B64 (Settings > Secrets and variables > Actions) tem a
mesma chave do TraveteFocus: todo APK sai assinado igual e atualiza por cima.

## Servicos usados (gratis, sem conta)
- Mapa: tiles do OpenStreetMap (tile.openstreetmap.org), pintados no tema do
  app por um shader. Cache de 30 dias no celular.
- Rota: Valhalla do OpenStreetMap (valhalla1.openstreetmap.de), perfil de bike,
  instrucoes em portugues e altimetria da rota (para achar as subidas).
- Busca: Nominatim do OpenStreetMap (1 busca por segundo, sem autocompletar).
Todos pedem User-Agent identificado e certificados do certifi (rede.py).

## Voz
Falas prontas em voz/ (geradas no PC com Kokoro, voz original no estilo de
assistente de IA, nao a voz real do Jarvis). Para trocar a voz ou o texto:
edite falas.py e rode ferramentas/gerar_voz.py (instrucoes no arquivo).

## Estrutura
- main.py: app, GPS, alertas, destino/rota/navegacao, recalculo, voz
- telas/: boot, mapa (principal), busca, hud (painel), viagens, detalhe, config
- widgets/: mapa, manobra, perfil (altimetria), velocimetro, trajeto,
  grafico, botao, componentes comuns
- mapa_tiles.py / rede.py: download e cache do mapa, internet em 2o plano
- rota.py / busca.py / navegacao.py: rota e subidas, busca de lugares, logica
  curva a curva (testavel no PC, sem tela)
- falas.py / voz.py: o que o assistente fala e como as falas sao tocadas
- gps_service.py / gps_android.py / simulador.py: GPS real ou falso
- java/: Localizacao.java (recebe o GPS no Android 12+) e Satelites.java
- viagem.py / banco.py / filtro.py / ajustes.py: viagem, SQLite, suavizacao,
  configuracoes
- icone/ e ferramentas/: icone, abertura e geradores (nao entram no APK)
