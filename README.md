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

## Servicos usados
Sem conta nenhuma:
- Mapa: Goiania inteira vem DENTRO do app. `dados/goiania_mapa.db` sao os dados
  (OpenFreeMap/OpenStreetMap, montado por `ferramentas/empacotar_mapa.py`) e
  `dados/mapa_pronto.db` e o mapa ja desenhado nos zooms que o app usa (montado
  a cada build por `ferramentas/empacotar_prontos.py`; nao vai para o git).
- Rota: Valhalla do OpenStreetMap (perfil de bike, instrucoes em portugues,
  altimetria); reserva: OSRM. A "tranquila" mede as avenidas de cada rota.
- Busca: base offline de lugares (`dados/goiania_lugares.db`) e Photon.
- Chuva: Open-Meteo.

Com a chave gratuita da TomTom do dono (secret `TOMTOM_KEY` do GitHub, gravado
em `chaves.json` no build; o repositorio e publico e a chave nunca vai para o
codigo). Sem a chave, tudo abaixo simplesmente nao aparece:
- `transito.py`: acidentes, obras, vias interditadas (Incident Details).
- `fluxo.py`: ruas coloridas pela velocidade de agora (Vector Flow Tiles).
- `rota_tomtom.py`: rota pelo transito de agora e conferencia do caminho em uso.
- `busca.py`: busca de lugares (Fuzzy Search) e endereco de um ponto.
Tudo isso foi feito pela documentacao da TomTom e testado com respostas
simuladas: a confirmacao de verdade e no celular (Ajustes > Testar o transito).

## Voz e sons
- Falas prontas em `voz/` (Kokoro, voz original no estilo de assistente de IA,
  nao a voz real do Jarvis). Trocar voz ou texto: `falas.py` e
  `ferramentas/gerar_voz.py`.
- Sons de aviso em `sons/` (sintetizados por `ferramentas/gerar_sons.py`):
  `sons.py` diz qual som anuncia cada fala.

## Estrutura
- `main.py`: o app (GPS, destino, rotas, navegacao, recalculo, transito, voz).
- `telas/`: boot, mapa (principal), busca, hud, viagens, detalhe, config.
- `widgets/mapa.py`: o mapa (camera, toque, nomes, rota, animacoes);
  `widgets/mapa_camadas.py`: o que vai por cima das ruas (transito em cores,
  ocorrencias, semaforos/radares, toque nos lugares);
  `widgets/icones_mapa.py`: os emblemas dos lugares.
- `mapa_vetor.py` / `mvt.py`: leitura dos dados do mapa, preparo do desenho,
  pedacos prontos (do app e guardados no celular).
- `rota.py` / `rota_tomtom.py` / `navegacao.py` / `busca.py`: rotas, logica
  curva a curva e busca (testaveis no PC, sem tela).
- `transito.py` / `fluxo.py` / `clima.py` / `aprendizado.py`: transito ao vivo,
  chuva e o que o app aprende com as viagens do dono.
- `falas.py` / `voz.py` / `sons.py`: o que o assistente fala e toca.
- `segundo_plano.py` / `ao_vivo.py`: navegacao minimizada (janela flutuante) e
  corrida ao vivo.
- `gps_service.py` / `gps_android.py` / `simulador.py` / `filtro.py`: GPS real
  ou falso e o filtro do velocimetro.
- `viagem.py` / `banco.py` / `ajustes.py` / `ritmo.py`: viagens, SQLite,
  configuracoes, ritmo.
- `java/`: codigo Android (GPS, voz, servico, bolha, painel flutuante).
- `testes/`: testes automaticos (rodam no GitHub antes de cada APK).
- `ferramentas/`: geradores e `testes_tela/` (testes com a janela do app,
  so no PC); nao entram no APK.

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
