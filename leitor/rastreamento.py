"""Etapa 6: um carro = um registro.

O mesmo carro aparece em dezenas de quadros. O rastreador liga a placa de um quadro à do quadro
seguinte (pela sobreposição das caixas ou, se não houver, pela distância entre os centros), dá um
número a cada veículo enquanto ele está na tela e, quando ele some, escolhe a leitura mais votada.

Este módulo não depende dos modelos: recebe caixas e leituras prontas, e por isso é fácil de testar.
"""

from collections import defaultdict
from dataclasses import dataclass, field

# Limites escolhidos na etapa 5, medindo contra o gabarito (ver README).
CONFIANCA_MINIMA_LEITURA = 0.80
LARGURA_MINIMA_PLACA = 60

# Dois centros a menos de 1,5 largura de placa de distância são considerados a mesma placa.
DISTANCIA_MAXIMA = 1.5


@dataclass
class Observacao:
    """Uma placa vista num quadro: caixa e, se o OCR formou placa válida, a leitura."""

    x1: int
    y1: int
    x2: int
    y2: int
    placa: str | None = None
    confianca: float = 0.0

    @property
    def largura(self) -> int:
        return self.x2 - self.x1

    @property
    def centro(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2

    @property
    def confiavel(self) -> bool:
        """Só leituras que passam nos limites da etapa 5 viram voto."""
        return (
            self.placa is not None
            and self.confianca >= CONFIANCA_MINIMA_LEITURA
            and self.largura >= LARGURA_MINIMA_PLACA
        )


def iou(a: Observacao, b: Observacao) -> float:
    """Sobreposição entre duas caixas: área da interseção dividida pela área da união (0 a 1)."""
    larg = min(a.x2, b.x2) - max(a.x1, b.x1)
    alt = min(a.y2, b.y2) - max(a.y1, b.y1)
    if larg <= 0 or alt <= 0:
        return 0.0
    intersecao = larg * alt
    uniao = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - intersecao
    return intersecao / uniao


def distancia_relativa(a: Observacao, b: Observacao) -> float:
    """Distância entre os centros, medida em larguras de placa (assim vale para perto e longe)."""
    (ax, ay), (bx, by) = a.centro, b.centro
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 / max(a.largura, b.largura, 1)


@dataclass
class Registro:
    """Uma passagem de veículo: a placa escolhida por votação e quando apareceu."""

    placa: str
    primeiro_quadro: int
    ultimo_quadro: int
    votos: dict[str, float]
    """Soma das confianças de cada placa lida. A vencedora é a de maior soma."""


@dataclass
class Trilha:
    """Um veículo sendo acompanhado enquanto está na tela."""

    numero: int
    ultima: Observacao
    primeiro_quadro: int
    ultimo_quadro: int
    votos: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def adicionar(self, quadro: int, obs: Observacao) -> None:
        self.ultima = obs
        self.ultimo_quadro = quadro
        if obs.confiavel:
            # Voto com peso: uma leitura com 99% vale mais que uma com 81%.
            self.votos[obs.placa] += obs.confianca

    @property
    def placa(self) -> str | None:
        """A placa mais votada até agora, ou None se ainda não houve leitura confiável."""
        return max(self.votos, key=self.votos.get) if self.votos else None


class Rastreador:
    def __init__(self, ausencia_maxima: int, janela_juncao: int):
        """
        ausencia_maxima: quantos quadros uma placa pode sumir antes de o veículo ser dado como fora da tela.
        janela_juncao: se a mesma placa reaparecer até esse número de quadros depois, é a mesma passagem
            (por exemplo, outro carro passou na frente) e os registros são juntados.
        """
        self.ausencia_maxima = ausencia_maxima
        self.janela_juncao = janela_juncao
        self.trilhas: list[Trilha] = []
        self.registros: list[Registro] = []
        self._proximo_numero = 1

    def atualizar(self, quadro: int, observacoes: list[Observacao]) -> list[Registro]:
        """Recebe as placas de um quadro. Devolve os registros novos de veículos que saíram da tela."""
        self._associar(quadro, observacoes)
        return self._encerrar(lambda t: quadro - t.ultimo_quadro > self.ausencia_maxima)

    def finalizar(self) -> list[Registro]:
        """Fim do vídeo: encerra todos os veículos ainda na tela."""
        return self._encerrar(lambda t: True)

    def _associar(self, quadro: int, observacoes: list[Observacao]) -> None:
        # Todos os pares possíveis, do mais parecido para o menos: maior sobreposição, depois menor distância.
        pares = []
        for i, trilha in enumerate(self.trilhas):
            for j, obs in enumerate(observacoes):
                sobreposicao = iou(trilha.ultima, obs)
                distancia = distancia_relativa(trilha.ultima, obs)
                if sobreposicao > 0 or distancia <= DISTANCIA_MAXIMA:
                    pares.append((-sobreposicao, distancia, i, j))
        pares.sort()

        trilhas_usadas, obs_usadas = set(), set()
        for _, _, i, j in pares:
            if i in trilhas_usadas or j in obs_usadas:
                continue
            self.trilhas[i].adicionar(quadro, observacoes[j])
            trilhas_usadas.add(i)
            obs_usadas.add(j)

        # Placas que não combinaram com nenhuma trilha são veículos novos.
        for j, obs in enumerate(observacoes):
            if j not in obs_usadas:
                trilha = Trilha(self._proximo_numero, obs, quadro, quadro)
                trilha.adicionar(quadro, obs)
                self.trilhas.append(trilha)
                self._proximo_numero += 1

    def _encerrar(self, saiu) -> list[Registro]:
        novos = []
        for trilha in [t for t in self.trilhas if saiu(t)]:
            self.trilhas.remove(trilha)
            registro = self._registrar(trilha)
            if registro:
                novos.append(registro)
        return novos

    def _registrar(self, trilha: Trilha) -> Registro | None:
        """Transforma a trilha em registro. Sem nenhuma leitura confiável, o veículo é descartado."""
        placa = trilha.placa
        if placa is None:
            return None

        for anterior in reversed(self.registros):
            if anterior.placa == placa and trilha.primeiro_quadro - anterior.ultimo_quadro <= self.janela_juncao:
                anterior.ultimo_quadro = max(anterior.ultimo_quadro, trilha.ultimo_quadro)
                for p, v in trilha.votos.items():
                    anterior.votos[p] = anterior.votos.get(p, 0.0) + v
                return None

        registro = Registro(placa, trilha.primeiro_quadro, trilha.ultimo_quadro, dict(trilha.votos))
        self.registros.append(registro)
        return registro
