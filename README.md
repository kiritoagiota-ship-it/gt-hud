# GT-HUD — Fase 1

Velocimetro GPS e registro de viagens para a Ouxi GT20.

## Testar no PC
    pip install kivy plyer
    python main.py
No PC o app usa o simulador automaticamente (GPS falso rodando em Goiania).

## Gerar o APK
1. Crie um repositorio novo no GitHub (ex.: gt-hud) e envie todos estes arquivos,
   incluindo a pasta .github.
2. Opcional, mas recomendado: em Settings > Secrets and variables > Actions, crie o
   secret DEBUG_KEYSTORE_B64 com a mesma keystore usada no TraveteFocus.
   Assim cada APK novo instala por cima do anterior sem apagar as viagens.
3. O build roda sozinho a cada push. O APK fica em Actions > ultimo build > Artifacts.

## Estrutura
- main.py: app, GPS e salvamento de viagens
- gps_service.py / simulador.py: GPS real (Android) ou falso (PC)
- filtro.py: suavizacao da velocidade
- viagem.py / banco.py: calculo e gravacao das viagens (SQLite)
- ajustes.py: configuracoes (JSON)
- telas/: boot, hud, viagens, detalhe, config
- widgets/: velocimetro, botao, grafico, componentes comuns
