"""Etapa 2: regras da placa brasileira.

Formatos aceitos:
- antigo:   AAA9999 (3 letras e 4 números)
- Mercosul: AAA9A99 (3 letras, 1 número, 1 letra e 2 números)
"""

import re

ANTIGO = "antigo"
MERCOSUL = "mercosul"

_PADROES = {
    ANTIGO: re.compile(r"[A-Z]{3}[0-9]{4}"),
    MERCOSUL: re.compile(r"[A-Z]{3}[0-9][A-Z][0-9]{2}"),
}


def normalizar(texto: str) -> str:
    """Passa para maiúsculas e remove tudo que não for letra ou número ("abc-1234" vira "ABC1234")."""
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def formato_placa(texto: str) -> str | None:
    """Diz o formato da placa ("antigo" ou "mercosul"), ou None se o texto não for uma placa válida."""
    placa = normalizar(texto)
    for formato, padrao in _PADROES.items():
        if padrao.fullmatch(placa):
            return formato
    return None


def placa_valida(texto: str) -> bool:
    return formato_placa(texto) is not None


# Tabela de confusões comuns de OCR: caracteres que têm desenho parecido.
LETRA_PARA_NUMERO = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "A": "4",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
}
NUMERO_PARA_LETRA = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "4": "A",
    "5": "S",
    "6": "G",
    "7": "T",
    "8": "B",
}

# O que cada uma das 7 posições aceita. A posição 4 aceita os dois,
# porque é ela que diferencia o formato antigo (número) do Mercosul (letra).
_LETRA, _NUMERO, _QUALQUER = "L", "N", "?"
_POSICOES = (_LETRA, _LETRA, _LETRA, _NUMERO, _QUALQUER, _NUMERO, _NUMERO)


def corrigir_placa(texto: str) -> str | None:
    """Corrige confusões de OCR olhando o que cada posição aceita.

    Onde só pode haver número, "O" vira "0"; onde só pode haver letra, "0" vira "O".
    Devolve a placa corrigida, ou None se nem com a correção ela fica válida.

    A posição 4 não é corrigida: "8" e "B" ali são ambos válidos (antigo e Mercosul),
    então só a confiança do OCR pode decidir entre eles.
    """
    placa = normalizar(texto)
    if len(placa) != len(_POSICOES):
        return None

    corrigida = []
    for caractere, tipo in zip(placa, _POSICOES):
        if tipo == _LETRA:
            caractere = NUMERO_PARA_LETRA.get(caractere, caractere)
        elif tipo == _NUMERO:
            caractere = LETRA_PARA_NUMERO.get(caractere, caractere)
        corrigida.append(caractere)

    resultado = "".join(corrigida)
    return resultado if placa_valida(resultado) else None
