"""Painel web e API do espelho-live."""
import hmac
import logging
import re
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import config, db
from .detector import detector
from .retransmissao import montar_destino, retransmissor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("painel")

USUARIO_RE = re.compile(r"^[A-Za-z0-9._]{2,24}$")


@asynccontextmanager
async def ciclo(app: FastAPI):
    if not config.PAINEL_SENHA:
        raise RuntimeError("Defina a variável de ambiente PAINEL_SENHA antes de iniciar.")
    db.fechar_sessoes_orfas()
    detector.iniciar(lambda: retransmissor.criador["usuario"] if retransmissor.ativo else None)
    yield
    retransmissor.parar()


app = FastAPI(title="espelho-live", lifespan=ciclo, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware, secret_key=config.SEGREDO_SESSAO, same_site="strict", max_age=12 * 3600
)


def exigir_login(request: Request) -> None:
    if not request.session.get("ok"):
        raise HTTPException(401, "Sessão expirada. Entre novamente.")


# ---------- páginas ----------

@app.get("/")
def pagina(request: Request):
    if not request.session.get("ok"):
        return RedirectResponse("/login", 303)
    return FileResponse(config.RAIZ / "static" / "painel.html", headers={"Cache-Control": "no-store"})


@app.get("/login")
def pagina_login():
    return FileResponse(config.RAIZ / "static" / "login.html", headers={"Cache-Control": "no-store"})


class Login(BaseModel):
    senha: str


@app.post("/api/login")
def login(dados: Login, request: Request):
    if not hmac.compare_digest(dados.senha.encode(), config.PAINEL_SENHA.encode()):
        log.warning("tentativa de login recusada de %s", request.client.host if request.client else "?")
        raise HTTPException(401, "Senha incorreta.")
    request.session["ok"] = True
    return {"ok": True}


@app.post("/api/sair")
def sair(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------- estado ----------

@app.get("/api/estado", dependencies=[Depends(exigir_login)])
def estado():
    return {
        "retransmissao": retransmissor.resumo(),
        "deteccao": {
            "ativa": detector.ativa,
            "ao_vivo": [u for u, v in detector.ao_vivo.items() if v],
            "ultima_verificacao": detector.ultima_verificacao,
        },
        "criadores": db.listar_criadores(),
        "sessoes": db.listar_sessoes(30),
    }


# ---------- retransmissão ----------

class Inicio(BaseModel):
    criador_id: int
    url: str
    chave: str = ""


@app.post("/api/iniciar", dependencies=[Depends(exigir_login)])
def iniciar(dados: Inicio):
    criador = db.obter_criador(dados.criador_id)
    if not criador:
        raise HTTPException(404, "Criador não encontrado.")
    if not criador["ativo"]:
        raise HTTPException(403, "Este criador está desativado na lista.")
    if not criador["termo_valido"]:
        raise HTTPException(403, "O termo de autorização deste criador está vencido.")
    url = dados.url.strip()
    if not re.match(r"^rtmps?://\S+$", url):
        raise HTTPException(422, "A URL da Shopee deve começar com rtmp:// ou rtmps://.")
    if re.search(r"\s", dados.chave.strip()):
        raise HTTPException(422, "A chave não pode conter espaços.")
    try:
        retransmissor.iniciar(criador, montar_destino(url, dados.chave))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    log.info("retransmissão de @%s iniciada", criador["usuario"])
    return {"ok": True}


@app.post("/api/parar", dependencies=[Depends(exigir_login)])
def parar():
    retransmissor.parar()
    return {"ok": True}


@app.post("/api/aviso/dispensar", dependencies=[Depends(exigir_login)])
def dispensar():
    retransmissor.dispensar_aviso()
    return {"ok": True}


# ---------- criadores ----------

class Criador(BaseModel):
    usuario: str
    nome: str
    termo_validade: str
    ativo: bool = True


def _validar(c: Criador) -> Criador:
    c.usuario = c.usuario.strip().lstrip("@")
    c.nome = c.nome.strip()
    if not USUARIO_RE.match(c.usuario):
        raise HTTPException(422, "Usuário do TikTok inválido (use só letras, números, ponto e sublinhado).")
    if not c.nome:
        raise HTTPException(422, "Informe o nome do criador.")
    try:
        date.fromisoformat(c.termo_validade)
    except ValueError:
        raise HTTPException(422, "Informe a validade do termo de autorização.")
    return c


def _salvar(cid: int | None, c: Criador) -> dict:
    c = _validar(c)
    for outro in db.listar_criadores():
        if outro["usuario"].lower() == c.usuario.lower() and outro["id"] != cid:
            raise HTTPException(409, "Este usuário já está na lista.")
    return {"id": db.salvar_criador(cid, c.usuario, c.nome, c.termo_validade, c.ativo)}


@app.post("/api/criadores", dependencies=[Depends(exigir_login)])
def criar(c: Criador):
    return _salvar(None, c)


@app.put("/api/criadores/{cid}", dependencies=[Depends(exigir_login)])
def editar(cid: int, c: Criador):
    if not db.obter_criador(cid):
        raise HTTPException(404, "Criador não encontrado.")
    return _salvar(cid, c)


@app.delete("/api/criadores/{cid}", dependencies=[Depends(exigir_login)])
def remover(cid: int):
    alvo = db.obter_criador(cid)
    if alvo and retransmissor.ativo and retransmissor.criador["usuario"] == alvo["usuario"]:
        raise HTTPException(409, "Pare a retransmissão deste criador antes de removê-lo.")
    db.remover_criador(cid)
    return {"ok": True}


# ---------- detecção ----------

class Deteccao(BaseModel):
    ativa: bool


@app.post("/api/deteccao", dependencies=[Depends(exigir_login)])
def deteccao(d: Deteccao):
    detector.definir(d.ativa)
    return {"ok": True}
