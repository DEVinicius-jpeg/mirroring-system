"""Configurações fixas, lidas de variáveis de ambiente."""
import os
import secrets
from pathlib import Path

PAINEL_SENHA = os.environ.get("PAINEL_SENHA", "")
SEGREDO_SESSAO = os.environ.get("SEGREDO_SESSAO") or secrets.token_hex(32)

# Cookie de uma conta (secundária) logada no TikTok. Opcional: só é preciso
# para lives que exigem login. Aceita o valor do "sessionid" ou a linha
# inteira de cookies ("nome=valor; nome2=valor2").
TIKTOK_COOKIE = os.environ.get("TIKTOK_COOKIE", "").strip()

# Aviso por WhatsApp (Evolution API) quando a retransmissão para sozinha.
# Opcional: com algum destes vazio, nenhum aviso é enviado.
WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "").strip()
WHATSAPP_INSTANCIA = os.environ.get("WHATSAPP_INSTANCIA", "").strip()
WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "").strip()
WHATSAPP_NUMERO = "".join(c for c in os.environ.get("WHATSAPP_NUMERO", "") if c.isdigit())

DADOS_DIR = Path(os.environ.get("DADOS_DIR", "/data"))
BANCO = DADOS_DIR / "espelho.db"

RAIZ = Path(__file__).resolve().parent
TELA_ESPERA = Path(os.environ.get("TELA_ESPERA", RAIZ / "static" / "espera.png"))

# Tempo máximo em tela de espera antes de encerrar a retransmissão.
ESPERA_MAX_SEG = int(os.environ.get("ESPERA_MAX_SEG", "180"))
# Intervalo entre tentativas de reencontrar a live durante a espera.
ESPERA_VERIFICA_SEG = int(os.environ.get("ESPERA_VERIFICA_SEG", "10"))
# Sem dados da fonte por este tempo, a live é considerada caída.
FONTE_SILENCIO_SEG = int(os.environ.get("FONTE_SILENCIO_SEG", "20"))
# Intervalo da detecção automática de lives.
DETECCAO_INTERVALO_SEG = int(os.environ.get("DETECCAO_INTERVALO_SEG", "90"))

VIDEO_LARGURA = int(os.environ.get("VIDEO_LARGURA", "720"))
VIDEO_ALTURA = int(os.environ.get("VIDEO_ALTURA", "1280"))
VIDEO_FPS = int(os.environ.get("VIDEO_FPS", "30"))
VIDEO_BITRATE_K = int(os.environ.get("VIDEO_BITRATE_K", "2500"))
AUDIO_BITRATE_K = int(os.environ.get("AUDIO_BITRATE_K", "128"))
