"""Demonstração do sistema com um vídeo comum (sem câmera de estacionamento).

O mesmo trecho de vídeo é usado duas vezes:
1. como câmera da ENTRADA: os carros chegam e ocupam vagas;
2. depois de "passar o tempo", como câmera da SAÍDA: os mesmos carros vão embora e pagam.

Para o pátio não começar vazio, o banco da demonstração é preenchido com carros já estacionados
e alguns dias de histórico (para o faturamento e os relatórios terem o que mostrar).
As placas desse histórico são inventadas, geradas ao acaso no formato brasileiro.
"""

import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from leitor import config as cfg
from leitor.banco import BLOQUEADO, FORMATO_DATA, MENSALISTA, Banco
from leitor.regras import calcular_valor
from leitor.relogio import RELOGIO

CAMINHO_BANCO = Path("data") / "demo.db"

# Placas que aparecem no vídeo de teste e precisam de cadastro para mostrar os alertas.
CADASTROS_DO_VIDEO = [
    ("GAM4069", "Ana Souza", MENSALISTA, "mensalista desde 2024"),
    ("BZR7297", "Carlos Lima", BLOQUEADO, "inadimplente"),
]

# Horários de chegada mais comuns (para o relatório mostrar picos): hora -> peso.
PESOS_HORA = {7: 3, 8: 8, 9: 6, 10: 3, 11: 4, 12: 7, 13: 6, 14: 3, 15: 3, 16: 4, 17: 6, 18: 8, 19: 5, 20: 2}


@dataclass
class ConfigDemo:
    video: str
    segundos: float = 30
    """Quanto do vídeo usar em cada fase."""
    horas: float = 2
    """Quanto tempo "passa" entre a entrada e a saída."""
    aceleracao: float = 300
    """Na fase de saída, cada segundo real vale isto em segundos (300 = 1 s vira 5 min)."""
    carros_dentro: int = 13
    """Carros já estacionados quando a demonstração começa. Com 13, o último carro do vídeo encontra o pátio lotado."""


def _placa_inventada(sorteio: random.Random) -> str:
    letras = "".join(sorteio.choices(string.ascii_uppercase, k=3))
    if sorteio.random() < 0.5:
        return f"{letras}{sorteio.randint(0, 9999):04d}"  # antigo
    return f"{letras}{sorteio.randint(0, 9)}{sorteio.choice(string.ascii_uppercase)}{sorteio.randint(0, 99):02d}"


def _texto(momento: datetime) -> str:
    return momento.strftime(FORMATO_DATA)


def semear(banco: Banco, config: cfg.Config, carros_dentro: int, semente: int = 42) -> None:
    """Preenche um banco vazio com cadastros, histórico de 7 dias e carros estacionados agora."""
    sorteio = random.Random(semente)
    agora = RELOGIO.agora().replace(microsecond=0)

    for placa, nome, tipo, observacao in CADASTROS_DO_VIDEO:
        banco.cadastrar(placa, nome, tipo, observacao)
    mensalistas = [_placa_inventada(sorteio) for _ in range(4)]
    for i, placa in enumerate(mensalistas):
        banco.cadastrar(placa, f"Mensalista {i + 1}", MENSALISTA)

    clientes = [_placa_inventada(sorteio) for _ in range(60)]
    frequentes = clientes[:6]  # alguns voltam quase todo dia

    # Histórico: cada visita entra e sai, com o valor calculado pelas regras de verdade.
    horas, pesos = list(PESOS_HORA), list(PESOS_HORA.values())
    for dias_atras in range(6, -1, -1):
        dia = (agora - timedelta(days=dias_atras)).replace(hour=0, minute=0, second=0)
        # dict.fromkeys tira repetidos mantendo a ordem: cada placa visita no máximo uma vez por dia.
        visitantes = dict.fromkeys(sorteio.sample(clientes, 22) + sorteio.sample(frequentes, 4) + mensalistas[:3])
        for placa in visitantes:
            entrada = dia + timedelta(hours=sorteio.choices(horas, pesos)[0], minutes=sorteio.randint(0, 59))
            tipo = MENSALISTA if placa in mensalistas else "avulso"
            minutos = sorteio.randint(480, 600) if tipo == MENSALISTA else sorteio.choice(
                [sorteio.randint(5, 14), sorteio.randint(30, 180), sorteio.randint(180, 420)]
            )
            saida = entrada + timedelta(minutes=minutos)
            if saida >= agora:
                continue  # ainda não aconteceu
            banco.registrar_entrada(placa, _texto(entrada))
            banco.registrar_saida(placa, _texto(saida), calcular_valor(minutos, tipo, config.precos))

    # Carros estacionados agora, em vagas espalhadas pelo pátio.
    ja_dentro = {a.placa for a in banco.dentro_agora()}
    candidatos = [p for p in clientes + mensalistas[3:] if p not in ja_dentro]
    vagas = sorteio.sample(range(1, config.vagas + 1), min(carros_dentro, config.vagas))
    for placa, vaga in zip(sorteio.sample(candidatos, len(vagas)), vagas):
        entrada = agora - timedelta(minutes=sorteio.randint(20, 300))
        banco.registrar_entrada(placa, _texto(entrada), vaga=vaga)


def preparar_banco(caminho: Path | str, config: cfg.Config, carros_dentro: int) -> None:
    """Recria do zero o banco da demonstração."""
    caminho = Path(caminho)
    caminho.unlink(missing_ok=True)
    banco = Banco(caminho)
    try:
        semear(banco, config, carros_dentro)
    finally:
        banco.fechar()
