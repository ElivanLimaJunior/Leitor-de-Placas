"""Relógio do sistema.

Em operação normal é a hora do computador. Na demonstração, ele pode adiantar e correr mais
rápido, para simular as horas que os carros passam estacionados sem esperar de verdade.
"""

import threading
import time
from datetime import datetime, timedelta


class Relogio:
    def __init__(self):
        self._trava = threading.Lock()
        self._base_real = time.monotonic()
        self._base_simulada = datetime.now()
        self._velocidade = 1.0

    def agora(self) -> datetime:
        with self._trava:
            decorrido = time.monotonic() - self._base_real
            return self._base_simulada + timedelta(seconds=decorrido * self._velocidade)

    @property
    def velocidade(self) -> float:
        return self._velocidade

    def ajustar(self, velocidade: float | None = None, avancar: timedelta = timedelta()) -> None:
        """Muda a velocidade (1 = tempo real) e/ou adianta o relógio, sem pular para trás."""
        atual = self.agora()
        with self._trava:
            self._base_real = time.monotonic()
            self._base_simulada = atual + avancar
            if velocidade is not None:
                self._velocidade = velocidade

    def reiniciar(self) -> None:
        """Volta para a hora do computador, em tempo real."""
        with self._trava:
            self._base_real = time.monotonic()
            self._base_simulada = datetime.now()
            self._velocidade = 1.0


RELOGIO = Relogio()
