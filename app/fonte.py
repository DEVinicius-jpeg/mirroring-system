"""Acesso à live pública do criador no TikTok (via Streamlink).

Este é o único ponto do sistema que depende do TikTok. Se a captura parar
de funcionar, o primeiro passo é atualizar o Streamlink (reconstruir a imagem).
"""
import logging
import sys

from streamlink import Streamlink
from streamlink.exceptions import StreamlinkError

log = logging.getLogger("fonte")


def url_live(usuario: str) -> str:
    return f"https://www.tiktok.com/@{usuario}/live"


def esta_ao_vivo(usuario: str) -> bool:
    """True se o criador está com uma live no ar agora."""
    try:
        return bool(Streamlink().streams(url_live(usuario)))
    except StreamlinkError as e:
        log.info("verificação de @%s falhou: %s", usuario, e)
        return False
    except Exception:  # rede fora do ar etc.
        log.exception("erro inesperado ao verificar @%s", usuario)
        return False


def comando_captura(usuario: str) -> list[str]:
    """Comando que escreve o vídeo da live na saída padrão."""
    return [
        sys.executable, "-m", "streamlink",
        "--stdout", "--loglevel", "error",
        "--retry-open", "2",
        url_live(usuario), "best",
    ]
