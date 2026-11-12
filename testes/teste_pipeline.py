"""Teste do pipeline com fonte simulada (sem TikTok e sem Shopee).

Simula: live de 8 s -> queda -> espera -> live volta por 8 s -> queda ->
live não volta -> encerramento por tempo esgotado. O "destino" é um arquivo FLV.

Uso:  python -m testes.teste_pipeline
"""
import os
import subprocess
import sys
import tempfile
import time

tmp = tempfile.mkdtemp()
os.environ.update(DADOS_DIR=tmp, ESPERA_MAX_SEG="14", ESPERA_VERIFICA_SEG="2", PAINEL_SENHA="x")

from app import db, fonte  # noqa: E402
from app.retransmissao import retransmissor  # noqa: E402

t0 = time.monotonic()


def falso_ao_vivo(usuario):
    t = time.monotonic() - t0
    return t < 4 or 16 < t < 22


def falsa_captura(usuario):
    # Vídeo deitado de propósito, para exercitar o ajuste para vertical.
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-re",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "8", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-f", "mpegts", "pipe:1"]


fonte.esta_ao_vivo = falso_ao_vivo
fonte.comando_captura = falsa_captura

destino = os.path.join(tmp, "saida.flv")
retransmissor.iniciar({"usuario": "teste", "nome": "Teste"}, destino)
estados = []
while retransmissor.ativo:
    e = retransmissor.estado
    if not estados or estados[-1] != e:
        estados.append(e)
        print(f"{time.monotonic() - t0:5.1f}s  {e}")
    time.sleep(0.2)

print("aviso:", retransmissor.ultimo_aviso)
s = db.listar_sessoes()[0]
print("sessão:", s)
info = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate:format=duration",
     "-of", "default=nw=1", destino], capture_output=True, text=True).stdout
print(info)
erros = subprocess.run(["ffmpeg", "-v", "error", "-i", destino, "-f", "null", "-"],
                       capture_output=True, text=True).stderr
print("erros de decodificação:", erros.strip() or "nenhum")

assert estados[:4] == ["conectando", "ao_vivo", "espera", "ao_vivo"], estados
assert s["quedas"] == 2 and "não voltou" in s["resultado"], s
assert "width=720" in info and "height=1280" in info, info
assert retransmissor.ultimo_aviso
print("OK")
