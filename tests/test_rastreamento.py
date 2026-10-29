from leitor.rastreamento import Observacao, Rastreador, iou


def placa(x: int, y: int, texto: str | None = "ABC1234", confianca: float = 0.95, largura: int = 100) -> Observacao:
    return Observacao(x, y, x + largura, y + largura // 3, texto, confianca)


def novo_rastreador() -> Rastreador:
    return Rastreador(ausencia_maxima=10, janela_juncao=50)


def test_iou_de_caixas_iguais_e_1_e_de_caixas_separadas_e_0():
    assert iou(placa(0, 0), placa(0, 0)) == 1.0
    assert iou(placa(0, 0), placa(500, 500)) == 0.0


def test_carro_em_varios_quadros_vira_um_registro():
    r = novo_rastreador()
    for quadro in range(0, 30, 3):
        # A placa anda um pouco a cada quadro, como um carro se aproximando.
        assert r.atualizar(quadro, [placa(100 + quadro, 200 + quadro)]) == []
    registros = r.finalizar()
    assert [x.placa for x in registros] == ["ABC1234"]
    assert registros[0].primeiro_quadro == 0
    assert registros[0].ultimo_quadro == 27


def test_registro_sai_quando_o_carro_some_da_tela():
    r = novo_rastreador()
    r.atualizar(0, [placa(100, 200)])
    assert r.atualizar(5, []) == []  # sumiu há pouco: pode ter sido encoberto
    registros = r.atualizar(20, [])  # sumiu há mais de 10 quadros: saiu
    assert [x.placa for x in registros] == ["ABC1234"]


def test_dois_carros_ao_mesmo_tempo_viram_dois_registros():
    r = novo_rastreador()
    for quadro in range(0, 30, 3):
        r.atualizar(quadro, [placa(100, 200, "ABC1234"), placa(900, 200, "XYZ9876")])
    assert sorted(x.placa for x in r.finalizar()) == ["ABC1234", "XYZ9876"]


def test_votacao_escolhe_a_leitura_mais_votada():
    r = novo_rastreador()
    leituras = ["FWK2707", "FVK2707", "FWK2707", "FWK2707"]
    for quadro, texto in enumerate(leituras):
        r.atualizar(quadro, [placa(100, 200, texto)])
    registro = r.finalizar()[0]
    assert registro.placa == "FWK2707"
    assert set(registro.votos) == {"FWK2707", "FVK2707"}


def test_leituras_nao_confiaveis_nao_votam():
    r = novo_rastreador()
    r.atualizar(0, [placa(100, 200, "FVK2707", largura=50)])  # placa pequena demais
    r.atualizar(1, [placa(100, 200, "FVK2707", confianca=0.5)])  # confiança baixa
    r.atualizar(2, [placa(100, 200, "FWK2707")])
    assert r.finalizar()[0].votos == {"FWK2707": 0.95}


def test_veiculo_sem_leitura_confiavel_nao_gera_registro():
    r = novo_rastreador()
    r.atualizar(0, [placa(100, 200, None)])
    r.atualizar(1, [placa(100, 200, "ABC1234", largura=40)])
    assert r.finalizar() == []


def test_mesma_placa_que_volta_logo_e_juntada():
    # Outro carro passou na frente e a placa sumiu por um tempo.
    r = novo_rastreador()
    r.atualizar(0, [placa(100, 200)])
    r.atualizar(3, [placa(103, 203)])
    r.atualizar(20, [])  # encerra a primeira trilha
    r.atualizar(30, [placa(400, 300)])  # reaparece em outro ponto
    registros = r.finalizar()
    assert registros == []
    assert len(r.registros) == 1
    assert r.registros[0].ultimo_quadro == 30


def test_mesma_placa_muito_depois_e_outra_passagem():
    r = novo_rastreador()
    r.atualizar(0, [placa(100, 200)])
    r.atualizar(20, [])
    r.atualizar(200, [placa(100, 200)])
    r.finalizar()
    assert len(r.registros) == 2
