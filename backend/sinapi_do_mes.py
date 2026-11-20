# -*- coding: utf-8 -*-
"""Baixa o SINAPI de um mês direto da Caixa e grava numa tabela À PARTE.

📅 20/11/2026 — a tabela `sinapi_composicao` do motor parou em 03/2026. Medido
no relatório oficial de manutenções (abr→out/2026): 196 composições
desativadas, ~1.020 com a descrição mudada e 765 novas. Das 10.411 escolhas de
código SINAPI do último mês, 209 (2%) já apontavam código desativado — 180
eram o concreto fck 25/30 (94965/94966), que o orçamentista não acha mais no
SINAPI do mês.

A carga de março foi feita à mão, de um PC com a chave de serviço no .env.
Esta aqui roda NO SERVIDOR (a chave não sai de lá) e grava em
`sinapi_composicao_novo` — a tabela do motor NÃO muda. A troca é um passo
separado, depois de comparar as duas.

O formato e o endereço do arquivo da Caixa seguem o mesmo que o projeto aberto
sinapi-mcp (licença MIT) usa; a leitura da planilha é a NOSSA, a mesma do
`sinapi_loader.py` que carregou março.
"""
import io
import os
import re
import tempfile
import urllib.request
import zipfile

URL_DA_CAIXA = ("https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/"
                "SINAPI-{ano}-{mes}-formato-xlsx.zip")
TABELA_NOVA = "sinapi_composicao_novo"

# Março tinha 10.284 composições e outubro 10.710. Uma planilha que chega com
# muito menos que isso é sinal de que a Caixa mudou o formato (ou o arquivo
# veio pela metade) — aí NÃO grava nada.
MINIMO_DE_COMPOSICOES = 8000

_RE_MES = re.compile(r"^(20\d\d)-(0[1-9]|1[0-2])$")


def url_do_mes(mes: str) -> str:
    """'2026-10' → endereço do .zip da Caixa. Formato errado → ValueError."""
    m = _RE_MES.match((mes or "").strip())
    if not m:
        raise ValueError("mês no formato AAAA-MM (ex.: 2026-10)")
    return URL_DA_CAIXA.format(ano=m.group(1), mes=m.group(2))


def baixar(mes: str, timeout: int = 120) -> bytes:
    """Bytes do .zip do mês. Página de erro (HTML) no lugar do zip → ValueError."""
    req = urllib.request.Request(url_do_mes(mes), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dados = resp.read()
    if not dados.startswith(b"PK"):
        raise ValueError("a Caixa não devolveu um .zip pra %s (mês ainda não publicado?)" % mes)
    return dados


def extrair_referencia(zip_bytes: bytes, pasta: str) -> str:
    """Grava em `pasta` a planilha SINAPI_Referência do pacote e devolve o caminho.

    O nome vem com o acento em codificações diferentes conforme o mês, por isso
    procura por 'Refer' e não pelo nome exato."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        alvo = next((i for i in z.infolist()
                     if "Refer" in i.filename and i.filename.lower().endswith(".xlsx")), None)
        if alvo is None:
            raise ValueError("o pacote não tem a planilha SINAPI_Referência")
        caminho = os.path.join(pasta, "SINAPI_Referencia.xlsx")
        with open(caminho, "wb") as f:
            f.write(z.read(alvo))
    return caminho


def ler_composicoes(mes: str, zip_bytes: bytes) -> list:
    """Linhas prontas pra gravar: {codigo, descricao, unidade, sync_month}."""
    from sinapi_loader import parse_composicoes
    with tempfile.TemporaryDirectory() as pasta:
        caminho = extrair_referencia(zip_bytes, pasta)
        linhas = parse_composicoes(caminho, sync_month=mes + "-01")
    if len(linhas) < MINIMO_DE_COMPOSICOES:
        raise ValueError("só %d composições na planilha de %s (esperado ≥ %d) — "
                         "formato mudou? nada foi gravado"
                         % (len(linhas), mes, MINIMO_DE_COMPOSICOES))
    return linhas


def carregar(mes: str, apagar, inserir, lote: int = 500) -> dict:
    """Baixa, lê e grava o mês em TABELA_NOVA. Devolve o resumo.

    `apagar()` esvazia a tabela nova; `inserir(linhas)` grava um lote e devolve
    True/False. Os dois vêm de fora (no servidor, a REST com a chave de
    serviço), pra este módulo ser testado sem banco. Só apaga DEPOIS de ler a
    planilha inteira: download ou leitura que falha não deixa a tabela vazia."""
    linhas = ler_composicoes(mes, baixar(mes))
    apagar()
    gravadas, lotes_com_erro = 0, 0
    for i in range(0, len(linhas), lote):
        pedaco = linhas[i:i + lote]
        if inserir(pedaco):
            gravadas += len(pedaco)
        else:
            lotes_com_erro += 1
    return {"mes": mes, "lidas": len(linhas), "gravadas": gravadas,
            "lotes_com_erro": lotes_com_erro}
