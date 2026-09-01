# -*- coding: utf-8 -*-
"""Quando o cliente apaga uma linha, o contador do projeto tem que cair.

🩸 A rota de revisão apagava a row de `project_items` e NUNCA mexia em
`projects.items_count`. Resultado: a tela dizia "50 itens" com 33 na lista, e o
cliente que apagou 17 linhas DE PROPÓSITO aparecia no nosso painel como
"o motor perdeu item".

📏 MEDIDO em 01/09/2026, investigando 647 itens que pareciam perdidos em 24 de
144 jobs. A investigação separou DUAS populações:
  · 21 jobs ANTES de 31/08, 610 itens — **15 deles nunca tiveram a tela de
    revisão aberta**, então não foi o cliente. Perda real, causa em aberto.
  · 3 jobs DEPOIS de 31/08, 37 itens — todos com a revisão aberta e com
    `item_reviews`, e 37 é exatamente o número de rejects. **Este arquivo
    guarda esses.**

🪤 Por que a data separa as duas: até 31/08 a FK de `item_reviews` tinha
ON DELETE CASCADE e o registro da exclusão se apagava junto com o item. Ou seja,
para job antigo a AUSÊNCIA de reject não prova ausência de exclusão — o que
prova é `revisao_aberturas = 0`.

🪤 O conserto RECONTA no banco em vez de fazer `items_count - 1`: subtrair supõe
que o número de partida estava certo, e é justamente ele que não dá pra assumir.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_comentarios(txt):
    return "\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("#"))


def _bloco_do_reject():
    """O trecho que roda quando o cliente aperta a lixeira."""
    src = _fonte()
    # 🪤 `if action == "reject":` aparece 2x no arquivo — a âncora tem que ser
    # o comentário do passo 3, que é único.
    ini = "    # 3) Se rejeitado, deleta row do item"
    assert src.count(ini) == 1, "a âncora do bloco de reject mudou"
    i = src.index(ini)
    fim = '    if action in ("edit", "reject"):'
    return src[i:src.index(fim, i)]


def test_o_reject_ATUALIZA_o_items_count():
    """🩸 O que faltava."""
    bloco = _sem_comentarios(_bloco_do_reject())
    assert "_contar_itens_no_banco(job_id)" in bloco, (
        "o reject apaga o item e não reconta — items_count fica velho")
    assert '"items_count"' in bloco, (
        "recontou e não gravou o número novo no projeto")


def test_RECONTA_em_vez_de_subtrair_um():
    """🪤 `items_count - 1` supõe que o número de partida estava certo — e é
    exatamente o que a gente não pode assumir depois do caso dos 647."""
    bloco = _sem_comentarios(_bloco_do_reject())
    assert not re.search(r"items_count\s*[-+]\s*1", bloco), (
        "está fazendo aritmética em cima do contador velho em vez de recontar")


def test_so_grava_quando_a_contagem_e_um_NUMERO():
    """🪤 `_contar_itens_no_banco` devolve None quando não deu pra contar.
    Gravar None apagaria o contador — pior que deixá-lo velho."""
    bloco = _sem_comentarios(_bloco_do_reject())
    assert "isinstance(_n_apos, int)" in bloco, (
        "não checa o tipo: um None viraria items_count nulo")


def test_a_recontagem_NAO_derruba_a_exclusao_se_falhar():
    """A exclusão do cliente é o que importa. Se a recontagem falhar, ela não
    pode desfazer nem mascarar o delete que já aconteceu."""
    bloco = _bloco_do_reject()
    i = bloco.index("_n_apos = _contar_itens_no_banco")
    antes = bloco[:i]
    assert antes.rstrip().endswith("try:"), (
        "a recontagem não está no próprio try — uma falha dela mudaria o "
        "resultado do reject")
    assert "_escreveu = True" in antes, (
        "a recontagem tem que rodar DEPOIS de o delete ter dado certo")


# ── CONTROLES ──────────────────────────────────────────────────────────────
def test_CONTROLE_o_guarda_sabe_REPROVAR():
    """🧪 Reproduz o bloco ANTIGO (delete e nada mais) e confere que ele acusa."""
    antigo = "\n".join([
        '    if action == "reject":',
        "        try:",
        "            urllib.request.urlopen(req, timeout=15)",
        "            _escreveu = True",
        "        except Exception as e:",
        "            _supa_log(f'REVIEW reject ERR {e}')",
    ])
    limpo = _sem_comentarios(antigo)
    assert "_contar_itens_no_banco(job_id)" not in limpo, (
        "o controle não reproduz o comportamento antigo — o teste principal "
        "estaria guardando um problema que não existe")


def test_CONTROLE_o_APPROVE_e_o_EDIT_nao_mexem_no_contador():
    """Aprovar ou editar não muda a quantidade de linhas. Se o conserto tivesse
    vazado pra esses caminhos, todo salvamento recontaria o banco à toa."""
    src = _fonte()
    i = src.index('    if action in ("edit", "reject"):')
    depois = _sem_comentarios(src[i:i + 1800])
    assert "_contar_itens_no_banco" not in depois, (
        "a recontagem vazou pro caminho de edit/approve")


def test_CONTROLE_o_contador_reaproveitado_existe():
    """O conserto depende de `_contar_itens_no_banco`, que nasceu no mesmo dia
    pro guarda do persist. Se alguém remover, este caminho quebra junto."""
    assert "def _contar_itens_no_banco(job_id: str):" in _fonte()
