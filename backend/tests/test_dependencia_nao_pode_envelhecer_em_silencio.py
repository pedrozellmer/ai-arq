# -*- coding: utf-8 -*-
"""Dependência com CVE conhecida não volta pro requirements sem alguém ver.

🚨 08/09/2026, auditoria de segurança. Duas portas PÚBLICAS abertas por
dependência parada — conferido por mim na API do OSV, não em documento:

    starlette 0.38.6 (arrastado pelo fastapi 0.115.0) ... 14 vulns, 3 ALTAS
    python-multipart 0.0.18 ............................. 14 vulns, 3 ALTAS

O caminho é `POST /api/estimate-price`, que é público (sem login). As três
travas que existem — rate limit por IP, teto de 450 MB e cheque de JWT — moram
DENTRO do corpo da rota, e o FastAPI só chega lá DEPOIS de parsear o
formulário. Com 4 GB e `--workers 1`, poucas requisições simultâneas derrubam o
backend pra TODOS os clientes.

🪤 O QUE ESTE GUARDA EXISTE PRA IMPEDIR, e é a lição do caso: **o pin do
python-multipart em 0.0.18 estava CERTO quando foi feito** — 0.0.18 é
exatamente a versão que corrigiu a CVE-2024-53981. O problema não foi a
escolha; foi ela ter ficado parada dois anos sem ninguém perguntar se ainda
servia. Pin não envelhece sozinho: alguém tem que envelhecer junto com ele.

🪤 E o starlette era TRANSITIVO — ninguém o escrevia em lugar nenhum, então
ninguém o revisava. Agora é explícito, e este guarda cobra que continue.

🚫 O QUE ESTE GUARDA **NÃO** FAZ: consultar CVE nova. Isso precisa de rede, e
bancada que depende de rede falha por motivo errado. Ele congela o que já foi
MEDIDO em 08/09 — o piso só sobe. Vigiar CVE nova continua em aberto.
"""
import io
import os
import re

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REQ = os.path.join(_BACKEND, "requirements.txt")

#: pacote -> (versão mínima, o que ela fecha). Medido na API do OSV em
#: 08/09/2026. 🔑 O piso só SOBE — baixar exige medir de novo e dizer por quê.
_PISO = {
    "fastapi": ((0, 136, 1),
                "abaixo disso o pin é `starlette<0.39`, que PROÍBE o starlette "
                "corrigido — o fastapi é quem trancava a porta"),
    "starlette": ((1, 3, 1),
                  "3 falhas ALTAS; a última (GHSA-82w8-qh3p-5jfq) só cai em 1.3.1"),
    "python-multipart": ((0, 0, 31),
                         "3 falhas ALTAS na mesma rota pública; a última "
                         "(GHSA-v9pg-7xvm-68hf) só cai em 0.0.31"),
    "pdfplumber": ((0, 11, 10),
                   "ele PINA o pdfminer.six com `==`; abaixo de 0.11.10 prende a "
                   "20231228, que tem 2 ALTAS de execução de código via pickle"),
    "Pillow": ((12, 3, 0),
               "13 falhas ALTAS no 10.4.0. 📏 alcance baixo aqui (recebe bitmap "
               "já decodificado, não parseia formato exótico), mas subir é barato"),
    "Jinja2": ((3, 1, 6), "6 falhas, nenhuma ALTA — salto de patch"),
}

#: 🚫 Fica ATRÁS de propósito, com o motivo escrito. Sem isto, a próxima pessoa
#: lê o piso, vê o weasyprint fora e conclui que foi esquecimento.
_FICA_ATRAS_DE_PROPOSITO = {
    "weasyprint": (
        "62.3 tem UMA falha alta (GHSA-983w): bypass da proteção de SSRF via "
        "redirect HTTP. O nosso `url_fetcher` (pdf_seguro.py) recusa tudo que "
        "não seja `data:`, então não existe requisição HTTP pra redirecionar — "
        "a falha não é alcançável nesta configuração. Subir seriam 8 versões "
        "maiores num pacote que NÃO está instalado na máquina onde a bancada é "
        "escrita: trocaria uma falha fechada por uma mudança que ninguém "
        "consegue testar antes do deploy."),
}

_RX = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*==\s*([0-9]+(?:\.[0-9]+)*)", re.M)


def _pinos():
    txt = io.open(_REQ, encoding="utf-8").read()
    # 🪤 Só linhas de verdade: o cabeçalho deste arquivo CITA versões antigas
    # pra explicar o defeito ("starlette 0.38.6", "0.0.18"), e uma peneira que
    # lesse comentário acusaria a própria explicação — foi o que já me
    # empurrou, uma vez, a apagar documentação pra calar alarme.
    vivas = "\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("#"))
    return {m.group(1).lower(): tuple(int(x) for x in m.group(2).split("."))
            for m in _RX.finditer(vivas)}


@pytest.mark.parametrize("pacote", sorted(_PISO))
def test_o_pin_nao_esta_abaixo_do_piso_medido(pacote):
    piso, porque = _PISO[pacote]
    pinos = _pinos()
    # 🪤 O nome no requirements tem caixa (Pillow, Jinja2) e o parser normaliza:
    # comparar com caixa fazia o guarda acusar "sumiu do requirements" um pacote
    # que estava lá. Guarda que acusa o inocente treina a ignorar.
    pacote = pacote.lower()
    assert pacote in pinos, (
        "%s sumiu do requirements.txt. Se virou transitivo de novo, ninguém "
        "mais o revisa — foi assim que o starlette ficou dois anos parado."
        % pacote)
    atual = pinos[pacote]
    assert atual >= piso, (
        "%s pinado em %s, abaixo do piso %s.\n%s"
        % (pacote, ".".join(map(str, atual)), ".".join(map(str, piso)), porque))


@pytest.mark.parametrize("pacote", sorted(_FICA_ATRAS_DE_PROPOSITO))
def test_quem_fica_atras_tem_o_motivo_ESCRITO_no_requirements(pacote):
    """🪤 Dependência velha sem explicação é indistinguível de esquecimento — e
    a próxima auditoria vai reabrir o mesmo achado, gastando o dia de alguém.

    Este teste não julga a decisão: ele exige que ela esteja escrita ONDE quem
    for mexer vai ler, que é o requirements.txt.
    """
    txt = io.open(_REQ, encoding="utf-8").read()
    i = txt.lower().find(pacote.lower() + "==")
    assert i > 0, "%s sumiu do requirements" % pacote
    # o bloco de comentário imediatamente acima da linha
    antes = txt[:i].rsplit("\n\n", 1)[-1]
    assert antes.count("#") >= 3, (
        "%s está atrás da versão corrigida e o requirements.txt não explica "
        "por quê — quem ler vai achar que foi esquecimento." % pacote)
    assert "url_fetcher" in antes or "alcanc" in antes.lower(), (
        "a explicação não diz por que a falha não alcança a gente: %r"
        % antes[-160:])


def test_o_starlette_continua_EXPLICITO():
    """🔑 Ele era transitivo. Dependência que ninguém escreve é dependência que
    ninguém revisa — e foi exatamente a que abriu a porta pública."""
    txt = io.open(_REQ, encoding="utf-8").read()
    vivas = [l for l in txt.splitlines() if not l.lstrip().startswith("#")]
    assert any(l.strip().lower().startswith("starlette==") for l in vivas), (
        "o starlette voltou a ser transitivo")


def test_CONTROLE_a_peneira_ACHA_um_pin_baixo_plantado():
    """🧪 Sem isto, um guarda que não lê nada passaria em tudo acima."""
    baixo = "fastapi==0.115.0\nstarlette==0.38.6\npython-multipart==0.0.18\n"
    achados = {m.group(1).lower(): tuple(int(x) for x in m.group(2).split("."))
               for m in _RX.finditer(baixo)}
    assert achados["fastapi"] < _PISO["fastapi"][0]
    assert achados["starlette"] < _PISO["starlette"][0]
    assert achados["python-multipart"] < _PISO["python-multipart"][0]


def test_CONTROLE_o_comentario_do_arquivo_NAO_e_lido_como_pin():
    """🪤 O cabeçalho do requirements cita as versões VELHAS pra explicar o
    defeito. Se a peneira lesse comentário, ela acusaria a própria explicação e
    me empurraria a apagá-la — que é o pior conserto possível."""
    txt = io.open(_REQ, encoding="utf-8").read()
    assert "0.0.18" in txt, "o comentário que explica o caso sumiu do arquivo"
    pinos = _pinos()
    assert pinos["python-multipart"] >= _PISO["python-multipart"][0], (
        "a peneira leu a versão citada no comentário como se fosse o pin")


def test_o_que_esta_INSTALADO_aqui_tambem_respeita_o_piso():
    """🪤 A bancada rodava contra bibliotecas que a PRODUÇÃO não tinha — local
    com fastapi 0.136 e starlette 1.0 enquanto o requirements pinava 0.115/0.38.
    Verde aqui não provava nada sobre lá. Este teste amarra os dois lados.

    🚫 Pula em vez de reprovar quando o pacote não está instalado: quem roda a
    bancada sem ambiente completo não é o caso que este guarda persegue.
    """
    import importlib.metadata as md
    for pacote, (piso, porque) in sorted(_PISO.items()):
        try:
            bruto = md.version(pacote)
        except Exception:
            pytest.skip("%s não está instalado neste ambiente" % pacote)
        atual = tuple(int(x) for x in re.findall(r"\d+", bruto)[:3])
        assert atual >= piso, (
            "instalado aqui: %s %s, abaixo do piso %s — a bancada estaria "
            "validando um ambiente que a produção não vai ter.\n%s"
            % (pacote, bruto, ".".join(map(str, piso)), porque))
