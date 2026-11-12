"""Detecção automática: avisa no painel quando um criador autorizado entra ao vivo.

Não inicia nada sozinha. Pode ser ligada e desligada pelo painel.
"""
import logging
import threading
import time

from . import config, db, fonte

log = logging.getLogger("detector")


class Detector:
    def __init__(self) -> None:
        self.ao_vivo: dict[str, bool] = {}
        self.ultima_verificacao: float | None = None
        self._acordar = threading.Event()

    @property
    def ativa(self) -> bool:
        return db.obter_config("deteccao_ativa", "1") == "1"

    def definir(self, ativa: bool) -> None:
        db.definir_config("deteccao_ativa", "1" if ativa else "0")
        if not ativa:
            self.ao_vivo = {}
            self.ultima_verificacao = None
        self._acordar.set()

    def iniciar(self, em_retransmissao) -> None:
        """`em_retransmissao()` devolve o usuário sendo retransmitido agora, ou None."""
        threading.Thread(target=self._laco, args=(em_retransmissao,), daemon=True, name="detector").start()

    def _laco(self, em_retransmissao) -> None:
        while True:
            try:
                if self.ativa:
                    atual = em_retransmissao()
                    novo: dict[str, bool] = {}
                    for c in db.listar_criadores():
                        if not c["autorizado"] or c["usuario"] == atual:
                            continue
                        novo[c["usuario"]] = fonte.esta_ao_vivo(c["usuario"])
                        if not self.ativa:
                            break
                    if self.ativa:
                        self.ao_vivo = novo
                        self.ultima_verificacao = time.time()
            except Exception:
                log.exception("erro na detecção")
            self._acordar.wait(config.DETECCAO_INTERVALO_SEG)
            self._acordar.clear()


detector = Detector()
