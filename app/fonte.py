"""Acesso à live do criador no TikTok (via Streamlink).

Este é o único ponto do sistema que depende do TikTok. Se a captura parar
de funcionar, o primeiro passo é atualizar o Streamlink (reconstruir a imagem).

Lives que exigem login só funcionam com TIKTOK_COOKIE preenchido no .env.
O cookie nunca vai para a linha de comando, registros ou painel: a captura
o recebe por um arquivo de configuração do Streamlink legível só por este
processo.
"""
import atexit
import logging
import os
import sys
import tempfile

from streamlink import Streamlink
from streamlink.exceptions import StreamlinkError

from . import config

log = logging.getLogger("fonte")


def _ler_cookies(bruto: str) -> dict[str, str]:
    """Aceita só o valor do sessionid ou a linha inteira 'a=1; b=2'."""
    bruto = bruto.strip().strip('"').strip("'")
    if not bruto:
        return {}
    if bruto.lower().startswith("cookie:"):
        bruto = bruto[len("cookie:"):]
    if "=" not in bruto:
        return {"sessionid": bruto.strip()}
    cookies = {}
    for parte in bruto.split(";"):
        nome, sep, valor = parte.strip().partition("=")
        if sep and nome.strip():
            cookies[nome.strip()] = valor.strip()
    return cookies


COOKIES = _ler_cookies(config.TIKTOK_COOKIE)


def _criar_config_captura() -> str | None:
    """Arquivo de configuração do Streamlink com os cookies (permissão 600)."""
    if not COOKIES:
        return None
    fd, caminho = tempfile.mkstemp(prefix="streamlink-", suffix=".conf")
    with os.fdopen(fd, "w") as f:
        for nome, valor in COOKIES.items():
            f.write(f"http-cookie={nome}={valor}\n")
    os.chmod(caminho, 0o600)
    atexit.register(lambda: os.path.exists(caminho) and os.remove(caminho))
    return caminho


_CONFIG_CAPTURA = _criar_config_captura()
if COOKIES:
    log.info("TikTok: usando conta logada (%d cookie(s))", len(COOKIES))


# Qualidades em ordem de preferência. Só H.264 com vídeo ("h264_ao" é só
# áudio). O H.265 do TikTok vem num FLV fora do padrão que o FFmpeg não lê
# (vídeo "unknown"), então "best", que costuma ser "h265_origin", fica por
# último, só para o caso de não haver H.264.
QUALIDADES = [
    "h264_origin", "h264_uhd_60", "h264_uhd", "h264_hd_60", "h264_hd",
    "h264_sd", "h264_ld", "best",
]


def escolher_qualidade(disponiveis) -> str | None:
    return next((q for q in QUALIDADES if q in disponiveis), None)


def url_live(usuario: str) -> str:
    return f"https://www.tiktok.com/@{usuario}/live"


def _sessao() -> Streamlink:
    sessao = Streamlink()
    if COOKIES:
        sessao.set_option("http-cookies", COOKIES)
    return sessao


def esta_ao_vivo(usuario: str) -> bool:
    """True se o criador está com uma live no ar e o vídeo está acessível agora."""
    try:
        streams = _sessao().streams(url_live(usuario))
        if streams and not escolher_qualidade(streams).startswith("h264"):
            log.warning("@%s está ao vivo só em %s; a captura pode falhar", usuario, list(streams))
        return bool(streams)
    except StreamlinkError as e:
        log.info("verificação de @%s falhou: %s", usuario, e)
        return False
    except Exception:  # rede fora do ar etc.
        log.exception("erro inesperado ao verificar @%s", usuario)
        return False


def comando_captura(usuario: str) -> list[str]:
    """Comando que escreve o vídeo da live na saída padrão."""
    cmd = [sys.executable, "-m", "streamlink"]
    if _CONFIG_CAPTURA:
        cmd += ["--config", _CONFIG_CAPTURA]
    return cmd + [
        "--stdout", "--loglevel", "error",
        "--retry-open", "2",
        url_live(usuario), ",".join(QUALIDADES),
    ]
