# -*- coding: utf-8 -*-
"""Escala ADIVINHADA por votação de cotas não vira medição entregue.

🩸 11/09/2026, job b0fa9104 — uma folha de TABELA (sem escala escrita) recebeu
"1:500" por votação: os números que a votação tomou por cota eram os dígitos do
endereço e do telefone no carimbo. Com essa escala ela "mediu" 40 ambientes,
1.071,9 m² e 4.095 m de parede, e isso entrou no prompt como medição com
procedência.

📏 Medido nas 206 promoções desde 14/08 (`pdfvec:promo`): 6 pranchas em 3
arquivos vieram por votação (2,9%, carregando 1.852 m² e 4.846 m). Em 2 dos 3
arquivos a escala votada está FORA da faixa do próprio documento — 1:1000 onde
as outras pranchas dizem 1:25/1:50/1:75, e 1:500 onde as outras dizem 1:6 a
1:13. No terceiro caiu em 1:50, uma das escalas do documento: chute que
acertou. 88% do m² que sai daqui é invenção.

🔑 O passo 1 (`1a3fc1c`) elevou o custo: a medição da PRÓPRIA prancha virou a
prova que autoriza o número do item. Uma prancha com escala inventada deixou de
inflar só o teto do job e passou a autorizar sozinha o item que aponta pra ela.

🪤 Nome de arquivo aqui é FICTÍCIO: repositório público (regra dura nº6).
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
_SECAO_SEM_PROVA = "MEDIÇÕES VETORIAIS DA PRANCHA (escala NÃO confirmada"


def _vm(**kw):
    """Um retorno do filho do pdfvec, na forma que o `process_job` recebe."""
    base = {"scale": 50, "scale_src": "carimbo", "escala_validada": False,
            "n_rooms": 10, "rooms_m2": 120.0, "walls_m": 200.0, "n_walls": 40}
    base.update(kw)
    return base


# ── a decisão, chamada de verdade ────────────────────────────────────────
def test_a_escala_ADIVINHADA_por_votacao_nao_entrega_medicao():
    """O caso do job b0fa9104: folha de tabela, 1:500 votado, 1.071,9 m²."""
    vale, motivo = main._a_escala_sustenta_a_medicao(
        _vm(scale=500, scale_src="cotas", n_rooms=40, rooms_m2=1071.9, walls_m=4095.1))
    assert vale is False, motivo
    assert "ADIVINHADA" in motivo


def test_a_votacao_tambem_nao_entrega_quando_o_chute_PARECE_bom():
    """🪤 Perda deliberada: o 3º arquivo votou 1:50, que é escala do documento.
    A gente não tem como saber isso NA HORA — o motor promove página a página,
    antes de conhecer as outras. Barrar os três é o mínimo honesto; aceitar por
    concordância com o documento é o próximo passo, com número próprio."""
    vale, _ = main._a_escala_sustenta_a_medicao(
        _vm(scale=50, scale_src="cotas", n_rooms=21, rooms_m2=216.7, walls_m=742.5))
    assert vale is False


def test_CONTROLE_escala_DECLARADA_continua_entrando():
    """Carimbo, recorte e rótulo são leitura do que está escrito na prancha —
    declaração não é prova, mas não é invenção. Entram com a ressalva."""
    for fonte in ("carimbo", "viewport", "vista"):
        vale, motivo = main._a_escala_sustenta_a_medicao(_vm(scale_src=fonte))
        assert vale is True, (fonte, motivo)
        assert fonte in motivo


def test_CONTROLE_votacao_CONFIRMADA_por_cota_entra():
    """`escala_validada` é o par cota×elemento medido batendo na view principal.
    Passou nisso, a origem da escala não importa mais."""
    vale, motivo = main._a_escala_sustenta_a_medicao(
        _vm(scale_src="cotas", escala_validada=True))
    assert vale is True and "validada" in motivo


def test_CONTROLE_fonte_desconhecida_ou_vazia_nao_e_tratada_como_votacao():
    """Fonte nova (ou vazia) não pode ser barrada por engano — barrar é perder
    medição. Só a votação, que é a que inventa, fica de fora."""
    for fonte in (None, "", "fonte-que-ainda-nao-existe"):
        vale, _ = main._a_escala_sustenta_a_medicao(_vm(scale_src=fonte))
        assert vale is True, fonte
    assert main._a_escala_sustenta_a_medicao(None)[0] is True


# ── o motor CONSULTA a decisão (senão ela nasce morta) ───────────────────
def _if_da_decisao():
    """O `If` do `process_job` que protege a SEÇÃO DO PROMPT com a pergunta.

    🪤 14/09: a 1ª versão pegava o PRIMEIRO `if` que chamasse a função — e
    quando a porta do checkpoint passou a perguntar também, o guarda passou a
    apontar pro `if` errado e reprovou o conserto certo. Quem identifica o ramo
    é o que ele PROTEGE, não a ordem no arquivo.

    🪤 AST, não texto: aqui não dá pra chamar: o ramo mora dentro do
    `process_job`, que é a função de 5 mil linhas que sobe o motor inteiro.
    A AST enxerga a ESTRUTURA (qual ramo protege qual), que é o que importa —
    uma janela de texto não enxergaria.
    """
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "process_job"), None)
    assert fn is not None, "não achei o process_job"
    for no in ast.walk(fn):
        if not isinstance(no, ast.If):
            continue
        chama = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                    and d.func.id == "_a_escala_sustenta_a_medicao"
                    for d in ast.walk(no.test))
        if chama and _tem_texto(no.orelse, _SECAO_SEM_PROVA):
            return no
    return None


def _tem_texto(nos, trecho):
    for no in nos:
        for d in ast.walk(no):
            if isinstance(d, ast.Constant) and isinstance(d.value, str) and trecho in d.value:
                return True
    return False


def _grava_em(nos, nome):
    for no in nos:
        for d in ast.walk(no):
            if isinstance(d, ast.Subscript) and isinstance(d.value, ast.Name) and d.value.id == nome:
                return True
            if isinstance(d, ast.Name) and d.id == nome and isinstance(d.ctx, (ast.Store,)):
                return True
    return False


def test_o_motor_PERGUNTA_antes_de_entregar_a_medicao_da_prancha():
    """🪤 Guarda de ponto de chamada: a função pode existir, estar certa, e
    ninguém consultar — foi assim que o `files_count` do /add-file nasceu morto.
    O ramo que monta a seção do prompt tem que estar DEPOIS desta pergunta."""
    no = _if_da_decisao()
    assert no is not None, (
        "o `process_job` não consulta `_a_escala_sustenta_a_medicao` — a decisão "
        "nasceu morta e a escala adivinhada volta a virar medição")
    assert _tem_texto(no.orelse, _SECAO_SEM_PROVA), (
        "a seção da escala sem prova não está protegida por esta pergunta")
    assert not _tem_texto(no.body, _SECAO_SEM_PROVA), (
        "o ramo que BARRA está montando a seção mesmo assim")


def test_a_prancha_barrada_NAO_entra_na_prova_da_propria_prancha():
    """Desde o passo 1, `_pdfvec_por_prancha` é o que autoriza o número do item.
    Deixar a prancha adivinhada entrar 'só na soma' seria o pior dos mundos."""
    no = _if_da_decisao()
    assert no is not None
    assert not _grava_em(no.body, "_pdfvec_por_prancha"), (
        "a prancha de escala adivinhada está sendo gravada como prova da própria prancha")
    assert not _grava_em(no.body, "_pdfvec_area_m2"), (
        "a prancha de escala adivinhada ainda soma no m² do job")
    assert _grava_em(no.orelse, "_pdfvec_por_prancha"), (
        "o ramo que entrega deixou de registrar a medição por prancha — "
        "este guarda ficaria cego")

def test_TODA_porta_que_grava_a_prova_passa_pela_pergunta():
    """🩸 14/09, achado da revisão: o conserto morava só no laço de medição, e
    um job RETOMADO não passa por lá — a medição volta pronta do checkpoint,
    inclusive a de escala adivinhada gravada antes deste commit.

    🔑 Em vez de tapar essa porta e torcer pra não haver outra, o guarda cobra a
    REGRA: toda gravação em `_pdfvec_por_prancha` (a prova que autoriza o número
    do item desde o passo 1) tem que estar sob um `if` que ou faz a pergunta, ou
    exige `escala_validada` — que é a prova forte.
    """
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "process_job"), None)
    assert fn is not None

    pai = {}
    for no in ast.walk(fn):
        for f in ast.iter_child_nodes(no):
            pai[f] = no

    def _protegido(no):
        p = pai.get(no)
        while p is not None:
            if isinstance(p, ast.If):
                txt = ast.dump(p.test)
                if "_a_escala_sustenta_a_medicao" in txt or "escala_validada" in txt:
                    return True
            p = pai.get(p)
        return False

    gravacoes = [d for d in ast.walk(fn)
                 if isinstance(d, ast.Subscript) and isinstance(d.value, ast.Name)
                 and d.value.id == "_pdfvec_por_prancha"
                 and isinstance(d.ctx, ast.Store)]
    assert len(gravacoes) >= 3, (
        "achei só %d gravação(ões) da prova por prancha — o guarda perdeu o alvo "
        "(eram 3: checkpoint, escala validada e escala declarada)" % len(gravacoes))
    desprotegidas = [d.lineno for d in gravacoes if not _protegido(d)]
    assert not desprotegidas, (
        "main.py linha(s) %s gravam a medição da prancha como PROVA sem passar "
        "pela pergunta da escala — por aí a adivinhação volta"
        % ", ".join(str(x) for x in desprotegidas))

def test_quem_BARRA_a_medicao_deixa_rastro():
    """🩸 14/09, mutante sobrevivente: desligar o `_log_error` do descarte deixava
    tudo verde. A prancha era barrada CERTO e em SILÊNCIO — a família que já nos
    custou 144 linhas engolidas em 37 jobs.

    🔑 Sem rastro eu não consigo responder "quantas pranchas o cliente perdeu
    por escala adivinhada?", que é a pergunta que mede se este conserto foi bom
    ou se está tirando medição demais.
    """
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "process_job"), None)
    assert fn is not None

    def _nega_a_pergunta(teste):
        for d in ast.walk(teste):
            if isinstance(d, ast.UnaryOp) and isinstance(d.op, ast.Not):
                if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                       and c.func.id == "_a_escala_sustenta_a_medicao"
                       for c in ast.walk(d.operand)):
                    return True
        return False

    def _loga_o_descarte(corpo):
        for no in corpo:
            for d in ast.walk(no):
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                        and d.func.id == "_log_error" and d.args
                        and isinstance(d.args[0], ast.Constant)
                        and d.args[0].value == "pdfvec:escala-adivinhada"):
                    return True
        return False

    barram = [no for no in ast.walk(fn) if isinstance(no, ast.If) and _nega_a_pergunta(no.test)]
    assert len(barram) >= 2, (
        "achei só %d ramo(s) que barram a medição — eram 2 (o laço de medição e a "
        "porta do checkpoint); o guarda perdeu o alvo" % len(barram))
    mudos = [no.lineno for no in barram if not _loga_o_descarte(no.body)]
    assert not mudos, (
        "main.py linha(s) %s barram a medição da prancha SEM registrar — descarte "
        "SILENCIOSO: ninguém consegue medir depois quanto este conserto tirou"
        % ", ".join(str(x) for x in mudos))
