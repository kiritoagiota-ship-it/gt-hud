# GT-HUD — guia da pasta

Esta é a pasta com tudo do app GT-HUD. Este guia explica, sem termo técnico,
o que é cada coisa aqui dentro. Você não precisa mexer em nada para usar o
app: é só um mapa para se achar quando abrir a pasta.

## O que é cada pasta

| Pasta | O que tem dentro |
|---|---|
| `telas` | As telas do app: abertura, mapa (a principal), busca, ajustes, viagens. |
| `widgets` | As peças que aparecem nas telas: o mapa, o velocímetro, os botões, os ícones dos lugares. |
| `mapa_motor` | O "motor" do mapa: lê os dados de Goiânia e prepara o desenho das ruas, prédios e praças. Também os semáforos, lombadas e radares. |
| `rotas_e_busca` | Tudo de rota: calcular o caminho (rápido, tranquilo, noturno, pelo trânsito), a navegação curva a curva, a busca de lugares e de endereços. |
| `transito_e_clima` | O trânsito ao vivo da TomTom (acidentes, ruas coloridas) e o aviso de chuva. |
| `audio` | A voz do assistente e os sons de aviso. As gravações ficam em `audio/voz` e `audio/sons`. |
| `gps` | A leitura do GPS do celular, o GPS de mentira usado nos testes do PC e o cálculo que deixa o velocímetro firme. |
| `sistema` | O que funciona por trás: seus ajustes, as viagens gravadas, a internet, o tema claro/escuro, a janela flutuante, a corrida ao vivo, o diagnóstico. |
| `dados` | Os dados que vão dentro do app: o mapa de Goiânia, a lista de comércios, os semáforos e radares. |
| `java` | Pedaços feitos direto para o Android (GPS, voz, janela flutuante). |
| `icone` | O ícone do app e a imagem de abertura. |
| `docs` | A página da internet que seu amigo abre para acompanhar a corrida ao vivo. |
| `testes` | As conferências automáticas que rodam antes de cada versão. |
| `ferramentas` | Programas de apoio que rodam só no PC (gerar a voz, os sons, o mapa, e os testes com a janela do app). Não vão para o celular. |

## Os arquivos soltos

| Arquivo | Para que serve |
|---|---|
| `main.py` | O começo do app: é ele que liga tudo. |
| `caminhos.py` | Diz ao app em quais pastas o código está. |
| `buildozer.spec` | A "receita" para transformar o código no arquivo do app (APK). |
| `intent_filters.xml` | Faz o GT-HUD aparecer no "Abrir com" do Android. |
| `hooks.py` | Um ajuste usado só na hora de montar o APK. |
| `README.md` | A descrição técnica do projeto. |
| `COMECE-AQUI.md` | Este guia. |

## Onde fica o que

- **O app para instalar (APK):** não fica nesta pasta. Fica na internet, em
  github.com/kiritoagiota-ship-it/gt-hud → Releases.
- **Suas viagens e ajustes:** ficam só no celular, não aqui.
- **A chave da TomTom:** fica guardada no GitHub (Settings → Secrets), nunca
  nesta pasta nem no código.

## Como testar no PC

Com o Python instalado, abra esta pasta no terminal e rode:

```
python main.py
```

Abre uma janela com o app usando um GPS de mentira.

## Cuidados

- Não renomeie nem mova as pastas: o app procura cada uma pelo nome.
- Não apague a pasta `.git` (ela é oculta): é o histórico de tudo que já foi feito.
- Pode apagar sem medo, se aparecerem: pastas `__pycache__` e as pastas de
  fotos e `.tmp` dentro de `ferramentas/testes_tela`. São sobras de teste e
  voltam sozinhas quando os testes rodam.
