"""Teste da API do painel (sem TikTok e sem Shopee).  Uso: python -m testes.teste_api"""
import os
import tempfile
from datetime import date, timedelta

os.environ.update(DADOS_DIR=tempfile.mkdtemp(), PAINEL_SENHA="segredo")

from fastapi.testclient import TestClient  # noqa: E402

from app import fonte  # noqa: E402
from app.main import app  # noqa: E402

fonte.esta_ao_vivo = lambda u: False
amanha = (date.today() + timedelta(days=1)).isoformat()
ontem = (date.today() - timedelta(days=1)).isoformat()

with TestClient(app) as c:
    assert c.get("/api/estado").status_code == 401
    assert c.get("/", follow_redirects=False).status_code == 303
    assert c.post("/api/login", json={"senha": "errada"}).status_code == 401
    assert c.post("/api/login", json={"senha": "segredo"}).status_code == 200
    assert c.get("/").status_code == 200

    assert c.post("/api/criadores", json={"usuario": "tem espaço", "nome": "X", "termo_validade": amanha}).status_code == 422
    a = c.post("/api/criadores", json={"usuario": "@ana.loja", "nome": "Ana", "termo_validade": amanha}).json()["id"]
    assert c.post("/api/criadores", json={"usuario": "ANA.loja", "nome": "Ana 2", "termo_validade": amanha}).status_code == 409
    b = c.post("/api/criadores", json={"usuario": "beto", "nome": "Beto", "termo_validade": ontem}).json()["id"]
    d = c.post("/api/criadores", json={"usuario": "caio", "nome": "Caio", "termo_validade": amanha, "ativo": False}).json()["id"]

    ok = {"url": "rtmp://exemplo/live", "chave": "abc"}
    assert c.post("/api/iniciar", json={"criador_id": 999, **ok}).status_code == 404
    assert c.post("/api/iniciar", json={"criador_id": b, **ok}).status_code == 403   # termo vencido
    assert c.post("/api/iniciar", json={"criador_id": d, **ok}).status_code == 403   # desativado
    assert c.post("/api/iniciar", json={"criador_id": a, "url": "http://x", "chave": "k"}).status_code == 422

    e = c.get("/api/estado").json()
    assert [x["autorizado"] for x in sorted(e["criadores"], key=lambda x: x["nome"])] == [True, False, False]
    assert e["deteccao"]["ativa"] is True
    c.post("/api/deteccao", json={"ativa": False})
    assert c.get("/api/estado").json()["deteccao"]["ativa"] is False

    assert c.put(f"/api/criadores/{b}", json={"usuario": "beto", "nome": "Beto", "termo_validade": amanha}).status_code == 200
    assert c.delete(f"/api/criadores/{d}").status_code == 200
    assert len(c.get("/api/estado").json()["criadores"]) == 2

    c.post("/api/sair")
    assert c.get("/api/estado").status_code == 401
print("OK")
