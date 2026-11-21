"""O motor do leitor: quadro -> detecção -> OCR -> rastreamento -> regras do estacionamento.

Usado tanto pela linha de comando (leitor.processar) quanto pelo painel web (leitor.web).
"""

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import cv2
import numpy as np

from leitor.banco import FORMATO_DATA, agora
from leitor.deteccao import DetectorDePlacas, recortar
from leitor.estacionamento import Estacionamento
from leitor.ocr import VERMELHO, LeitorDePlacas
from leitor.rastreamento import Observacao, Rastreador, Registro
from leitor.video import desenhar_caixa

# Quanto tempo uma placa pode sumir (encoberta, fora do quadro) antes de o veículo ser dado como saído.
AUSENCIA_MAXIMA_S = 1.0
# Se a mesma placa voltar até este tempo depois, é a mesma passagem.
JANELA_JUNCAO_S = 5.0

ENTRADA = "entrada"
SAIDA = "saida"


@dataclass
class Evento:
    """Algo que a portaria precisa ver: uma entrada (com a decisão) ou uma saída (com o valor)."""

    hora: str
    placa: str
    situacao: str
    """liberado, bloqueado, lotado, saida, ou registro (quando não há banco)."""
    tipo: str
    """mensalista, bloqueado ou avulso."""
    mensagem: str

    def como_dict(self) -> dict:
        return asdict(self)


class Motor:
    def __init__(
        self,
        fps: float,
        estacionamento: Estacionamento | None = None,
        camera: str = ENTRADA,
        inicio: datetime | None = None,
        eventos: deque | None = None,
    ):
        """
        fps: quadros por segundo da fonte, para converter número do quadro em tempo.
        estacionamento: se None, só reconhece as placas, sem gravar nada.
        camera: se a câmera filma a entrada ou a saída.
        inicio: hora em que o vídeo começou. None = câmera ao vivo, usa a hora do sistema em cada registro.
        eventos: lista compartilhada onde os eventos novos entram (o painel web passa a dele).
        """
        self.fps = fps
        self.estacionamento = estacionamento
        self.camera = camera
        self.inicio = inicio
        self.detector = DetectorDePlacas()
        self.leitor = LeitorDePlacas()
        self.rastreador = Rastreador(
            ausencia_maxima=int(AUSENCIA_MAXIMA_S * fps), janela_juncao=int(JANELA_JUNCAO_S * fps)
        )
        self.eventos: deque[Evento] = eventos if eventos is not None else deque(maxlen=50)
        """Eventos mais recentes primeiro."""

    def processar(self, numero: int, quadro: np.ndarray) -> list[Evento]:
        """Processa um quadro, desenha as placas nele e devolve os eventos novos."""
        observacoes = []
        for d in self.detector.detectar(quadro):
            leitura = self.leitor.ler(recortar(quadro, d))
            observacoes.append(Observacao(d.x1, d.y1, d.x2, d.y2, leitura.placa, leitura.confianca))
        novos = self._tratar(self.rastreador.atualizar(numero, observacoes))
        self._desenhar(numero, quadro)
        return novos

    def finalizar(self) -> list[Evento]:
        """Fim do vídeo: os veículos ainda na tela viram registros."""
        return self._tratar(self.rastreador.finalizar())

    def _hora(self, registro: Registro) -> str:
        if self.inicio is None:
            return agora()
        return (self.inicio + timedelta(seconds=registro.primeiro_quadro / self.fps)).strftime(FORMATO_DATA)

    def _tratar(self, registros: list[Registro]) -> list[Evento]:
        novos = []
        for r in registros:
            evento = self._evento(r)
            if evento:
                self.eventos.appendleft(evento)
                novos.append(evento)
        return novos

    def _evento(self, r: Registro) -> Evento | None:
        hora = self._hora(r)
        if self.estacionamento is None:
            return Evento(hora, r.placa, "registro", "avulso", f"{r.placa}: veículo registrado.")

        tipo = self.estacionamento.banco.tipo(r.placa)
        if self.camera == ENTRADA:
            # Confiança do registro: que fração dos votos a placa vencedora levou (1.0 = leitura unânime).
            confianca = r.votos[r.placa] / sum(r.votos.values())
            decisao = self.estacionamento.entrada(r.placa, hora, confianca)
            if decisao is None:
                return None  # já estava dentro: leitura repetida
            return Evento(hora, r.placa, decisao.situacao, tipo, decisao.mensagem)

        saida = self.estacionamento.saida(r.placa, hora)
        if saida is None:
            return None  # saída sem entrada registrada
        return Evento(hora, r.placa, SAIDA, tipo, saida.mensagem)

    def _desenhar(self, numero: int, quadro: np.ndarray) -> None:
        for t in self.rastreador.trilhas:
            if t.ultimo_quadro != numero:
                continue  # veículo não visto neste quadro
            o = t.ultima
            if t.placa:
                desenhar_caixa(quadro, o.x1, o.y1, o.x2, o.y2, f"#{t.numero} {t.placa}")
            else:
                cv2.rectangle(quadro, (o.x1, o.y1), (o.x2, o.y2), VERMELHO, 2)
