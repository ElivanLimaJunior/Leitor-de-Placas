import pytest
from fastapi.testclient import TestClient

from leitor.banco import Banco
from leitor.web.app import criar_app


@pytest.fixture
def cliente(tmp_path):
    caminho = str(tmp_path / "teste.db")
    Banco(caminho).fechar()
    with TestClient(criar_app(caminho)) as cliente:
        yield cliente


def test_pagina_abre(cliente):
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "Portaria" in resposta.text


def test_estado_inicial(cliente):
    estado = cliente.get("/api/estado").json()
    assert estado["vagas"] == 20
    assert estado["livres"] == 20
    assert estado["camera"]["ativa"] is False
    assert estado["eventos"] == []


def test_entrada_e_saida_manual(cliente):
    resposta = cliente.post("/api/entrada", json={"placa": "epy-4372"})
    assert resposta.json()["situacao"] == "liberado"
    assert resposta.json()["vaga"] == 1

    estado = cliente.get("/api/estado").json()
    assert estado["livres"] == 19
    assert estado["dentro"][0]["placa"] == "EPY4372"
    assert estado["eventos"][0]["placa"] == "EPY4372"
    assert estado["patio"][0] | {"minutos": 0} == estado["dentro"][0] | {"minutos": 0}
    assert estado["patio"][1] == {"vaga": 2, "placa": None}

    saida = cliente.post("/api/saida", json={"placa": "EPY4372"}).json()
    assert saida["valor"] == 0  # dentro da tolerância
    assert cliente.get("/api/estado").json()["livres"] == 20


def test_entrada_repetida_e_placa_invalida(cliente):
    cliente.post("/api/entrada", json={"placa": "EPY4372"})
    assert cliente.post("/api/entrada", json={"placa": "EPY4372"}).status_code == 409
    assert cliente.post("/api/entrada", json={"placa": "XX"}).status_code == 400
    assert cliente.post("/api/saida", json={"placa": "GAM4069"}).status_code == 404


def test_entrada_manual_de_bloqueado_avisa_mas_registra(cliente):
    # Pelo painel, quem decide é o operador: o alerta aparece, mas a entrada é gravada.
    cliente.post("/api/veiculos", json={"placa": "BZR7297", "proprietario": "Carlos", "tipo": "bloqueado"})
    resposta = cliente.post("/api/entrada", json={"placa": "BZR7297"}).json()
    assert resposta["situacao"] == "bloqueado"
    assert "operador" in resposta["mensagem"]
    estado = cliente.get("/api/estado").json()
    assert (estado["eventos"][0]["situacao"], estado["eventos"][0]["tipo"]) == ("bloqueado", "bloqueado")
    assert estado["ocupadas"] == 1


def test_cadastro(cliente):
    assert cliente.post(
        "/api/veiculos", json={"placa": "GAM4069", "proprietario": "Ana", "tipo": "mensalista"}
    ).status_code == 200
    assert [v["placa"] for v in cliente.get("/api/veiculos").json()] == ["GAM4069"]
    assert cliente.post("/api/veiculos", json={"placa": "GAM4069", "proprietario": "Ana", "tipo": "vip"}).status_code == 422
    assert cliente.delete("/api/veiculos/GAM4069").status_code == 200
    assert cliente.delete("/api/veiculos/GAM4069").status_code == 404


def test_relatorio(cliente):
    cliente.post("/api/entrada", json={"placa": "EPY4372"})
    relatorio = cliente.get("/api/relatorio", params={"de": "2000-01-01", "ate": "2100-01-01"}).json()
    assert sum(relatorio["por_hora"].values()) == 1
    assert relatorio["frequentes"][0]["placa"] == "EPY4372"


def test_video_sem_camera(cliente):
    assert cliente.get("/video").status_code == 404
