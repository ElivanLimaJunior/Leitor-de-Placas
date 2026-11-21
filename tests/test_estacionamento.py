import pytest

from leitor.banco import BLOQUEADO, MENSALISTA, Banco
from leitor.config import Config, Precos, carregar
from leitor.estacionamento import Estacionamento
from leitor.regras import ALERTA_BLOQUEADO, ALERTA_LOTADO, LIBERADO

PRECOS = Precos(tolerancia_minutos=15, valor_base=1000, horas_base=3, valor_hora_adicional=300, diaria_maxima=4000)


@pytest.fixture
def banco():
    b = Banco(":memory:")
    yield b
    b.fechar()


def estacionamento(banco, vagas=20):
    return Estacionamento(banco, Config(vagas=vagas, precos=PRECOS))


def test_entrada_e_saida_com_valor(banco):
    e = estacionamento(banco)
    assert e.entrada("EPY4372", "2026-10-28 08:00:00").situacao == LIBERADO
    saida = e.saida("EPY4372", "2026-10-28 13:00:00")
    assert saida.valor == 1600  # 5 h
    assert banco.historico("EPY4372")[0].valor == 1600


def test_vagas_livres(banco):
    e = estacionamento(banco, vagas=3)
    e.entrada("EPY4372", "2026-10-28 08:00:00")
    e.entrada("GAM4069", "2026-10-28 08:05:00")
    assert e.vagas_livres() == 1
    e.saida("EPY4372", "2026-10-28 09:00:00")
    assert e.vagas_livres() == 2


def test_alerta_de_lotacao_nao_deixa_entrar(banco):
    e = estacionamento(banco, vagas=2)
    e.entrada("EPY4372", "2026-10-28 08:00:00")
    e.entrada("GAM4069", "2026-10-28 08:05:00")
    decisao = e.entrada("FCG1890", "2026-10-28 08:10:00")
    assert decisao.situacao == ALERTA_LOTADO
    assert not decisao.registrada
    assert banco.acesso_aberto("FCG1890") is None


def test_alerta_de_bloqueado_nao_deixa_entrar(banco):
    banco.cadastrar("BZR7297", "Carlos", BLOQUEADO)
    decisao = estacionamento(banco).entrada("BZR7297", "2026-10-28 08:00:00")
    assert decisao.situacao == ALERTA_BLOQUEADO
    assert not decisao.registrada
    assert banco.acesso_aberto("BZR7297") is None


def test_operador_pode_liberar_mesmo_com_alerta(banco):
    banco.cadastrar("BZR7297", "Carlos", BLOQUEADO)
    decisao = estacionamento(banco).entrada("BZR7297", "2026-10-28 08:00:00", forcar=True)
    assert decisao.situacao == ALERTA_BLOQUEADO
    assert decisao.registrada
    assert banco.acesso_aberto("BZR7297").vaga == 1


def test_cada_carro_ocupa_a_menor_vaga_livre(banco):
    e = estacionamento(banco)
    assert e.entrada("EPY4372", "2026-10-28 08:00:00").vaga == 1
    assert e.entrada("GAM4069", "2026-10-28 08:05:00").vaga == 2
    assert e.entrada("FCG1890", "2026-10-28 08:10:00").vaga == 3
    e.saida("GAM4069", "2026-10-28 09:00:00")
    assert e.entrada("MMI5721", "2026-10-28 09:10:00").vaga == 2  # a vaga liberada é reaproveitada
    assert banco.vagas_ocupadas() == {1, 2, 3}


def test_operador_libera_com_patio_cheio_sem_vaga(banco):
    e = estacionamento(banco, vagas=1)
    e.entrada("EPY4372", "2026-10-28 08:00:00")
    decisao = e.entrada("GAM4069", "2026-10-28 08:05:00", forcar=True)
    assert decisao.registrada
    assert decisao.vaga is None


def test_mensalista_sai_sem_pagar(banco):
    banco.cadastrar("GAM4069", "Ana", MENSALISTA)
    e = estacionamento(banco)
    e.entrada("GAM4069", "2026-10-28 08:00:00")
    assert e.saida("GAM4069", "2026-10-28 18:00:00").valor == 0


def test_leitura_repetida_na_entrada_e_ignorada(banco):
    e = estacionamento(banco)
    e.entrada("EPY4372", "2026-10-28 08:00:00")
    assert e.entrada("EPY4372", "2026-10-28 08:00:30") is None


def test_saida_sem_entrada(banco):
    assert estacionamento(banco).saida("EPY4372", "2026-10-28 08:00:00") is None


def test_relatorios(banco):
    e = estacionamento(banco)
    e.entrada("EPY4372", "2026-10-28 08:10:00")
    e.entrada("GAM4069", "2026-10-28 08:40:00")
    e.entrada("FCG1890", "2026-10-28 14:00:00")
    e.saida("EPY4372", "2026-10-28 09:00:00")  # 50 min: R$ 10
    e.entrada("EPY4372", "2026-10-28 17:00:00")
    e.saida("EPY4372", "2026-10-28 22:00:00")  # 5 h: R$ 16

    assert banco.entradas_por_hora("2026-10-28", "2026-10-28") == {8: 2, 14: 1, 17: 1}
    assert banco.frequentes("2026-10-28", "2026-10-28")[0] == ("EPY4372", "avulso", 2)
    assert banco.faturamento("2026-10-28", "2026-10-28") == 2600


def test_config_do_projeto_carrega():
    config = carregar()
    assert config.vagas == 20
    assert config.precos.valor_base == 1000
