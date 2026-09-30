import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from schemas import AgentConfig, StatusResponse, ActionResponse, LogEntry
from storage import Storage
from agent_adapter import SimulationAgentAdapter
from s2gpr_browser import s2gpr_browser


load_dotenv()

logger = logging.getLogger("s2gpr")


PORT = int(os.getenv("PORT", "8000"))
API_TOKEN = os.getenv("API_TOKEN", "")
DEV_NO_AUTH = os.getenv("DEV_NO_AUTH", "false").lower() == "true"
DATABASE_PATH = os.getenv("DATABASE_PATH", "./agent_api.db")

LOVABLE_ORIGINS = [
    x.strip()
    for x in os.getenv(
        "LOVABLE_ORIGINS",
        "http://localhost:5173"
    ).split(",")
    if x.strip()
]


app = FastAPI(
    title="Agente de Lances S2GPR API",
    version="1.1.1",
    description=(
        "API de controle do Agente de Lances S2GPR. "
        "Simulação habilitada e conector de autenticação supervisionada."
    ),
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=LOVABLE_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)


storage = Storage(DATABASE_PATH)
agent = SimulationAgentAdapter(storage)


class S2GPRCredentials(BaseModel):
    usuario: str
    senha: str


bearer_scheme = HTTPBearer(auto_error=False)


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)
):
    if DEV_NO_AUTH:
        return True

    if not API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="API_TOKEN não configurado no servidor.",
        )

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or credentials.credentials != API_TOKEN
    ):
        raise HTTPException(
            status_code=401,
            detail="Não autorizado.",
        )

    return True



def response(message: str) -> ActionResponse:
    return ActionResponse(
        ok=True,
        status=StatusResponse(**agent.get_state()),
        message=message,
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "Agente de Lances S2GPR API",
        "mode": "simulacao",
        "browser_connector": True,
        "real_s2gpr_enabled": False,
    }


@app.get(
    "/status",
    response_model=StatusResponse,
    dependencies=[Depends(require_token)],
)
def status():
    return StatusResponse(**agent.get_state())


@app.post(
    "/authorize",
    response_model=ActionResponse,
    dependencies=[Depends(require_token)],
)
def authorize():
    agent.authorize()
    return response(
        "Agente autorizado para simulação."
    )


@app.post(
    "/start",
    response_model=ActionResponse,
    dependencies=[Depends(require_token)],
)
async def start():
    try:
        await agent.start()

        return response(
            "Simulação iniciada."
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@app.post(
    "/pause",
    response_model=ActionResponse,
    dependencies=[Depends(require_token)],
)
async def pause():
    try:
        await agent.pause()

        return response(
            "Simulação pausada."
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@app.post(
    "/resume",
    response_model=ActionResponse,
    dependencies=[Depends(require_token)],
)
async def resume():
    try:
        await agent.resume()

        return response(
            "Simulação retomada."
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@app.post(
    "/stop",
    response_model=ActionResponse,
    dependencies=[Depends(require_token)],
)
async def stop():
    await agent.stop()

    return response(
        "Simulação encerrada."
    )


@app.get(
    "/config",
    response_model=AgentConfig,
    dependencies=[Depends(require_token)],
)
def get_config():
    return AgentConfig(
        **agent.get_config()
    )


@app.put(
    "/config",
    response_model=AgentConfig,
    dependencies=[Depends(require_token)],
)
def put_config(config: AgentConfig):
    try:
        saved = agent.set_config(
            config.model_dump()
        )

        return AgentConfig(
            **saved
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )


@app.get(
    "/logs",
    response_model=list[LogEntry],
    dependencies=[Depends(require_token)],
)
def logs(limit: int = 100):
    return [
        LogEntry(**x)
        for x in storage.list_logs(limit)
    ]


# =========================================================
# CONECTOR S2GPR
# =========================================================


@app.post(
    "/s2gpr/connect",
    dependencies=[Depends(require_token)],
)
async def s2gpr_connect(
    credentials: S2GPRCredentials
):
    """
    Abre uma sessão supervisionada no portal S2GPR.

    A senha é usada somente durante a tentativa
    de autenticação e não é salva neste endpoint.
    """

    if not credentials.usuario.strip():
        raise HTTPException(
            status_code=422,
            detail="Usuário/CPF obrigatório.",
        )

    if not credentials.senha:
        raise HTTPException(
            status_code=422,
            detail="Senha obrigatória.",
        )

    try:
        result = await s2gpr_browser.connect(
            usuario=credentials.usuario.strip(),
            senha=credentials.senha,
        )

        # Safe operational log: never log credentials, tokens or raw portal HTML.
        logger.info(
            "S2GPR_CONNECT status=%s reason=%s connected=%s",
            result.get("status"),
            result.get("reason"),
            result.get("connected"),
        )
        return result

    except Exception:
        logger.exception("S2GPR_CONNECT unexpected_connector_error")
        raise HTTPException(
            status_code=500,
            detail="Falha técnica ao conectar ao S2GPR.",
        )


@app.get(
    "/s2gpr/session",
    dependencies=[Depends(require_token)],
)
async def s2gpr_session():
    """
    Retorna somente o estado da sessão.
    Não retorna usuário nem senha.
    """

    try:
        return await s2gpr_browser.session_status()

    except Exception:
        logger.exception("S2GPR_SESSION unexpected_connector_error")
        raise HTTPException(
            status_code=500,
            detail="Falha técnica ao consultar sessão S2GPR.",
        )


@app.post(
    "/s2gpr/disconnect",
    dependencies=[Depends(require_token)],
)
async def s2gpr_disconnect():
    """
    Encerra a sessão do navegador.
    """

    try:
        return await s2gpr_browser.disconnect()

    except Exception:
        logger.exception("S2GPR_DISCONNECT unexpected_connector_error")
        raise HTTPException(
            status_code=500,
            detail="Falha técnica ao desconectar a sessão S2GPR.",
        )


@app.get(
    "/s2gpr/quotations",
    dependencies=[Depends(require_token)],
)
async def s2gpr_quotations(mine: bool = True, status: str | None = None):
    """
    Descoberta somente leitura da área de cotações na sessão autenticada.
    Não envia propostas, lances ou formulários.
    """
    try:
        return await s2gpr_browser.quotations(mine=mine, status=status)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Falha ao consultar cotações no S2GPR.",
        )


@app.get("/")
def root():
    return {
        "name": "Agente de Lances S2GPR API",
        "version": "1.1.1",
        "mode": "simulacao",
        "browser_connector": True,
        "real_s2gpr_enabled": False,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
    )
