import os
import time

import cv2
import numpy as np

from leitor import camera as cam
from leitor.camera import Camera, carregar_env, esconder_senha


class CapturaFalsa:
    """Câmera de rede de mentira: entrega `quadros` quadros e depois "cai" (read devolve False)."""

    def __init__(self, quadros: int, abre: bool = True):
        self.restantes = quadros
        self.abre = abre
        self.numero = 0

    def isOpened(self):
        return self.abre

    def read(self):
        if self.restantes <= 0:
            return False, None
        self.restantes -= 1
        self.numero += 1
        return True, np.full((4, 4, 3), self.numero, dtype=np.uint8)

    def get(self, propriedade):
        return 0  # câmera de rede: sem fps nem total de quadros

    def release(self):
        pass


def test_esconde_a_senha_do_endereco():
    assert esconder_senha("rtsp://admin:segredo@192.168.0.10:554/stream") == "rtsp://admin:***@192.168.0.10:554/stream"
    assert esconder_senha("videos/teste.mp4") == "videos/teste.mp4"


def test_carrega_env_sem_sobrescrever(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text('# comentário\nCAMERA_URL="rtsp://u:s@ip/1"\nJA_EXISTE=novo\n', encoding="utf-8")
    monkeypatch.delenv("CAMERA_URL", raising=False)
    monkeypatch.setenv("JA_EXISTE", "antigo")
    carregar_env(arquivo)
    assert os.environ["CAMERA_URL"] == "rtsp://u:s@ip/1"
    assert os.environ["JA_EXISTE"] == "antigo"


def test_reconecta_sozinha_quando_a_conexao_cai(monkeypatch):
    monkeypatch.setattr(cam, "ESPERA_INICIAL_S", 0.01)
    # 1ª conexão: 3 quadros e cai. 2ª: não conecta (rede fora). 3ª: volta com mais 3 quadros.
    conexoes = iter([CapturaFalsa(3), CapturaFalsa(0, abre=False), CapturaFalsa(3)])
    camera = Camera("rtsp://camera-falsa", abrir=lambda fonte: next(conexoes, CapturaFalsa(0, abre=False)))
    camera.iniciar()
    try:
        # O 6º quadro (número 5) só existe se a câmera voltou depois da queda.
        ultimo = -1
        while ultimo < 5:
            lido = camera.ler(espera_s=2)
            assert lido is not None, "a câmera não voltou depois da queda"
            assert lido[0] > ultimo  # números continuam crescendo depois da reconexão
            ultimo = lido[0]
        assert camera.reconexoes >= 1
    finally:
        camera.parar()


def _esperar(condicao, segundos=2.0):
    limite = time.monotonic() + segundos
    while not condicao() and time.monotonic() < limite:
        time.sleep(0.01)


def test_entrega_sempre_o_quadro_mais_recente():
    conexoes = iter([CapturaFalsa(50)])
    camera = Camera("rtsp://camera-falsa", abrir=lambda fonte: next(conexoes, CapturaFalsa(0, abre=False)))
    camera.iniciar()
    try:
        _esperar(lambda: camera._numero == 49)  # a câmera falsa entrega os 50 quadros de uma vez
        numero, quadro = camera.ler(espera_s=1)
        assert numero == 49  # pulou os antigos: entregou o último
        assert quadro[0, 0, 0] == 50
        assert camera.ler(espera_s=0.05) is None  # nada novo desde a última leitura
    finally:
        camera.parar()


def test_arquivo_de_video_termina_sem_reconectar(tmp_path):
    caminho = str(tmp_path / "curto.avi")
    gravador = cv2.VideoWriter(caminho, cv2.VideoWriter_fourcc(*"MJPG"), 100, (32, 32))
    for i in range(5):
        gravador.write(np.full((32, 32, 3), i * 40, dtype=np.uint8))
    gravador.release()

    camera = Camera(caminho).iniciar()
    try:
        while camera.ler(espera_s=1) is not None:
            pass
        assert camera.terminou
        assert camera.reconexoes == 0
    finally:
        camera.parar()
