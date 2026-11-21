"""Leitura do arquivo de configuração (config.toml)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

CAMINHO_PADRAO = Path("config.toml")


@dataclass(frozen=True)
class Precos:
    """Tabela de preços. Dinheiro em centavos (inteiros), para não ter erro de arredondamento."""

    tolerancia_minutos: int
    valor_base: int
    horas_base: int
    valor_hora_adicional: int
    diaria_maxima: int


@dataclass(frozen=True)
class Config:
    vagas: int
    precos: Precos


def _centavos(reais: float) -> int:
    return round(reais * 100)


def carregar(caminho: Path | str = CAMINHO_PADRAO) -> Config:
    with open(caminho, "rb") as arquivo:
        dados = tomllib.load(arquivo)
    p = dados["precos"]
    return Config(
        vagas=dados["estacionamento"]["vagas"],
        precos=Precos(
            tolerancia_minutos=p["tolerancia_minutos"],
            valor_base=_centavos(p["valor_base"]),
            horas_base=p["horas_base"],
            valor_hora_adicional=_centavos(p["valor_hora_adicional"]),
            diaria_maxima=_centavos(p["diaria_maxima"]),
        ),
    )
