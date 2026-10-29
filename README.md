# Leitor de Placas

Sistema de leitura automática de placas de veículos brasileiras (formatos antigo e Mercosul) para controle de acesso em condomínio ou estacionamento.

> 🚧 Projeto em construção, desenvolvido em etapas. Acompanhe o histórico de commits.

## Objetivo

- Detectar placas em vídeo (arquivo ou câmera IP via RTSP).
- Ler os caracteres e validar pelas regras da placa brasileira.
- Registrar cada veículo uma única vez por passagem (rastreamento).
- Controlar entradas e saídas: moradores, visitantes e veículos bloqueados.
- Interface simples para a portaria.

## Tecnologias (previstas)

- Python, OpenCV, ONNX Runtime
- SQLite
- pytest

## Como instalar

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

A `open-image-models` e a `fast-plate-ocr` instalam junto o `opencv-python-headless` (OpenCV sem janelas). Se a janela não abrir, reinstale o OpenCV completo:

```
pip uninstall -y opencv-python-headless opencv-python
pip install opencv-python==5.0.0.93
```

Na primeira execução, os modelos de detecção e de OCR são baixados automaticamente.

O vídeo de teste não fica no repositório. Baixe-o no Pexels (crédito abaixo) e salve-o na pasta `videos/`.

## Como usar

Mostrar um vídeo quadro a quadro com um retângulo desenhado (Etapa 1):

```
python -m leitor.video videos/pexels_fabio_reis_de_abreu.mp4
```

Teclas: `espaço` pausa e retoma, `q` ou `Esc` fecha. Use `--largura` para mudar o tamanho da janela (padrão: 1280).

Marcar as placas numa foto ou num quadro do vídeo (Etapa 3):

```
python -m leitor.deteccao foto.jpg
python -m leitor.deteccao videos/pexels_fabio_reis_de_abreu.mp4 --quadro 150
python -m leitor.deteccao videos/pexels_fabio_reis_de_abreu.mp4 --quadro 150 --salvar capturas/q150.jpg
```

Encontrar e ler as placas (Etapa 4). A placa lida aparece escrita sobre a imagem. A caixa fica vermelha quando o texto não forma uma placa brasileira válida:

```
python -m leitor.ocr videos/pexels_fabio_reis_de_abreu.mp4 --quadro 1200
```

Medir a taxa de acerto (Etapa 5):

```
python -m leitor.medicao coletar videos/pexels_fabio_reis_de_abreu.mp4
python -m leitor.medicao avaliar capturas/leituras_pexels_fabio_reis_de_abreu.csv data/gabarito_pexels_fabio_reis_de_abreu.csv --limite 0.80 --largura-minima 60
```

O `coletar` analisa 1 a cada 10 quadros (`--passo`), salva todas as leituras em `capturas/` e cria em `data/` um rascunho de gabarito com as placas candidatas. Antes de avaliar, o rascunho precisa ser conferido à mão, olhando o vídeo: corrija ou apague as placas erradas e acrescente as que faltaram. Para isso, use o `conferir`, que mostra o vídeo com as leituras por cima:

```
python -m leitor.medicao conferir videos/pexels_fabio_reis_de_abreu.mp4 --inicio 30
```

Teclas: `espaço` pausa, `a`/`d` voltam ou avançam um quadro (com o vídeo pausado) e `q` ou `Esc` fecham. O `avaliar` mostra acertos, falsos positivos e falsos negativos para cada limite de confiança. Planilhas e gabarito ficam fora do Git, porque contêm placas reais.

### Resultados da medição

Vídeo de teste: 1 a cada 10 quadros (316 quadros), 694 leituras. O gabarito tem 19 placas conferidas à mão no vídeo.

| Filtro | Leituras aceitas | Precisão | Placas lidas certo |
|---|---|---|---|
| Nenhum | 603 | 68,3% | 19 de 19 |
| Confiança ≥ 0,80 | 354 | 86,4% | 19 de 19 |
| Confiança ≥ 0,80 e largura ≥ 60 px | 238 | **98,7%** | **18 de 19** |

**Limites escolhidos: confiança mínima de 0,80 e placa com pelo menos 60 px de largura.**

Por que esses valores:
- Só a confiança não basta. Placas de longe (cerca de 50 px) são lidas errado *com confiança alta*: um "W" vira "V" com 97% de confiança. O tamanho da placa separa esses casos muito melhor.
- Abaixo de 60 px, as leituras erradas disparam (40 leituras erradas com largura de 50 px, contra 3 com 60 px). Acima de 60 px, a precisão quase não melhora e o sistema começa a perder placas (16 de 19 com 70 px).
- Acima de 0,80 de confiança, a precisão sobe pouco e uma placa a mais deixa de ser lida.
- A placa perdida é a de um carro estacionado ao fundo, que nunca passa de 55 px. Ela não seria lida com segurança nem por uma pessoa.

```
python -m leitor.medicao avaliar capturas/leituras_pexels_fabio_reis_de_abreu.csv data/gabarito_pexels_fabio_reis_de_abreu.csv --limite 0.80 --largura-minima 60
```

Gerar um registro por veículo (Etapa 6):

```
python -m leitor.processar videos/pexels_fabio_reis_de_abreu.mp4
python -m leitor.processar videos/pexels_fabio_reis_de_abreu.mp4 --sem-janela --gabarito data/gabarito_pexels_fabio_reis_de_abreu.csv
```

Cada placa é acompanhada de um quadro para o outro, pela sobreposição das caixas (IoU) ou, se não houver, pela distância entre os centros, e o veículo recebe um número enquanto está na tela. Só as leituras que passam nos limites da Etapa 5 contam como voto, com peso pela confiança. Quando a placa some por mais de 1 segundo, o veículo vira um registro com a placa mais votada. Se a mesma placa reaparecer em até 5 segundos (por exemplo, quando outro carro passa na frente), as duas passagens são juntadas.

Resultado no vídeo de teste: **17 registros, nenhum duplicado**. Foram 16 placas certas e 1 errada: FPO1620 no lugar de FPD1620, porque o OCR confunde D com O de forma sistemática nessa placa e a votação não corrige um erro que se repete. Das 19 placas do gabarito, 2 ficaram sem registro porque nunca apareceram grandes o bastante para uma leitura confiável.

Rodar os testes:

```
pytest
```

## Créditos e licenças

### Vídeos de teste

Vídeo obtido no [Pexels](https://www.pexels.com) e usado sob a [licença do Pexels](https://www.pexels.com/license/):

- Vídeo de **Fábio Reis de Abreu (Portuga)**, no Pexels (`videos/pexels_fabio_reis_de_abreu.mp4`)

### Bibliotecas

- [open-image-models](https://github.com/ankandrew/open-image-models), de ankandrew, sob a licença MIT. Usada para detectar as placas com o modelo `yolo-v9-t-384-license-plate-end2end`.
- Os modelos de detecção são baseados no YOLOv9: Chien-Yao Wang e Hong-Yuan Mark Liao, *YOLOv9: Learning What You Want to Learn Using Programmable Gradient Information*, arXiv:2402.13616, 2024.
- [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr), de ankandrew, sob a licença MIT. Usada para ler os caracteres com o modelo `cct-s-v2-global-model`.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime), da Microsoft, sob a licença MIT.
- [OpenCV](https://github.com/opencv/opencv), sob a licença Apache 2.0.
- [NumPy](https://github.com/numpy/numpy), sob a licença BSD-3-Clause.
- [pytest](https://github.com/pytest-dev/pytest), sob a licença MIT.

## Privacidade (LGPD)

Será preenchido antes da primeira versão.

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
