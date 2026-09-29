# API Python — Agente de Lances S2GPR

Esta API é a ponte entre a Lovable e o agente em Python.

## O que esta versão faz

- `/health`
- `/status`
- `/authorize`
- `/start`
- `/pause`
- `/resume`
- `/stop`
- `/config`
- `/logs`

Ela roda **somente em modo simulação**.
Não acessa o S2GPR real, não faz login no portal e não envia lances reais.

## 1. Instalar

No PowerShell, dentro desta pasta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Configurar

Copie `.env.example` para `.env`.

Use um token forte em `API_TOKEN`.

Exemplo:

```env
PORT=8000
API_TOKEN=COLOQUE_UM_TOKEN_FORTE_AQUI
LOVABLE_ORIGINS=https://SEU-PROJETO.lovable.app
DATABASE_PATH=./agent_api.db
DEV_NO_AUTH=false
```

Não envie o token em conversa nem coloque o token no código-fonte.

## 3. Rodar localmente

```powershell
.\.venv\Scripts\python.exe main.py
```

Abra:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 4. Como a Lovable conversa com a API

Em produção, a Lovable deve chamar a API por HTTPS.

Fluxo:

`Lovable -> função de servidor/edge -> API Python -> agente -> resposta`

**Importante:** o token da API não deve ficar exposto no JavaScript do navegador.
Guarde o segredo em uma função de servidor/edge da Lovable/Supabase.

Exemplos de chamadas:

```http
GET /status
Authorization: Bearer SEU_TOKEN
```

```http
POST /authorize
Authorization: Bearer SEU_TOKEN
```

```http
POST /start
Authorization: Bearer SEU_TOKEN
```

```http
PUT /config
Authorization: Bearer SEU_TOKEN
Content-Type: application/json

{
  "initial_value": 10000,
  "floor_value": 8000,
  "decrement": 100,
  "interval_seconds": 2,
  "competitors": [
    {"name": "Concorrente A", "min_value": 8600},
    {"name": "Concorrente B", "min_value": 8400}
  ]
}
```

## 5. Próxima integração

O arquivo `agent_adapter.py` foi criado justamente para não prender a Lovable ao simulador interno.

Na próxima fase, substituímos `SimulationAgentAdapter` por um adapter que chama a lógica já existente em:

`C:\AGENTES\Agente_Lances_S2GPR\src\simulador.py`

Os endpoints da Lovable continuam iguais.

Depois disso, podemos hospedar a API em nuvem e configurar na Lovable uma variável:

`AGENT_API_BASE_URL=https://api.seudominio.com`

## 6. Segurança

- Não habilite modo real ainda.
- Não armazene credenciais do S2GPR em texto puro.
- Não coloque senha/token no front-end.
- Não automatize CAPTCHA, MFA ou mecanismos de segurança.
- Antes da operação real, valide regras e autorização do portal.
