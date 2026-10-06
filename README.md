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

## Corrida ao vivo (link para alguém acompanhar pela web)

Na navegação, o botão **Ao vivo** manda um link pelo WhatsApp; quem abre vê a
posição, a rota, a velocidade e a hora de chegada numa página
(`docs/acompanhar/`, publicada pelo GitHub Pages). Ao chegar ou encerrar, a
posição e o caminho são apagados do banco.

A posição passa por um banco gratuito do próprio dono (Firebase Realtime
Database, plano Spark). Configuração, uma vez só:

1. Em <https://console.firebase.google.com>, criar um projeto (pode desligar o
   Google Analytics).
2. No menu, **Criação → Realtime Database → Criar banco de dados** (qualquer
   região; começar no modo bloqueado).
3. Na aba **Regras**, apagar o que estiver lá, colar o conteúdo de
   [`docs/regras-do-banco.json`](docs/regras-do-banco.json) e **Publicar**.
   Com essas regras: só escreve numa corrida quem tem a senha dela (o app),
   ninguém lê a senha, ninguém lista as corridas, e só quem tem o link lê a
   posição.
4. Na aba **Dados**, copiar o endereço do banco (termina em `firebaseio.com`
   ou `firebasedatabase.app`).
5. No app: **Ajustes → Corrida ao vivo → Configurar**, colar o endereço e
   tocar em **Salvar e testar**.

O endereço fica só no celular (o repositório é público). Para testar a página
no PC sem Firebase: `python ferramentas/simular_ao_vivo.py`.
