# -*- coding: utf-8 -*-
"""PDF e DXF nao sao caminhos equivalentes - e a copy oferecia como se fossem.

Ver o cabecalho original: 03/09/2026, cliente-NN. O DWG dele nao abriu, ele
recebeu as 14:02 o e-mail com "O ideal e reenviar em DXF ou PDF vetorial",
subiu um PDF as 14:04 e recebeu 19 de 19 linhas ZERADAS.

MEDIDO em 118 projetos concluidos: so CAD -> 73,6% com item MEDIDO;
so PDF -> 5,4% (35 de 37 receberam ZERO).
"""
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
for _p in (_BACKEND, _AQUI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _emails_render as _R  # noqa: E402

_NL = chr(10)

import io  # noqa: E402

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


_B = chr(92)
_NL = _B + "n"
# Cola literais grudados: a frase do cliente não existe inteira no fonte.
_COLA = re.compile('"' + _B + 's*' + _NL + _B + 's*f?"')


def _copy(src=None):
    src = src if src is not None else _FONTE
    linhas = [l for l in src.splitlines() if not l.strip().startswith("#")]
    return _COLA.sub("", chr(10).join(linhas))


# A peneira ÚNICA de "isto é uma RECOMENDAÇÃO do que mandar". Um lugar só: os
# dois guardas deste arquivo perguntam a mesma coisa, e duas cópias da mesma
# régua divergem sozinhas (foi o que aconteceu — a absolvição da "lista dos
# três" não fazia esta pergunta e por isso absolvia recomendação).
_RECOMENDA = re.compile(
    r"(?:ideal|reenvi|reexport|manda|mande|suba|sobe|exporte|replote)", re.I)


def _pdf_vem_primeiro(src=None):
    """Recomendação que nomeia PDF ANTES de DXF/DWG.

    🩸 03/09, 2ª revisão: a absolvição de "lista dos três nomes adjacentes"
    (necessária, porque listar formatos aceitos é legítimo) escondia um
    problema de ORDEM. O ramo "não conseguimos ler as quantidades" dizia
    "reenviar exportado direto do CAD **(PDF vetorial, DWG ou DXF)**" — com o
    PDF primeiro — e `_oferece_pdf_como_igual` absolvia por causa da forma.

    🔑 Numa frase que RECOMENDA o que mandar, o formato citado primeiro é o que
    o cliente vai tentar. Só CAD mede em 73,6% dos projetos; só PDF em 5,4%.
    Liderar pelo PDF é mandar 18 em 19 pro caminho que não mede.

    🪤 Só vale onde há RECOMENDAÇÃO. "Envie ao menos um arquivo: DWG, DXF ou
    PDF" é lista de aceitos e não recomenda nada — nela a ordem é irrelevante.
    """
    txt = _copy(src)
    ruins = []
    for m in re.finditer(_RECOMENDA.pattern + "[^" + _NL + "]{0,200}", txt, re.I):
        t = m.group(0)
        pos_pdf = t.upper().find("PDF")
        pos_cad = min([p for p in (t.upper().find("DXF"), t.upper().find("DWG"))
                       if p >= 0] or [-1])
        if pos_pdf < 0 or pos_cad < 0:
            continue
        if pos_pdf < pos_cad:
            ruins.append(t.strip())
    return ruins


def _frases_da_recusa():
    """[(ramo, frase)] de tudo que o cliente lê nos e-mails de "não deu".

    Cobre os TRÊS ramos do `_build_falha_email` (DWG que não abre, arquivo
    grande, prancha sem cotas) e mais os dois irmãos de má notícia — é
    exatamente aqui que a pergunta "e agora, o que eu mando?" é respondida.
    """
    import main as _m
    fora = []
    fontes = [(rot, _R.falha_do_ramo(hint)) for rot, hint in _R.RAMOS_DE_FALHA]
    fontes.append(("sem_medida", _m._render_email_by_type("sem_medida")))
    fontes.append(("leu_sem_medir", _m._render_email_by_type("leu_sem_medir")))
    for rot, (subj, html) in fontes:
        pedacos = [subj, _R.preheader_de(html)]
        pedacos += [alt for _arq, alt in _R.imagens_de(html)]
        for p in pedacos:
            fora.append((rot, p))
        for f in _R.frases(html):
            fora.append((rot, f))
    return fora


_RESSALVA = re.compile(
    r"estim|n[ãa]o mede|quase nunca|zerad|n[ãa]o [ée] confi|menos confi"
    r"|sem medi|n[ãa]o medid|nunca(\s+\w+){0,3}\s+medi", re.I)
_CAD = re.compile(r"\b(DXF|DWG)\b", re.I)
_PDF = re.compile(r"\bPDF\b", re.I)
_LISTA_DOS_TRES = re.compile(
    r"(DWG|DXF|PDF)\s*[,/]?\s*(ou|e|,)?\s*(DWG|DXF|PDF)\s*[,/]?\s*(ou|e|,)?\s*"
    r"(DWG|DXF|PDF)", re.I)


def _frase_poe_pdf_no_mesmo_nivel(frase):
    """A frase cita PDF e CAD lado a lado sem dizer que o PDF entrega menos.

    🩸 06/09, 3ª revisão: a absolvição da "lista dos três" (`DWG, DXF ou PDF`)
    não perguntava se a frase RECOMENDA. Bastava escrever a recomendação no
    formato de lista — *"mande em DXF, DWG ou PDF vetorial"* — pra oferecer PDF
    como equivalente logo depois de uma falha e sair absolvido, sem nenhuma
    ressalva de que de PDF só sai estimativa. É a frase de 03/09 com outra
    pontuação; e o guarda irmão de ORDEM também não pega, porque nessa forma o
    PDF vem por último.

    🔑 Listar formatos ACEITOS continua legítimo. Listar formatos RECOMENDADOS
    não é lista: é recomendação, e aí o PDF precisa vir com a ressalva.
    """
    if not (_PDF.search(frase) and _CAD.search(frase)):
        return False
    if _RESSALVA.search(frase):
        return False
    if _LISTA_DOS_TRES.search(frase) and not _RECOMENDA.search(frase):
        return False
    return True


def test_a_copy_nao_oferece_PDF_como_alternativa_igual_ao_DXF():
    """🩸 A frase que o cliente-NN leu dois minutos antes de subir um PDF.

    🚨 06/09/2026 — a janela `DXF[^\\n]{0,60}PDF` era o ponto cego: bastava
    afastar os dois nomes pra ela não casar. Agora o julgamento é por FRASE, no
    e-mail montado — a distância entre as palavras deixou de importar.
    """
    ruins = [(rot, f) for rot, f in _frases_da_recusa()
             if _frase_poe_pdf_no_mesmo_nivel(f)]
    assert not ruins, (
        "a copy voltou a oferecer PDF e DXF como equivalentes — medido, só-PDF "
        "entrega item medido em 5,4% dos projetos contra 73,6% do CAD:"
        + _NL + "  " + (_NL + "  ").join("%s: %s" % (r, f[:130]) for r, f in ruins))


def test_CONTROLE_o_julgamento_por_frase_REPROVA_as_duas_versoes_ruins():
    """🧪 As duas frases que passaram pelo guarda velho, no julgamento novo."""
    afastada = ("O ideal é reenviar em DXF, que é o formato onde a gente lê a "
                "geometria exata do desenho e devolve quantidade medida, ou em "
                "PDF vetorial, se for o que você tiver na mão agora.")
    # 🔒 Rótulo, nunca o nome (regra dura nº6, repo público): é a frase que o
    # cliente-NN leu às 14:02 de 03/09, dois minutos antes de subir o PDF.
    de_0309 = "O ideal é reenviar em DXF ou PDF vetorial, ou salvar o DWG numa versão mais antiga."
    assert _frase_poe_pdf_no_mesmo_nivel(afastada), (
        "a frase com os dois formatos afastados continua passando — o guarda "
        "novo herdou o ponto cego do antigo")
    assert _frase_poe_pdf_no_mesmo_nivel(de_0309)


def test_CONTROLE_o_julgamento_por_frase_ACEITA_a_copy_HONESTA():
    """Dizer que de PDF sai estimativa é o conserto — não pode ser acusado."""
    boa = ("Se não der nenhum dos dois, dá pra mandar o PDF vetorial — mas aí a "
           "gente identifica e estima, não mede: de PDF quase nunca sai "
           "quantidade medida do desenho.")
    lista = "Envie ao menos um arquivo: DWG, DXF ou PDF."
    assert not _frase_poe_pdf_no_mesmo_nivel(boa), "o guarda proibiria o conserto"
    assert not _frase_poe_pdf_no_mesmo_nivel(lista), (
        "o guarda acusaria a lista de formatos ACEITOS — viraria ruído e "
        "pararia de ser lido")


@pytest.mark.parametrize("frase", [
    "O ideal é mandar em DXF, DWG ou PDF vetorial.",
    "Reenvie o arquivo em DXF, DWG ou PDF vetorial que a gente processa de novo.",
    "Exporte de novo: DXF, DWG ou PDF.",
    "Suba de novo em DWG, DXF ou PDF vetorial.",
])
def test_CONTROLE_recomendacao_em_FORMA_DE_LISTA_continua_sendo_acusada(frase):
    """🩸 O buraco que o cético achou: a recomendação disfarçada de lista.

    Estas quatro frases citam os três formatos adjacentes (então a absolvição
    da "lista dos três" as inocentava) e põem o PDF por ÚLTIMO (então o guarda
    de ORDEM também não pega). Mesmo assim são a frase de 03/09: o cliente lê,
    sobe o PDF, e cai no caminho que entrega item medido em 5,4% dos projetos.
    """
    assert _frase_poe_pdf_no_mesmo_nivel(frase), (
        "recomendação escrita em forma de lista escapou das duas peneiras: %r" % frase)
    assert not _pdf_vem_primeiro(frase + chr(10)), (
        "controle do controle: o guarda de ORDEM não deveria pegar esta — é "
        "justamente por isso que a absolvição da lista precisava apertar")


def test_CONTROLE_o_e_mail_de_falha_e_montado_de_verdade():
    """🪤 Verde vazio é verde falso: se os builders parassem de ser chamados,
    os três testes acima passariam sem olhar nada."""
    frases = _frases_da_recusa()
    ramos = {r for r, _f in frases}
    assert len(ramos) == 5, "sumiu um ramo do e-mail de falha: %s" % sorted(ramos)
    assert len(frases) > 60, "só %d frases — os e-mails não estão sendo montados" % len(frases)
    assert any("DXF" in f for _r, f in frases), "nenhuma frase cita DXF"
    assert any("PDF" in f for _r, f in frases), "nenhuma frase cita PDF"


def test_nao_prometemos_que_medimos_pela_geometria_do_PDF():
    """Havia uma frase prometendo medição de PDF: 35 de 37 saíram com zero."""
    txt = _copy()
    proibida = re.search(
        "PDF[^" + _NL + "]{0,120}a gente mede pela geometria", txt, re.I)
    assert not proibida, (
        "voltou a prometer que mede pela geometria do PDF: medido, 35 de 37 "
        "projetos só-PDF receberam ZERO item medido")


def test_CONTROLE_a_recomendacao_de_DXF_continua_de_pe():
    """Consertar a equivalência não pode virar 'não recomenda nada'.

    DXF é o formato nº1 desta casa desde 20/07 e a recomendação tem que
    continuar explícita — é ela que leva o cliente pro caminho de 73,6%.
    """
    txt = _copy()
    assert re.search("reenviar em <b>DXF</b>|reenviar em DXF", txt, re.I), (
        "sumiu a recomendação de reenviar em DXF")


def test_nenhuma_recomendacao_cita_PDF_antes_do_CAD():
    """🩸 O ramo vizinho, que a absolvição de 'lista de três' escondia."""
    ruins = _pdf_vem_primeiro()
    assert not ruins, (
        "recomendação citando PDF antes de DXF/DWG — o formato citado primeiro "
        "é o que o cliente tenta, e só PDF mede em 5,4% contra 73,6% do CAD:"
        + _NL + "  " + (_NL + "  ").join(r[:110] for r in ruins))


def test_CONTROLE_o_guarda_de_ordem_REPROVA_a_copy_que_estava_no_ar():
    """A frase real do ramo, como estava antes deste conserto."""
    antiga = ('    fix = ("O ideal é <b>reenviar a planta completa exportada '
              'direto do CAD</b> (PDF vetorial, DWG ou DXF).")' + chr(10))
    assert _pdf_vem_primeiro(antiga), (
        "o guarda de ordem não acusa a frase que estava em produção — foi "
        "exatamente ela que a absolvição de 'lista de três' deixou passar")


def test_CONTROLE_o_guarda_de_ordem_ACEITA_a_ordem_CERTA():
    """DXF primeiro, PDF depois e rotulado — é o conserto, não pode ser acusado."""
    boa = ('    fix = ("O ideal é reenviar exportado direto do CAD, em DXF. Se '
           'você só tem o PDF, replote em PDF vetorial — aí a gente estima.")' + chr(10))
    assert not _pdf_vem_primeiro(boa)


def test_CONTROLE_lista_de_formatos_ACEITOS_nao_e_recomendacao():
    """🪤 "Envie ao menos um arquivo: DWG, DXF ou PDF" não recomenda nada.

    Sem esta absolvição o guarda acusaria a validação de upload, viraria ruído
    e pararia de ser lido — que é como um guarda morre.
    """
    lista = '    raise HTTPException(400, "Envie ao menos um arquivo: DWG, DXF ou PDF.")' + chr(10)
    assert not _pdf_vem_primeiro(lista)
