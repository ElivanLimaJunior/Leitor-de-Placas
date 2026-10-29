import pytest

from leitor.banco import AVULSO, BLOQUEADO, MENSALISTA, Banco


@pytest.fixture
def banco():
    b = Banco(":memory:")
    yield b
    b.fechar()


def test_quem_esta_dentro_agora(banco):
    banco.registrar_entrada("EPY4372", "2026-10-28 08:00:00")
    banco.registrar_entrada("GAM4069", "2026-10-28 08:10:00")
    banco.registrar_saida("EPY4372", "2026-10-28 09:00:00")
    dentro = banco.dentro_agora(referencia="2026-10-28 10:00:00")
    assert [a.placa for a in dentro] == ["GAM4069"]
    assert dentro[0].minutos == pytest.approx(110)  # 08:10 até 10:00


def test_quanto_tempo_o_carro_ficou(banco):
    banco.registrar_entrada("EPY4372", "2026-10-28 08:00:00")
    banco.registrar_saida("EPY4372", "2026-10-28 09:30:00")
    banco.registrar_entrada("EPY4372", "2026-10-29 14:00:00")
    banco.registrar_saida("EPY4372", "2026-10-29 14:45:00")
    historico = banco.historico("EPY4372")
    assert [round(a.minutos) for a in historico] == [90, 45]


def test_placa_e_normalizada(banco):
    banco.registrar_entrada("epy-4372", "2026-10-28 08:00:00")
    assert banco.historico("EPY 4372")[0].placa == "EPY4372"


def test_placa_invalida_e_recusada(banco):
    with pytest.raises(ValueError):
        banco.registrar_entrada("XYZ", "2026-10-28 08:00:00")


def test_entrada_repetida_e_ignorada(banco):
    assert banco.registrar_entrada("EPY4372", "2026-10-28 08:00:00") is not None
    assert banco.registrar_entrada("EPY4372", "2026-10-28 08:05:00") is None
    assert len(banco.historico("EPY4372")) == 1


def test_saida_sem_entrada_e_ignorada(banco):
    assert banco.registrar_saida("EPY4372", "2026-10-28 08:00:00") is None


def test_saida_antes_da_entrada_e_recusada(banco):
    banco.registrar_entrada("EPY4372", "2026-10-28 08:00:00")
    with pytest.raises(Exception):
        banco.registrar_saida("EPY4372", "2026-10-28 07:00:00")


def test_tipo_vem_do_cadastro(banco):
    banco.cadastrar("GAM4069", "Ana", MENSALISTA)
    banco.cadastrar("BZR7297", "Carlos", BLOQUEADO, "inadimplente")
    assert banco.tipo("GAM4069") == MENSALISTA
    assert banco.tipo("BZR7297") == BLOQUEADO
    assert banco.tipo("EPY4372") == AVULSO


def test_acesso_mostra_tipo_e_proprietario(banco):
    banco.cadastrar("GAM4069", "Ana", MENSALISTA)
    banco.registrar_entrada("GAM4069", "2026-10-28 08:00:00")
    banco.registrar_entrada("EPY4372", "2026-10-28 08:01:00")
    a, b = banco.dentro_agora(referencia="2026-10-28 09:00:00")
    assert (a.tipo, a.proprietario) == (MENSALISTA, "Ana")
    assert (b.tipo, b.proprietario) == (AVULSO, None)


def test_cadastrar_de_novo_atualiza(banco):
    banco.cadastrar("GAM4069", "Ana", MENSALISTA)
    banco.cadastrar("GAM4069", "Ana", BLOQUEADO, "mensalidade atrasada")
    assert banco.tipo("GAM4069") == BLOQUEADO


def test_acessos_do_dia(banco):
    banco.registrar_entrada("EPY4372", "2026-10-28 23:50:00")
    banco.registrar_saida("EPY4372", "2026-10-29 00:20:00")
    banco.registrar_entrada("GAM4069", "2026-10-29 08:00:00")
    assert [a.placa for a in banco.acessos_do_dia("2026-10-29")] == ["GAM4069"]
