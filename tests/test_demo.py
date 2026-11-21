import time
from datetime import timedelta

import cv2
import numpy as np
import pytest

from leitor.banco import Banco
from leitor.camera import VideoQuadroAQuadro
from leitor.config import carregar
from leitor.demo import semear
from leitor.relogio import Relogio


def test_relogio_em_tempo_real_acompanha_o_computador():
    relogio = Relogio()
    antes = relogio.agora()
    time.sleep(0.05)
    assert timedelta(seconds=0.04) <= relogio.agora() - antes < timedelta(seconds=1)


def test_relogio_adianta_e_acelera():
    relogio = Relogio()
    inicio = relogio.agora()
    relogio.ajustar(velocidade=3600, avancar=timedelta(hours=2))
    time.sleep(0.05)  # 0,05 s reais = 3 min simulados
    decorrido = relogio.agora() - inicio
    assert timedelta(hours=2, minutes=2) < decorrido < timedelta(hours=2, minutes=10)


def test_relogio_nunca_volta_ao_mudar_a_velocidade():
    relogio = Relogio()
    relogio.ajustar(velocidade=1000)
    time.sleep(0.02)
    antes = relogio.agora()
    relogio.ajustar(velocidade=1)
    assert relogio.agora() >= antes


@pytest.fixture
def banco():
    b = Banco(":memory:")
    yield b
    b.fechar()


def test_semear_coloca_carros_em_vagas_e_cria_historico(banco):
    config = carregar()
    semear(banco, config, carros_dentro=13)
    dentro = banco.dentro_agora()
    assert len(dentro) == 13
    assert len(banco.vagas_ocupadas()) == 13  # cada carro numa vaga diferente
    assert all(1 <= a.vaga <= config.vagas for a in dentro)
    assert banco.faturamento("2000-01-01", "2100-01-01") > 0
    assert banco.tipo("BZR7297") == "bloqueado"
    assert banco.tipo("GAM4069") == "mensalista"


def test_semear_e_sempre_igual():
    resultados = []
    for _ in range(2):
        b = Banco(":memory:")
        semear(b, carregar(), carros_dentro=5)
        resultados.append(sorted((a.placa, a.vaga) for a in b.dentro_agora()))
        b.fechar()
    assert resultados[0] == resultados[1]


def test_video_quadro_a_quadro_entrega_um_a_cada_passo(tmp_path):
    caminho = str(tmp_path / "curto.avi")
    gravador = cv2.VideoWriter(caminho, cv2.VideoWriter_fourcc(*"MJPG"), 1000, (32, 32))
    for i in range(10):
        gravador.write(np.full((32, 32, 3), i * 20, dtype=np.uint8))
    gravador.release()

    video = VideoQuadroAQuadro(caminho, passo=3).iniciar()
    numeros = []
    while (lido := video.ler()) is not None:
        numeros.append(lido[0])
    video.parar()
    assert numeros == [2, 5, 8]
    assert video.terminou
