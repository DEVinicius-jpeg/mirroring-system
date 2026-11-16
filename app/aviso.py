"""Avisos para o operador por WhatsApp, via Evolution API.

Opcional: sem WHATSAPP_* no .env, nada é enviado. O envio roda em segundo
plano e nunca atrapalha a retransmissão; falhas só vão para o registro.
A chave da API nunca aparece em registro.
"""
import json
import logging
import threading
import urllib.error
import urllib.request

from . import config

log = logging.getLogger("aviso")

TENTATIVAS = 3


def configurado() -> bool:
    return bool(
        config.WHATSAPP_API_URL and config.WHATSAPP_INSTANCIA
        and config.WHATSAPP_API_KEY and config.WHATSAPP_NUMERO
    )


def _enviar(texto: str) -> bool:
    url = f"{config.WHATSAPP_API_URL.rstrip('/')}/message/sendText/{config.WHATSAPP_INSTANCIA}"
    corpo = json.dumps({"number": config.WHATSAPP_NUMERO, "text": texto}).encode()
    req = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": "application/json", "apikey": config.WHATSAPP_API_KEY},
    )
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if 200 <= resp.status < 300:
                    log.info("aviso por WhatsApp enviado")
                    return True
                log.warning("WhatsApp respondeu HTTP %s", resp.status)
        except urllib.error.HTTPError as e:
            detalhe = e.read(300).decode("utf-8", "replace")
            log.warning("WhatsApp recusou o aviso (HTTP %s): %s", e.code, detalhe)
            if 400 <= e.code < 500:
                return False          # erro de configuração: não adianta repetir
        except Exception as e:        # rede, Evolution fora do ar etc.
            log.warning("falha ao enviar aviso por WhatsApp (tentativa %d): %s", tentativa, e)
        if tentativa < TENTATIVAS:
            threading.Event().wait(5 * tentativa)
    return False


def whatsapp(texto: str) -> None:
    """Envia `texto` ao número configurado, em segundo plano."""
    if not configurado():
        return
    threading.Thread(target=_enviar, args=(texto,), daemon=True, name="aviso-whatsapp").start()
