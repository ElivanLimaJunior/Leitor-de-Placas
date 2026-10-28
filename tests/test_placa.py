import pytest

from leitor.placa import ANTIGO, MERCOSUL, corrigir_placa, formato_placa, normalizar, placa_valida


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("abc-1234", "ABC1234"),
        (" ABC 1D23 ", "ABC1D23"),
        ("abc.1234\n", "ABC1234"),
        ("", ""),
    ],
)
def test_normalizar(texto, esperado):
    assert normalizar(texto) == esperado


@pytest.mark.parametrize(
    "texto, esperado",
    [
        # antigo
        ("ABC1234", ANTIGO),
        ("EVA4011", ANTIGO),
        ("abc-1234", ANTIGO),
        ("ZZZ0000", ANTIGO),
        # Mercosul
        ("ABC1D23", MERCOSUL),
        ("BRA2E19", MERCOSUL),
        ("bra-2e19", MERCOSUL),
        ("RIO2A18", MERCOSUL),
    ],
)
def test_formatos_validos(texto, esperado):
    assert formato_placa(texto) == esperado
    assert placa_valida(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "ABC123",  # curta
        "ABC12345",  # longa
        "AB12345",  # só 2 letras no início
        "ABCD123",  # 4 letras no início
        "1BC1234",  # número onde só pode haver letra
        "ABC12D3",  # letra na posição errada
        "ABCDE12",  # quase tudo letra
        "1234567",  # só números
        "ÁBC1234",  # acento não é letra de placa
    ],
)
def test_textos_invalidos(texto):
    assert formato_placa(texto) is None
    assert not placa_valida(texto)


@pytest.mark.parametrize(
    "lido, esperado",
    [
        # já corretas: nada muda
        ("ABC1234", "ABC1234"),
        ("BRA2E19", "BRA2E19"),
        ("eva-4011", "EVA4011"),
        # número no lugar de letra (posições 0 a 2)
        ("0BC1234", "OBC1234"),
        ("A8C1234", "ABC1234"),
        ("5P01234", "SPO1234"),
        ("EVA40I1", "EVA4011"),
        # letra no lugar de número (posições 3, 5 e 6)
        ("ABCO234", "ABC0234"),
        ("ABC1DZ3", "ABC1D23"),
        ("ABC12S4", "ABC1254"),
        ("BRA2EI9", "BRA2E19"),
        ("RIOZAIB", "RIO2A18"),
        # posição 4 é ambígua: fica como foi lida
        ("ABC1B34", "ABC1B34"),
        ("ABC1834", "ABC1834"),
        ("EVA4O11", "EVA4O11"),  # "O" lido no lugar de "0" vira Mercosul válido: a correção não tem como saber
    ],
)
def test_corrigir_placa(lido, esperado):
    assert corrigir_placa(lido) == esperado


@pytest.mark.parametrize(
    "lido",
    [
        "",
        "ABC123",  # tamanho errado
        "ABC12345",
        "A3C1234",  # "3" não tem letra parecida na tabela
        "ABC1XX4",  # "X" na posição 5 não tem número parecido
        "ABCXYZW",
    ],
)
def test_corrigir_placa_impossivel(lido):
    assert corrigir_placa(lido) is None
