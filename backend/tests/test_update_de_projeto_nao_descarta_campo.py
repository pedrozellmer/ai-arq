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


# 🪤 ASPAS SIMPLES ERAM O FURO REAL. A 1ª versão deste varredor lia só
# `"campo":`; um dicionário escrito com `'campo':` era invisível pra ele —
# mesmo defeito, roupa nova, e o guarda verde. As três expressões abaixo
# aceitam as duas aspas de propósito.
_CHAVE = r'["\']([a-z_]+)["\']\s*:'
# 🪤 E o 3º argumento tem que ser um IDENTIFICADOR. Com `[^,]+` a expressão
# atravessava linhas e casava até com a menção a `_supabase_update("projects",
# "job_id",…)` dentro da DOCSTRING do `_projeto_patch` — um "chamador" de
# conjunto de chaves VAZIO, que passa em qualquer conferência por ser vazio.
_CHAMADA = (r'_supabase_update\(\s*"projects"\s*,\s*"job_id"\s*,'
            r'\s*[A-Za-z_]\w*\s*,\s*')


def _pacotes_enviados(src=None):
    """Todo `_supabase_update("projects","job_id",…)`: chaves do pacote.

    Lê dicionário INLINE e pacote em VARIÁVEL (`x = {...}` e `x["k"] = ...`),
    com aspas simples ou duplas."""
    src = _SRC if src is None else src
    achados = []
    linhas = src.splitlines()
    for m in re.finditer(_CHAMADA, src):
        n = src[:m.start()].count("\n")
        resto = src[m.end():m.end() + 900]
        var = re.match(r'([A-Za-z_]\w*)\s*\)', resto)
        if var:                                   # pacote em variável
            nome, chaves = var.group(1), set()
            for i in range(max(0, n - 40), n + 1):
                for bloco in re.findall(r'%s\s*=\s*\{([^}]*)\}' % re.escape(nome), linhas[i]):
                    chaves |= set(re.findall(_CHAVE, bloco))
                chaves |= set(re.findall(
                    r'%s\[["\']([a-z_]+)["\']\]\s*=' % re.escape(nome), linhas[i]))
            achados.append((n + 1, nome, chaves))
        else:                                     # dicionário inline
            prof, k = 0, m.end()
            while k < len(src):
                if src[k] == "{":
                    prof += 1
                elif src[k] == "}":
                    prof -= 1
                    if prof == 0:
                        break
                elif src[k] == ")" and prof == 0:
                    break
                k += 1
            achados.append((n + 1, "inline",
                            set(re.findall(_CHAVE, src[m.end():k + 1]))))
    return achados


# ── O guarda ───────────────────────────────────────────────────────────────
_META_DA_TELA = {
    "project_name": "Reforma do apartamento 402",
    "typology": "residential",
    "address": "Rua das Acacias, 100 - sala 3",
    "phase": "Projeto executivo",
}


def _salvar_meta_de_verdade(monkeypatch, campos):
    """Chama a rota /meta e devolve (resposta, o-que-foi-gravado, caminhos).

    🔑 Os dublês ficam no NÍVEL DO BANCO (`_supa_rest_service` e o `urlopen`
    das RPCs), não na rota. Assim a rota escolhe o caminho dela sozinha e a
    gente vê o que sobrou do outro lado — que é onde os quatro campos sumiam.
    """
    import asyncio, json, urllib.request
    import main as m
    gravado, caminhos = {}, []

    def _rest_falso(metodo, caminho, body=None, params=None, prefer=None, timeout=15):
        caminhos.append("%s %s" % (metodo, caminho))
        if metodo == "PATCH" and caminho.startswith("projects?job_id=eq."):
            gravado.update(body or {})
            return 204, None
        return 200, []

    class _RespFalsa:
        def read(self):
            return b"1"

    def _urlopen_falso(req, timeout=None):
        caminhos.append("POST %s" % req.full_url)
        corpo = json.loads((req.data or b"{}").decode("utf-8"))
        # cada RPC só GUARDA o que ela conhece; o resto ela descarta calada
        for k, v in corpo.items():
            if k == "p_job_id" or v is None:
                continue
            gravado[k[2:]] = v
        return _RespFalsa()

    monkeypatch.setattr(m, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(m, "_supa_rest_service", _rest_falso)
    monkeypatch.setattr(m, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(m, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_falso)

    resposta = asyncio.run(m.update_project_meta(
        "job-de-teste", m.ProjectMetaPayload(**campos), None))
    return resposta, gravado, caminhos


def test_NENHUM_update_de_projeto_manda_campo_que_a_RPC_descarta(monkeypatch):
    """🩸 A rota respondia 'ok' e o banco não mudava, desde 13/05/2026.

    🪤 O varredor de fonte lia `"campo":` com ASPAS DUPLAS. Um dicionário com
    aspas simples é invisível pra ele — mesmo defeito, roupa nova. Aqui a rota
    RODA e a pergunta é a de sempre: o que a tela mandou chegou no banco?
    """
    resposta, gravado, caminhos = _salvar_meta_de_verdade(monkeypatch, _META_DA_TELA)
    assert resposta.get("status") == "ok", resposta

    perdidos = {k: v for k, v in _META_DA_TELA.items() if gravado.get(k) != v}
    assert not perdidos, (
        "a rota devolveu OK e estes campos NÃO chegaram ao banco: %r.\n"
        "Gravado de verdade: %r\nCaminhos usados: %r"
        % (sorted(perdidos), gravado, caminhos))

    assert not [c for c in caminhos if "update_project_status" in c], (
        "os dados do projeto foram por `update_project_status`, que aceita 7 "
        "campos fixos, descarta o resto e AINDA devolve sucesso: %r" % caminhos)


def test_NENHUM_pacote_de_update_de_projeto_leva_campo_que_a_RPC_DESCARTA():
    """🩸 A REGRESSÃO DE COBERTURA QUE ISTO DESFAZ.

    O teste acima virou a execução de UMA rota (`/meta`) — necessário, e não
    suficiente. O invariante que fez este arquivo nascer vale pros **17**
    `_supabase_update("projects","job_id",…)` do main.py, e o caso 2 (o
    `/add-file`, com `files_count`/`file_types`) mora num deles. Trocar o
    varredor pela rota deixava o defeito de 13/05 voltar por uma porta vizinha
    com a bateria inteira verde: `address` não está entre os 7 campos da RPC,
    a rota responde "ok" e o banco não muda.

    🔑 Os dois, não um no lugar do outro: a rota prova o COMPORTAMENTO de um
    chamador, a varredura prova que nenhum dos outros 16 reabre o buraco.
    """
    aceitos = _campos_que_a_rpc_aceita()
    pacotes = _pacotes_enviados()
    assert len(pacotes) >= 15, (
        "a varredura encolheu de 17 pra %d chamadores — ou o main.py mudou "
        "muito, ou a expressão parou de enxergar" % len(pacotes))

    fora = [(ln, var, sorted(ch - aceitos)) for ln, var, ch in pacotes
            if ch - aceitos]
    assert not fora, (
        "estes `_supabase_update(\"projects\", …)` mandam campo que a RPC "
        "`update_project_status` DESCARTA em silêncio — e ela devolve sucesso, "
        "então quem chamou acha que gravou: %r.\nA RPC só aceita: %r"
        % (fora, sorted(aceitos)))

    # 🪤 Pacote VAZIO não é aprovação, é ponto cego: um chamador cujo
    # dicionário o varredor não conseguiu ler passaria por não ter chave
    # nenhuma pra reprovar. Foi exatamente assim que o meu primeiro varredor
    # disse "0 chamadores com problema" com dois defeitos reais no ar.
    cegos = [(ln, var) for ln, var, ch in pacotes if not ch]
    assert not cegos, (
        "o varredor não conseguiu ler o pacote destes chamadores — eles passam "
        "por serem ilegíveis, não por estarem certos: %r" % (cegos,))


def test_CONTROLE_o_varredor_enxerga_ASPAS_SIMPLES():
    """🧪 O furo real da 1ª versão. Sem este controle, alguém "conserta" o
    varredor pra aspas duplas de novo e o guarda de cima passa a absolver todo
    dicionário escrito com `'campo':`."""
    falso = ("    _supabase_update(\"projects\", \"job_id\", job_id,\n"
             "                     {'address': x, 'phase': y})\n")
    (_, forma, chaves), = _pacotes_enviados(falso)
    assert forma == "inline", forma
    assert chaves == {"address", "phase"}, (
        "o varredor voltou a ser cego pra aspas simples: %r" % (chaves,))

    variavel = ("    _pac = {'address': x}\n"
                "    _pac['phase'] = y\n"
                "    _supabase_update(\"projects\", \"job_id\", job_id, _pac)\n")
    (_, forma2, chaves2), = _pacotes_enviados(variavel)
    assert forma2 == "_pac", forma2
    assert chaves2 == {"address", "phase"}, (
        "o varredor voltou a ser cego pra aspas simples no pacote em "
        "variável: %r" % (chaves2,))


def test_CONTROLE_o_varredor_REPROVA_um_chamador_com_campo_descartado():
    """🧪 Controle positivo do guarda de cima: com um chamador plantado que
    manda `address`, a varredura tem que acusar."""
    falso = ('    _supabase_update("projects", "job_id", job_id,\n'
             '                     {"status": "done", "address": _end})\n')
    aceitos = _campos_que_a_rpc_aceita()
    fora = [sorted(ch - aceitos) for _, _, ch in _pacotes_enviados(falso)
            if ch - aceitos]
    assert fora == [["address"]], (
        "a varredura não reprovaria um chamador que manda campo fora da RPC: "
        "%r" % (fora,))


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
