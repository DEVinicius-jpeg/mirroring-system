# espelho-live

Retransmite na Shopee Live a live que um criador parceiro está fazendo no TikTok.
Uso interno de TI, uma retransmissão por vez.

## Regras do projeto

- Só entram na lista criadores com **termo escrito** que autorize a captura da live
  no TikTok e a retransmissão na loja. O sistema recusa quem está fora da lista,
  desativado ou com termo vencido.
- A retransmissão contraria a regra da Shopee Live contra repostar conteúdo de
  outras lives e usa um meio não oficial de leitura do TikTok. Por isso o piloto
  roda em **conta secundária**; na primeira punição, o piloto pausa.
- A chave da Shopee é colada no painel a cada live e fica só na memória. Nenhum
  vídeo é gravado em disco.

## Instalação (máquina dedicada, Windows com Docker Desktop)

1. Copie `.env.example` para `.env` e defina `PAINEL_SENHA`.
2. Na pasta do projeto: `docker compose up -d --build`
3. Abra `http://IP-DA-MAQUINA:8080` em um computador da rede do escritório.

Os dados (lista de criadores e registro de sessões) ficam em `dados/espelho.db`,
fora do Git. Para atualizar depois de um `git pull`: `docker compose up -d --build`.

## Operação de uma live

1. Antes do horário combinado, crie a live na Shopee (Central do Vendedor >
   Central de Marketing > Live), monte a vitrine e copie a **URL** e a **Chave**.
2. No painel, escolha o criador, cole URL e chave e clique em **Iniciar retransmissão**.
3. Acompanhe o estado:
   - **Conectando**: a tela de espera está sendo enviada enquanto a live é localizada.
   - **Retransmitindo ao vivo**: o vídeo do criador está indo para a Shopee.
   - **Tela de espera no ar**: a live caiu. O sistema tenta de novo a cada 10 s e
     encerra sozinho após 3 minutos, com um aviso em vermelho no painel.
4. Ao terminar, clique em **Parar retransmissão** e encerre a live na Shopee.

Responda o chat da Shopee pelo aplicativo ou pela Central do Vendedor e repasse
as perguntas ao criador pelo canal combinado.

## Detecção automática

Quando ativada, o sistema consulta o perfil de cada criador autorizado a cada
90 s e mostra no painel quem está ao vivo. Ela só avisa; o início é sempre manual.
Pode ser desligada no próprio painel.

## Primeiro teste

Use o modo **Live Teste** da Shopee na conta secundária, com um criador autorizado
ao vivo. Confira imagem, som e orientação no aplicativo da Shopee. O formato
enviado é vertical 720x1280, 30 fps, H.264 + AAC, 2500 kbit/s (ajustável no `.env`).

## Quando algo falha

| Sintoma | O que verificar |
|---|---|
| Fica em "Conectando" e encerra em 3 min | O criador está mesmo ao vivo? O usuário está escrito certo? Se sim, o TikTok pode ter mudado: atualize com `docker compose build --no-cache` e suba de novo. |
| Aviso "erro no envio para a Shopee" | URL ou chave erradas ou vencidas (gere outras criando nova live), ou a Shopee encerrou a sessão. O detalhe técnico aparece no aviso. |
| Imagem travando | Processador da máquina no limite ou internet instável. Reduza `VIDEO_BITRATE_K`. |

Registros do sistema: `docker compose logs -f`

## Estrutura

- `app/fonte.py`: leitura da live do TikTok (Streamlink). Único ponto que depende do TikTok.
- `app/retransmissao.py`: FFmpeg, tela de espera, reconexão e registro da sessão.
- `app/detector.py`: detecção automática.
- `app/main.py`, `app/static/`: painel web e API.
- `app/static/espera.png`: tela de espera (troque por outra imagem 720x1280 se quiser).
- `testes/teste_pipeline.py`: teste com fonte simulada. Requer Linux com FFmpeg;
  rode dentro do contêiner ou no WSL: `python -m testes.teste_pipeline`
