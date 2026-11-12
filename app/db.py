"""Banco SQLite: criadores autorizados, sessões e configurações."""
import sqlite3
import threading
from datetime import date, datetime

from . import config

_trava = threading.Lock()
_con: sqlite3.Connection | None = None


def _c() -> sqlite3.Connection:
    global _con
    if _con is None:
        config.DADOS_DIR.mkdir(parents=True, exist_ok=True)
        _con = sqlite3.connect(config.BANCO, check_same_thread=False)
        _con.row_factory = sqlite3.Row
        _con.executescript(
            """
            CREATE TABLE IF NOT EXISTS criadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                termo_validade TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sessoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                nome TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fim TEXT,
                quedas INTEGER NOT NULL DEFAULT 0,
                segundos_espera INTEGER NOT NULL DEFAULT 0,
                resultado TEXT
            );
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
            """
        )
        _con.commit()
    return _con


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- criadores ----------

def listar_criadores() -> list[dict]:
    with _trava:
        linhas = _c().execute("SELECT * FROM criadores ORDER BY nome").fetchall()
    hoje = date.today().isoformat()
    saida = []
    for l in linhas:
        d = dict(l)
        d["ativo"] = bool(d["ativo"])
        d["termo_valido"] = d["termo_validade"] >= hoje
        d["autorizado"] = d["ativo"] and d["termo_valido"]
        saida.append(d)
    return saida


def obter_criador(cid: int) -> dict | None:
    for c in listar_criadores():
        if c["id"] == cid:
            return c
    return None


def salvar_criador(cid: int | None, usuario: str, nome: str, termo_validade: str, ativo: bool) -> int:
    with _trava:
        con = _c()
        if cid is None:
            cur = con.execute(
                "INSERT INTO criadores (usuario, nome, termo_validade, ativo) VALUES (?,?,?,?)",
                (usuario, nome, termo_validade, int(ativo)),
            )
            cid = cur.lastrowid
        else:
            con.execute(
                "UPDATE criadores SET usuario=?, nome=?, termo_validade=?, ativo=? WHERE id=?",
                (usuario, nome, termo_validade, int(ativo), cid),
            )
        con.commit()
    return cid


def remover_criador(cid: int) -> None:
    with _trava:
        _c().execute("DELETE FROM criadores WHERE id=?", (cid,))
        _c().commit()


# ---------- sessões ----------

def abrir_sessao(usuario: str, nome: str) -> int:
    with _trava:
        cur = _c().execute(
            "INSERT INTO sessoes (usuario, nome, inicio) VALUES (?,?,?)", (usuario, nome, _agora())
        )
        _c().commit()
        return cur.lastrowid


def fechar_sessao(sid: int, quedas: int, segundos_espera: int, resultado: str) -> None:
    with _trava:
        _c().execute(
            "UPDATE sessoes SET fim=?, quedas=?, segundos_espera=?, resultado=? WHERE id=?",
            (_agora(), quedas, segundos_espera, resultado, sid),
        )
        _c().commit()


def fechar_sessoes_orfas() -> None:
    """Sessões que ficaram abertas por um desligamento inesperado."""
    with _trava:
        _c().execute(
            "UPDATE sessoes SET fim=?, resultado='interrompida (sistema reiniciado)' WHERE fim IS NULL",
            (_agora(),),
        )
        _c().commit()


def listar_sessoes(limite: int = 50) -> list[dict]:
    with _trava:
        linhas = _c().execute("SELECT * FROM sessoes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    return [dict(l) for l in linhas]


# ---------- configurações ----------

def obter_config(chave: str, padrao: str) -> str:
    with _trava:
        l = _c().execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    return l["valor"] if l else padrao


def definir_config(chave: str, valor: str) -> None:
    with _trava:
        _c().execute(
            "INSERT INTO config (chave, valor) VALUES (?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, valor),
        )
        _c().commit()
