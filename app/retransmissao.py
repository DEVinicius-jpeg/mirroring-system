"""Retransmissão: captura a live do criador e envia para a Shopee por RTMP.

Desenho:
  - Um processo FFmpeg de SAÍDA fica conectado à Shopee do início ao fim.
  - "Alimentadores" se revezam escrevendo vídeo já codificado nele:
      * live   -> Streamlink | FFmpeg (recodifica para o padrão fixo)
      * espera -> FFmpeg gerando a tela de espera com áudio mudo
  - Quando a live cai, entra a tela de espera sem derrubar a conexão com a
    Shopee. Se a live não voltar dentro do limite, a retransmissão encerra.

A chave da Shopee vive só na memória deste processo: não vai para o banco,
para arquivos nem para os registros.
"""
import logging
import os
import select
import subprocess
import threading
import time
from collections import deque

from . import config, db, fonte

log = logging.getLogger("retransmissao")

# Um trecho de live precisa durar isto para zerar o contador de espera.
LIVE_ESTAVEL_SEG = 30
# Folga somada ao relógio do vídeo a cada troca de alimentador.
MARGEM_TROCA_SEG = 2


def _args_codificacao() -> list[str]:
    w, h, fps = config.VIDEO_LARGURA, config.VIDEO_ALTURA, config.VIDEO_FPS
    vb = config.VIDEO_BITRATE_K
    filtro = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )
    return [
        "-vf", filtro,
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
        "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-g", str(fps * 2), "-keyint_min", str(fps * 2), "-sc_threshold", "0",
        "-b:v", f"{vb}k", "-maxrate", f"{vb}k", "-bufsize", f"{vb * 2}k",
        "-c:a", "aac", "-b:a", f"{config.AUDIO_BITRATE_K}k", "-ar", "44100", "-ac", "2",
    ]


def montar_destino(url: str, chave: str) -> str:
    url, chave = url.strip(), chave.strip()
    if not chave:
        return url
    return url.rstrip("/") + "/" + chave


class Retransmissor:
    """Controla uma retransmissão por vez."""

    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self.estado = "parado"          # parado | conectando | ao_vivo | espera
        self.criador: dict | None = None
        self.inicio: float | None = None
        self.quedas = 0
        self.segundos_espera = 0.0
        self.espera_desde: float | None = None
        self.ultimo_aviso: dict | None = None   # mostrado no painel até ser dispensado
        self._erros_saida: deque[str] = deque(maxlen=8)

    # ---------- controle ----------

    @property
    def ativo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self, criador: dict, destino: str) -> None:
        with self._trava:
            if self.ativo:
                raise RuntimeError("Já existe uma retransmissão em andamento.")
            self._parar.clear()
            self.criador = criador
            self.estado = "conectando"
            self.inicio = time.time()
            self.quedas = 0
            self.segundos_espera = 0.0
            self.espera_desde = None
            self.ultimo_aviso = None
            self._erros_saida.clear()
            self._thread = threading.Thread(
                target=self._executar, args=(criador, destino), daemon=True, name="retransmissao"
            )
            self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=15)

    def dispensar_aviso(self) -> None:
        self.ultimo_aviso = None

    def resumo(self) -> dict:
        espera_atual = time.time() - self.espera_desde if self.espera_desde else 0
        return {
            "estado": self.estado,
            "criador": {"usuario": self.criador["usuario"], "nome": self.criador["nome"]}
            if self.criador and self.ativo else None,
            "inicio": self.inicio if self.ativo else None,
            "quedas": self.quedas,
            "segundos_espera": int(self.segundos_espera + espera_atual),
            "espera_atual": int(espera_atual),
            "espera_max": config.ESPERA_MAX_SEG,
            "aviso": self.ultimo_aviso,
        }

    # ---------- execução ----------

    def _executar(self, criador: dict, destino: str) -> None:
        usuario = criador["usuario"]
        sid = db.abrir_sessao(usuario, criador["nome"])
        resultado = "encerrada pelo operador"
        alerta = False
        t0 = time.monotonic()
        trocas = 0
        saida = None
        try:
            saida = subprocess.Popen(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-fflags", "+genpts", "-f", "mpegts", "-i", "pipe:0",
                    "-c", "copy", "-bsf:a", "aac_adtstoasc",
                    "-f", "flv", destino,
                ],
                stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            threading.Thread(
                target=self._ler_erros, args=(saida, destino), daemon=True
            ).start()

            espera_corrida = 0.0   # espera acumulada sem um trecho estável de live
            while not self._parar.is_set():
                # ----- tela de espera até a live aparecer -----
                self.estado = "espera" if trocas else "conectando"
                self.espera_desde = time.time()
                desloc = time.monotonic() - t0 + trocas * MARGEM_TROCA_SEG
                trocas += 1
                motivo = self._espera(saida, usuario, desloc, config.ESPERA_MAX_SEG - espera_corrida)
                durou = time.time() - self.espera_desde
                self.segundos_espera += durou
                espera_corrida += durou
                self.espera_desde = None
                if motivo == "saida":
                    resultado, alerta = "erro no envio para a Shopee", True
                    break
                if motivo == "tempo":
                    resultado, alerta = "live do criador não voltou; encerrada", True
                    break
                if motivo == "parar":
                    break

                # ----- live -----
                self.estado = "ao_vivo"
                desloc = time.monotonic() - t0 + trocas * MARGEM_TROCA_SEG
                trocas += 1
                ini_live = time.monotonic()
                motivo, teve_dados = self._live(saida, usuario, desloc)
                if motivo == "saida":
                    resultado, alerta = "erro no envio para a Shopee", True
                    break
                if motivo == "parar":
                    break
                if teve_dados:
                    self.quedas += 1
                if time.monotonic() - ini_live >= LIVE_ESTAVEL_SEG:
                    espera_corrida = 0.0
                log.warning("live de @%s caiu (%s); entrando em espera", usuario, motivo)
        except Exception as e:
            log.exception("falha na retransmissão")
            resultado, alerta = f"erro interno: {type(e).__name__}", True
        finally:
            if saida:
                self._encerrar(saida, gentil=True)
            self.estado = "parado"
            self.espera_desde = None
            db.fechar_sessao(sid, self.quedas, int(self.segundos_espera), resultado)
            if alerta:
                detalhe = " | ".join(self._erros_saida) if "Shopee" in resultado else ""
                self.ultimo_aviso = {
                    "quando": time.time(),
                    "texto": f"Retransmissão de @{usuario}: {resultado}.",
                    "detalhe": detalhe,
                }
            log.info("retransmissão de @%s finalizada: %s", usuario, resultado)

    def _espera(self, saida, usuario: str, desloc: float, limite: float) -> str:
        """Mostra a tela de espera. Retorna: 'voltou' | 'tempo' | 'parar' | 'saida'."""
        if limite <= 0:
            return "tempo"
        voltou = threading.Event()
        fim = threading.Event()

        def vigiar():
            while not fim.is_set():
                if fonte.esta_ao_vivo(usuario):
                    voltou.set()
                    return
                fim.wait(config.ESPERA_VERIFICA_SEG)

        threading.Thread(target=vigiar, daemon=True).start()
        proc = subprocess.Popen(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-re", "-loop", "1", "-framerate", str(config.VIDEO_FPS), "-i", str(config.TELA_ESPERA),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                *_args_codificacao(),
                "-output_ts_offset", f"{desloc:.3f}", "-f", "mpegts", "pipe:1",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        prazo = time.monotonic() + limite
        try:
            motivo, _ = self._bombear(
                proc, saida,
                lambda: "voltou" if voltou.is_set() else ("tempo" if time.monotonic() > prazo else None),
            )
            return "tempo" if motivo in ("fim", "silencio") else motivo
        finally:
            fim.set()
            self._encerrar(proc)

    def _live(self, saida, usuario: str, desloc: float) -> tuple[str, bool]:
        """Repassa a live. Retorna (motivo, teve_dados); motivo: 'fim' | 'silencio' | 'parar' | 'saida'."""
        captura = subprocess.Popen(
            fonte.comando_captura(usuario), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        proc = subprocess.Popen(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                *_args_codificacao(),
                "-output_ts_offset", f"{desloc:.3f}", "-f", "mpegts", "pipe:1",
            ],
            stdin=captura.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        captura.stdout.close()
        try:
            return self._bombear(proc, saida, lambda: None)
        finally:
            self._encerrar(captura)
            self._encerrar(proc)

    def _bombear(self, proc, saida, condicao) -> tuple[str, bool]:
        """Copia a saída de `proc` para o FFmpeg de saída até algo interromper."""
        fd = proc.stdout.fileno()
        ultimo = time.monotonic()
        teve_dados = False
        while True:
            if self._parar.is_set():
                return "parar", teve_dados
            if saida.poll() is not None:
                return "saida", teve_dados
            m = condicao()
            if m:
                return m, teve_dados
            pronto, _, _ = select.select([fd], [], [], 0.5)
            if not pronto:
                if time.monotonic() - ultimo > config.FONTE_SILENCIO_SEG:
                    return "silencio", teve_dados
                continue
            dados = os.read(fd, 65536)
            if not dados:
                return "fim", teve_dados
            ultimo = time.monotonic()
            teve_dados = True
            try:
                saida.stdin.write(dados)
                saida.stdin.flush()
            except (BrokenPipeError, OSError):
                return "saida", teve_dados

    def _ler_erros(self, saida, destino: str) -> None:
        for linha in saida.stderr:
            texto = linha.decode("utf-8", "replace").strip()
            if texto:
                # A chave nunca aparece em registro nem no painel.
                self._erros_saida.append(texto.replace(destino, "[destino]"))

    @staticmethod
    def _encerrar(proc, gentil: bool = False) -> None:
        try:
            if gentil and proc.stdin:
                try:
                    proc.stdin.close()
                    proc.wait(timeout=5)
                    return
                except Exception:
                    pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception:
            log.exception("erro ao encerrar processo")
        finally:
            for canal in (proc.stdout, proc.stdin):
                try:
                    if canal:
                        canal.close()
                except Exception:
                    pass


retransmissor = Retransmissor()
