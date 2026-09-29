# Contrato Lovable ↔ API Python

Base URL:
`https://SEU-ENDERECO-DA-API`

Headers para rotas protegidas:
`Authorization: Bearer <token-servidor>`

## GET /status
Retorna o estado atual do agente.

## POST /authorize
Autoriza a execução em modo simulação.

## POST /start
Inicia a simulação.

## POST /pause
Pausa a simulação.

## POST /resume
Retoma a simulação.

## POST /stop
Encerra a simulação.

## GET /config
Obtém parâmetros atuais.

## PUT /config
Atualiza parâmetros.

## GET /logs?limit=100
Retorna log operacional.

## Observação para a Lovable
O front-end não deve carregar o token secreto.
Crie uma função server-side/edge que chama esta API e devolve ao navegador apenas os dados necessários.
