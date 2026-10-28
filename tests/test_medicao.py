from leitor.medicao import LeituraColetada, avaliar

GABARITO = {"EPY4372", "GAM4069", "FWK2707"}

LEITURAS = [
    LeituraColetada(quadro=0, conf_deteccao=0.8, texto_bruto="EPY4372", placa="EPY4372", conf_leitura=1.0),
    LeituraColetada(quadro=10, conf_deteccao=0.8, texto_bruto="GAM4069", placa="GAM4069", conf_leitura=0.9),
    # Erro do OCR: trocou W por V, e com confiança baixa.
    LeituraColetada(quadro=20, conf_deteccao=0.3, texto_bruto="FVK2707", placa="FVK2707", conf_leitura=0.5),
    # Placa cortada: não formou placa válida, não conta como aceita.
    LeituraColetada(quadro=30, conf_deteccao=0.7, texto_bruto="5721", placa=None, conf_leitura=0.8),
]


def test_sem_limite_aceita_todas_as_validas():
    r = avaliar(LEITURAS, GABARITO, limite_leitura=0.0)
    assert r.aceitas == 3
    assert r.corretas == 2
    assert r.erradas == {"FVK2707": 1}
    assert r.encontradas == {"EPY4372", "GAM4069"}
    assert r.perdidas == {"FWK2707"}


def test_limite_de_leitura_corta_o_falso_positivo():
    r = avaliar(LEITURAS, GABARITO, limite_leitura=0.6)
    assert r.aceitas == 2
    assert not r.erradas
    assert r.precisao == 1.0


def test_limite_de_deteccao_tambem_filtra():
    r = avaliar(LEITURAS, GABARITO, limite_leitura=0.0, limite_deteccao=0.5)
    assert r.aceitas == 2
    assert not r.erradas


def test_limite_alto_demais_perde_placas():
    r = avaliar(LEITURAS, GABARITO, limite_leitura=0.95)
    assert r.encontradas == {"EPY4372"}
    assert r.perdidas == {"GAM4069", "FWK2707"}


def test_precisao_sem_leituras_aceitas_e_zero():
    assert avaliar([], GABARITO, limite_leitura=0.5).precisao == 0.0
