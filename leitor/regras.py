"""Etapa 8: regras do negócio do estacionamento.

Funções puras: não acessam banco nem câmera, por isso são fáceis de testar.
"""

import math
from dataclasses import dataclass

from leitor.banco import AVULSO, BLOQUEADO, MENSALISTA
from leitor.config import Precos

MINUTOS_POR_DIA = 24 * 60

LIBERADO = "liberado"
ALERTA_BLOQUEADO = "bloqueado"
ALERTA_LOTADO = "lotado"


def calcular_valor(minutos: float, tipo: str, precos: Precos) -> int:
    """Valor a pagar, em centavos.

    - Mensalista não paga avulso.
    - Até a tolerância, não paga.
    - Depois: valor base cobre as primeiras horas; cada hora (ou fração) a mais soma o adicional.
    - Cada período de 24 horas tem teto na diária máxima.
    """
    if tipo == MENSALISTA or minutos <= precos.tolerancia_minutos:
        return 0

    dias_completos, resto = divmod(minutos, MINUTOS_POR_DIA)
    total = int(dias_completos) * precos.diaria_maxima
    if resto > 0:
        total += _valor_do_periodo(resto, precos)
    return total


def _valor_do_periodo(minutos: float, precos: Precos) -> int:
    """Valor de um período de até 24 horas, já limitado pela diária."""
    horas_iniciadas = math.ceil(minutos / 60)
    horas_extras = max(horas_iniciadas - precos.horas_base, 0)
    valor = precos.valor_base + horas_extras * precos.valor_hora_adicional
    return min(valor, precos.diaria_maxima)


@dataclass
class Decisao:
    situacao: str
    """liberado, bloqueado ou lotado."""
    mensagem: str
    registrada: bool = False
    """Se a entrada foi gravada (carro entrou)."""
    vaga: int | None = None


def decidir_entrada(placa: str, tipo: str, ocupadas: int, vagas: int) -> Decisao:
    """O que mostrar para a portaria quando um carro chega.

    Mensalista tem vaga garantida e entra mesmo com o estacionamento lotado.
    """
    if tipo == BLOQUEADO:
        return Decisao(ALERTA_BLOQUEADO, f"{placa}: veículo BLOQUEADO. Não liberar a entrada.")
    if tipo == AVULSO and ocupadas >= vagas:
        return Decisao(ALERTA_LOTADO, f"{placa}: estacionamento LOTADO ({ocupadas}/{vagas}).")
    if tipo == MENSALISTA:
        return Decisao(LIBERADO, f"{placa}: mensalista, entrada liberada.")
    return Decisao(LIBERADO, f"{placa}: entrada liberada.")


def formatar_reais(centavos: int) -> str:
    reais, cent = divmod(centavos, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{cent:02d}"
