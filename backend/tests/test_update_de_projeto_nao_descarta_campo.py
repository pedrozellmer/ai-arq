# -*- coding: utf-8 -*-
"""`_supabase_update("projects", …)` descarta campo em silêncio — e devolve OK.

🩸 03/09/2026. `_supabase_update` não faz UPDATE em `projects`: ele roteia pra
RPC `update_project_status`, que aceita SETE campos fixos. Qualquer outro campo
do pacote cai fora — e, como o pacote costuma levar `status` junto, a RPC
devolve SUCESSO. Quem chamou acha que gravou.

Dois casos reais, achados pela varredura "o que mais nasce morto":

**1. `/api/projects/{job}/meta` NUNCA SALVOU NADA** — no ar desde 13/05/2026.
É o formulário "salvar dados do projeto" de `projeto.html` (`saveProjectAndClient`,
linha 2228): nome, tipologia, endereço e fase. Os QUATRO campos caem fora. A
tela diz "Salvando…", o cliente vê OK, e o banco não muda.
📏 De 157 projetos de cliente: 2 têm endereço, 2 têm fase, 60 seguem com o nome
genérico "Projeto <data>".

**2. O conserto do `/add-file` de 31/07 nunca funcionou.** O bloco existe pra
corrigir "o painel mostra 1 PDF num projeto que já tem CAD" (caso Fernando) — e
mandava `files_count`/`file_types` pelo mesmo caminho que os descarta. 5
projetos de cliente afetados; o pior mostra "1 prancha" com 18 DWG no Storage,
e dois seguem contados como PDF puro na estatística PDF × CAD.

🪤 O MEU PRIMEIRO VARREDOR DISSE "0 CHAMADORES COM PROBLEMA" — e era falso: ele
só lia dicionário inline e os dois casos passam o pacote por VARIÁVEL. O guarda
abaixo lê as duas formas, porque instrumento que enxerga metade do território
dá verde exatamente onde dói (é a lição do dia inteiro).
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import corpo_de, fonte, sem_comentarios     # noqa: E402

_SRC = fonte("main.py")


def _campos_que_a_rpc_aceita():
    """Lê do PRÓPRIO `_supabase_update` quais `p_*` a RPC recebe.

    🪤 Fixar a lista aqui apodrece: no dia em que a RPC ganhar um campo, o
    guarda passa a reprovar quem está certo. A fonte é o código."""
    # 🪤 O payload NÃO mora em `_supabase_update` — ele delega pra
    # `_rpc_update_project_status`, que é quem monta os `p_*`. A 1ª versão
    # deste helper lia a função errada e devolvia CONJUNTO VAZIO; o guarda
    # de baixo (a lista não pode estar vazia) foi quem pegou.
    corpo = corpo_de("_rpc_update_project_status")
    return {k[2:] for k in re.findall(r'"(p_[a-z_]+)"\s*:', corpo)} - {"job_id"}


def _pacotes_enviados():
    """Todo `_supabase_update("projects","job_id",…)`: chaves do pacote.

    Lê dicionário INLINE e pacote em VARIÁVEL (`x = {...}` e `x["k"] = ...`)."""
    achados = []
    linhas = _SRC.splitlines()
    for m in re.finditer(
            r'_supabase_update\(\s*"projects"\s*,\s*"job_id"\s*,\s*[^,]+,\s*',
            _SRC):
        n = _SRC[:m.start()].count("\n")
        resto = _SRC[m.end():m.end() + 900]
        var = re.match(r'([A-Za-z_]\w*)\s*\)', resto)
        if var:                                   # pacote em variável
            nome, chaves = var.group(1), set()
            for i in range(max(0, n - 40), n + 1):
                for bloco in re.findall(r'%s\s*=\s*\{([^}]*)\}' % re.escape(nome), linhas[i]):
                    chaves |= set(re.findall(r'"([a-z_]+)"\s*:', bloco))
                chaves |= set(re.findall(r'%s\["([a-z_]+)"\]\s*=' % re.escape(nome), linhas[i]))
            achados.append((n + 1, nome, chaves))
        else:                                     # dicionário inline
            prof, k = 0, m.end()
            while k < len(_SRC):
                if _SRC[k] == "{":
                    prof += 1
                elif _SRC[k] == "}":
                    prof -= 1
                    if prof == 0:
                        break
                elif _SRC[k] == ")" and prof == 0:
                    break
                k += 1
            achados.append((n + 1, "inline",
                            set(re.findall(r'"([a-z_]+)"\s*:', _SRC[m.end():k + 1]))))
    return achados


# ── O guarda ───────────────────────────────────────────────────────────────
def test_NENHUM_update_de_projeto_manda_campo_que_a_RPC_descarta():
    """🩸 Os dois casos reais. Se este teste cair, alguém voltou a gravar num
    caminho que responde OK e não grava."""
    aceitos = _campos_que_a_rpc_aceita()
    ruins = [(n, var, sorted(ch - aceitos)) for n, var, ch in _pacotes_enviados()
             if ch - aceitos]
    assert not ruins, (
        "estes updates mandam campo que a RPC update_project_status DESCARTA "
        "em silêncio (e ainda devolve sucesso): %r.\nUse _projeto_patch pra "
        "esses campos — ele faz PATCH direto na tabela." % ruins)


def test_CONTROLE_o_guarda_ACHA_os_dois_formatos_de_pacote():
    """🧪 O meu primeiro varredor achou ZERO porque só lia dicionário inline —
    e os dois defeitos reais usavam variável. Guarda que enxerga metade do
    território dá verde exatamente onde dói."""
    formas = {var for _, var, _ in _pacotes_enviados()}
    assert "inline" in formas, "parou de ler dicionário escrito na chamada"
    assert formas - {"inline"}, "parou de ler pacote passado por variável"
    assert len(_pacotes_enviados()) >= 8, "a varredura encolheu"


def test_CONTROLE_a_lista_da_RPC_vem_do_CODIGO_e_nao_esta_vazia():
    """🪤 Se a leitura falhar e devolver conjunto vazio, o guarda acima passa a
    reprovar TUDO (ruído) ou, pior, a comparação vira sem sentido."""
    aceitos = _campos_que_a_rpc_aceita()
    assert "status" in aceitos and "warnings" in aceitos, aceitos
    assert 5 <= len(aceitos) <= 15, aceitos


# ── Os dois consertos ──────────────────────────────────────────────────────
def test_a_rota_meta_grava_pelo_patch_direto():
    """🩸 Nome, tipologia, endereço e fase — nada disso salvava desde 13/05."""
    corpo = sem_comentarios(corpo_de("update_project_meta"))
    assert "_projeto_patch(job_id, updates)" in corpo, (
        "a rota voltou a gravar pelo caminho que descarta os campos")
    assert "_supabase_update(" not in corpo, (
        "sobrou a escrita antiga na rota — cópia velha ao lado da nova")


def test_o_add_file_separa_status_da_COMPOSICAO():
    """O status continua pela RPC (é pra isso que ela existe); a composição do
    projeto vai pelo patch direto."""
    src = sem_comentarios(_SRC)
    assert '_projeto_patch(job_id, {"file_types": _comp,' in src, (
        "files_count/file_types voltaram a ir pelo caminho que os descarta")
    assert '{"status": "queued", "error_message": None})' in src, (
        "o status deixou de ir pela RPC")


def test_CONTROLE_a_checagem_sabe_REPROVAR():
    falso = '_supabase_update("projects", "job_id", job_id, {"address": "x"})'
    assert "address" in set(re.findall(r'"([a-z_]+)"\s*:', falso))
    assert "address" not in _campos_que_a_rpc_aceita()
