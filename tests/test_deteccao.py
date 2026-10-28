import numpy as np

from leitor.deteccao import Deteccao, recortar


def test_recorta_regiao_da_placa():
    imagem = np.zeros((100, 200, 3), dtype=np.uint8)
    recorte = recortar(imagem, Deteccao(10, 20, 60, 40, 0.9))
    assert recorte.shape == (20, 50, 3)


def test_recorte_limita_caixa_que_passa_da_borda():
    imagem = np.zeros((100, 200, 3), dtype=np.uint8)
    recorte = recortar(imagem, Deteccao(-5, -5, 250, 120, 0.9))
    assert recorte.shape == (100, 200, 3)
