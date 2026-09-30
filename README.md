# GT-HUD — Fase 1

Velocimetro GPS e registro de viagens para a Ouxi GT20.

## Testar no PC
    pip install kivy
    python main.py
No PC o app usa o simulador automaticamente (GPS falso rodando em Goiania).
Ligar "Tela deitada" nos Ajustes gira a janela, para testar o layout deitado.

## Baixar o APK
O build roda sozinho a cada push (GitHub Actions). O APK mais novo fica em
https://github.com/kiritoagiota-ship-it/gt-hud/releases/latest
(arquivo GT-HUD-1.0.N.apk; instale por cima do app, as viagens continuam).

O secret DEBUG_KEYSTORE_B64 (Settings > Secrets and variables > Actions) tem a
mesma chave do TraveteFocus: todo APK sai assinado igual e atualiza por cima.

## Estrutura
- main.py: app, GPS, alerta/vibracao no limite e salvamento de viagens
- gps_service.py / simulador.py: GPS real (Android) ou falso (PC)
- gps_android.py: ouve so o satelite no Android (sem wi-fi/antena)
- android_utils.py: permissoes, tela ligada, orientacao e vibracao
- filtro.py: suavizacao da velocidade
- viagem.py / banco.py: calculo (com pausa automatica) e gravacao das viagens (SQLite)
- ajustes.py: configuracoes (JSON)
- telas/: boot, hud, viagens, detalhe, config (todas se ajeitam em pe e deitadas)
- widgets/: velocimetro, botao, grafico, trajeto, componentes comuns
- icone/: icone e abertura do app; ferramentas/gerar_icones.py gera de novo
  (nenhuma das duas pastas entra no APK)
