import pytest

from leitor.banco import AVULSO, BLOQUEADO, MENSALISTA
from leitor.config import Precos
from leitor.regras import ALERTA_BLOQUEADO, ALERTA_LOTADO, LIBERADO, calcular_valor, decidir_entrada, formatar_reais

# Tabela do config.toml: 15 min grátis; R$ 10 até 3 h; R$ 3 por hora a mais; diária de R$ 40.
PRECOS = Precos(tolerancia_minutos=15, valor_base=1000, horas_base=3, valor_hora_adicional=300, diaria_maxima=4000)


@pytest.mark.parametrize(
    "minutos, esperado",
    [
        (5, 0),  # dentro da tolerância
        (15, 0),  # exatamente na tolerância
        (16, 1000),  # passou da tolerância: valor base
        (180, 1000),  # 3 h cheias: ainda o valor base
        (181, 1300),  # 3 h e 1 min: hora adicional começada conta inteira
        (300, 1600),  # 5 h: base + 2 adicionais
        (600, 3100),  # 10 h: base + 7 adicionais
        (720, 3700),  # 12 h: base + 9 adicionais
        (780, 4000),  # 13 h: base + 10 adicionais = R$ 40, chega na diária
        (1000, 4000),  # 16 h: limitado pela diária
        (1440, 4000),  # 24 h: uma diária
        (1440 + 60, 5000),  # 25 h: uma diária + valor base do segundo dia
    ],
)
def test_valor_avulso(minutos, esperado):
    assert calcular_valor(minutos, AVULSO, PRECOS) == esperado


def test_mensalista_nao_paga():
    assert calcular_valor(600, MENSALISTA, PRECOS) == 0


def test_bloqueado_gera_alerta():
    assert decidir_entrada("BZR7297", BLOQUEADO, ocupadas=0, vagas=20).situacao == ALERTA_BLOQUEADO


def test_bloqueado_tem_prioridade_sobre_lotado():
    assert decidir_entrada("BZR7297", BLOQUEADO, ocupadas=20, vagas=20).situacao == ALERTA_BLOQUEADO


def test_avulso_com_estacionamento_lotado_gera_alerta():
    assert decidir_entrada("EPY4372", AVULSO, ocupadas=20, vagas=20).situacao == ALERTA_LOTADO


def test_avulso_com_vaga_e_liberado():
    assert decidir_entrada("EPY4372", AVULSO, ocupadas=5, vagas=20).situacao == LIBERADO


def test_mensalista_entra_mesmo_lotado():
    assert decidir_entrada("GAM4069", MENSALISTA, ocupadas=20, vagas=20).situacao == LIBERADO


@pytest.mark.parametrize("centavos, texto", [(0, "R$ 0,00"), (1050, "R$ 10,50"), (123456, "R$ 1.234,56")])
def test_formatar_reais(centavos, texto):
    assert formatar_reais(centavos) == texto
