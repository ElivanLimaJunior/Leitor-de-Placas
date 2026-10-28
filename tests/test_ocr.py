from leitor.ocr import interpretar


def test_leitura_correta_vira_placa():
    leitura = interpretar("EPY4372", [1.0] * 7)
    assert leitura.placa == "EPY4372"
    assert leitura.formato == "antigo"


def test_leitura_mercosul():
    leitura = interpretar("BRA2E19", [1.0] * 7)
    assert leitura.placa == "BRA2E19"
    assert leitura.formato == "mercosul"


def test_leitura_com_confusao_e_corrigida():
    # O OCR trocou o "G" por "6" numa posição que só aceita letra.
    leitura = interpretar("6AM4069", [1.0] * 7)
    assert leitura.texto_bruto == "6AM4069"
    assert leitura.placa == "GAM4069"


def test_quinta_posicao_nao_e_corrigida():
    # Na 5ª posição, "O" (Mercosul) e "0" (antigo) são ambos válidos: o OCR decide, não a regra.
    leitura = interpretar("GAM4O69", [1.0] * 7)
    assert leitura.placa == "GAM4O69"
    assert leitura.formato == "mercosul"


def test_leitura_incompleta_nao_vira_placa():
    # Placa cortada na borda da imagem: só parte dos caracteres foi lida.
    leitura = interpretar("5721", [0.83, 0.98, 0.99, 1.0])
    assert leitura.placa is None
    assert leitura.formato is None


def test_confianca_e_a_do_caractere_mais_fraco():
    leitura = interpretar("FWK2707", [0.99, 0.84, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert leitura.confianca == 0.84


def test_confianca_sem_caracteres_e_zero():
    assert interpretar("", []).confianca == 0.0
