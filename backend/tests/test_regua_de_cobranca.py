# -*- coding: utf-8 -*-
"""Só cobra o projeto que mediu pelo menos UMA linha do CAD.

🚨 06/09/2026 — a régua que o Pedro aprovou pra sair do beta, depois da
auditoria de prontidão. O que ela resolve, medido no banco:

· A entrega é uma RIFA. Em setembro, 12 de 21 entregas saíram com ZERO linha
  medida (mediana de 0,0% de linhas medidas por projeto), enquanto o melhor
  projeto do mês mediu 88 de 108. Os dois pagariam os mesmos R$97 e nenhum dos
  dois tinha como saber, antes de pagar, de que lado ia cair.
· Desde 14/07, 41 clientes receberam "sua planilha está pronta" com zero linha
  medida. Com cobrança ligada, cada um desses e-mails é um pedido de reembolso.
· E o reembolso não teria pra onde ir: `contact_messages` tem 1 linha na vida
  (teste do próprio Pedro) e não existe a palavra "reembolso" nos Termos.

A régua converte o pior risco de reembolso em NÃO-COBRANÇA automática — a única
forma de devolução que não precisa de suporte humano.

Este arquivo guarda três invariantes:
  (1) o carimbo diz a verdade sobre o que foi entregue;
  (2) NULL ("não avaliado") nunca se confunde com false ("não cobra");
  (3) a régua NUNCA derruba a entrega de um projeto.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


def _capturar(monkeypatch):
    """Troca a escrita no banco por um coletor. Devolve a lista de updates.

    🩸 Espiona `_projeto_patch`, NÃO `_supabase_update`. O carimbo nasceu usando
    o segundo e nasceu MORTO: para a tabela `projects`, `_supabase_update`
    roteia pra RPC `update_project_status`, que aceita 7 parâmetros fixos e
    descarta o resto EM SILÊNCIO — devolvendo sucesso. Quem pegou foi um guarda
    que já existia na casa (test_update_de_projeto_nao_descarta_campo), escrito
    depois de o mesmo defeito matar `planilha_gerada_em` em agosto.
    """
    chamadas = []

    def _falso(job_id, campos):
        chamadas.append({"valor": job_id, "dados": campos})
        return True
    monkeypatch.setattr(main, "_projeto_patch", _falso)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    return chamadas


# ─────────────────────────────────────────────────────────────────────────────
#  (1) O carimbo diz a verdade
# ─────────────────────────────────────────────────────────────────────────────

def test_projeto_que_mediu_UMA_linha_e_cobravel(monkeypatch):
    """Uma linha basta. Não é 'mediu bem', é 'mediu alguma coisa do CAD'."""
    ch = _capturar(monkeypatch)
    main._carimbar_regua_de_cobranca("aaa111", 1, 80)
    assert len(ch) == 1
    d = ch[0]["dados"]
    assert d["cobravel"] is True, d
    assert d["linhas_medidas"] == 1 and d["linhas_total"] == 80


def test_projeto_com_ZERO_medida_NAO_e_cobravel(monkeypatch):
    """O caso que a régua existe pra pegar: 161 linhas, nenhuma medida."""
    ch = _capturar(monkeypatch)
    main._carimbar_regua_de_cobranca("bbb222", 0, 161)
    d = ch[0]["dados"]
    assert d["cobravel"] is False, d
    assert d["linhas_medidas"] == 0 and d["linhas_total"] == 161


def test_o_carimbo_grava_no_projeto_certo(monkeypatch):
    """🪤 Carimbar o projeto errado é pior que não carimbar: cobraria alguém
    por uma entrega que não foi dele."""
    ch = _capturar(monkeypatch)
    main._carimbar_regua_de_cobranca("ccc333", 5, 40)
    assert ch[0]["valor"] == "ccc333"


def test_o_carimbo_guarda_QUANDO_foi_avaliado(monkeypatch):
    """Sem a data não dá pra saber se o carimbo é do momento da entrega ou de
    uma avaliação retroativa — e os dois convivem no banco."""
    ch = _capturar(monkeypatch)
    main._carimbar_regua_de_cobranca("ddd444", 3, 30)
    assert "cobravel_em" in ch[0]["dados"], ch[0]["dados"]


def test_CONTROLE_o_coletor_enxerga_a_ausencia_de_carimbo(monkeypatch):
    """Os testes acima só valem se o coletor não inventar chamada sozinho."""
    ch = _capturar(monkeypatch)
    assert ch == []


# ─────────────────────────────────────────────────────────────────────────────
#  (2) A régua não derruba a entrega
# ─────────────────────────────────────────────────────────────────────────────

def test_banco_fora_do_ar_NAO_derruba_a_entrega(monkeypatch):
    """🚨 A régua é dinheiro, a entrega é o produto. Se a gravação falhar, o
    cliente TEM que receber a planilha do mesmo jeito — e o projeto fica com
    `cobravel` NULL, que quer dizer 'não avaliado', não 'não cobra'."""
    def _explode(*a, **k):
        raise RuntimeError("banco fora do ar")
    monkeypatch.setattr(main, "_projeto_patch", _explode)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._carimbar_regua_de_cobranca("eee555", 7, 50)   # não pode levantar


def test_gravacao_recusada_avisa_em_vez_de_passar_batido(monkeypatch):
    """`_projeto_patch` devolvendo False é falha silenciosa clássica: sem
    aviso, o projeto fica NULL pra sempre e ninguém sabe por quê."""
    avisos = []
    monkeypatch.setattr(main, "_projeto_patch", lambda *a, **k: False)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: avisos.append((stage, msg)))
    main._carimbar_regua_de_cobranca("fff666", 4, 40)
    assert any(s == "cobranca:regua" for s, _ in avisos), avisos


def test_CONTROLE_sem_o_try_a_falha_SUBIRIA(monkeypatch):
    """Prova que é o try/except que segura, e não um caminho que não executa."""
    def _explode(*a, **k):
        raise RuntimeError("banco fora do ar")
    try:
        _explode()
    except RuntimeError:
        return
    raise AssertionError("o simulador de falha parou de falhar")


# ─────────────────────────────────────────────────────────────────────────────
#  (3) A régua está LIGADA no motor, e o aviso não entope o painel
# ─────────────────────────────────────────────────────────────────────────────

def test_a_regua_e_chamada_no_fim_do_processamento():
    """Guarda de FATO, não de forma: a função existe, é chamada, e o número que
    ela recebe vem de uma CONTAGEM de itens `confirmado` — não de um literal."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "def _carimbar_regua_de_cobranca(" in src, "a régua sumiu"
    chamadas = re.findall(r"_carimbar_regua_de_cobranca\(([^)]*)\)", src)
    reais = [c for c in chamadas if "job_id: str" not in c]
    assert reais, "a régua existe mas ninguém a chama — carimbo morto"
    for c in reais:
        args = [a.strip() for a in c.split(",")]
        assert len(args) >= 2, "chamada da régua sem o número de medidas: %r" % c
        assert not args[1].isdigit(), (
            "a régua está sendo alimentada por um número solto (%r) em vez da "
            "contagem real de linhas medidas" % args[1])
    # e a variável que alimenta tem que nascer de uma contagem de 'confirmado'
    nomes = {a.split(",")[1].strip() for a in reais if len(a.split(",")) > 1}
    for nome in nomes:
        m = re.search(re.escape(nome) + r"\s*=\s*sum\((.{0,400}?)\)" + chr(10),
                      src, re.S)
        assert m and "confirmado" in m.group(1), (
            "%s não vem de uma contagem de itens com confidence='confirmado' — "
            "a régua estaria carimbando outra coisa" % nome)


def test_a_regua_NAO_mora_dentro_do_bloco_de_EMAIL():
    """🩸 06/09/2026 — o defeito que eu mesmo escrevi e peguei relendo o diff.

    A régua nasceu junto do `_n_med` que o e-mail já contava — e ali dentro de
    `if _pe and not is_complement and not _is_reproc:`. Ou seja: não carimbaria
    quem não tem e-mail, não carimbaria complemento e, pior, não carimbaria
    REPROCESSO — que é justamente o caso em que um projeto que não media passa
    a medir. Esses projetos ficariam `cobravel = NULL` para sempre.

    A régua é do PROJETO, não do e-mail. Este guarda prende isso: a chamada tem
    que estar ANTES do primeiro bloco condicional de e-mail do process_job.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    pos_regua = src.index("_carimbar_regua_de_cobranca(job_id")
    # o segundo índice é a chamada (o primeiro é a def)
    pos_regua = src.index("_carimbar_regua_de_cobranca(job_id",
                          src.index("def _carimbar_regua_de_cobranca") + 10)
    # 🪤 A busca crua achava o COMENTÁRIO que explica este próprio defeito
    # (main.py:12666 cita a condição para contar a história) e reprovava o
    # código correto. Guarda que lê o fonte tem que separar código de comentário
    # — é o mesmo erro que o guarda da allowlist já cometeu em 03/09.
    m_email = re.search(r"^\s+if _pe and not is_complement", src, re.M)
    assert m_email, "o bloco de e-mail do process_job sumiu; ajuste este guarda"
    pos_email = m_email.start()
    assert pos_regua < pos_email, (
        "a régua voltou pra dentro do caminho do e-mail — quem não tem e-mail, "
        "complemento e reprocesso ficariam sem carimbo")

    # e tem que estar colada no ponto em que o projeto vira 'done'
    pos_done = src.index('jobs.update_field(job_id, status="done")')
    assert 0 < (pos_regua - pos_done) < 1500, (
        "a régua se afastou do ponto em que o projeto é concluído (%d chars) — "
        "é ali que ela tem que carimbar" % (pos_regua - pos_done))


def test_o_aviso_da_regua_NAO_entope_o_painel_de_erros():
    """🪤 Uma linha por projeto não medido. O painel 'Erros do motor' já foi
    tomado por bookkeeping antes (20 das 40 linhas, em 30/08)."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_STAGES_DIAGNOSTICO = frozenset({")
    bloco = src[i:src.index("})", i)]
    assert '"cobranca:regua"' in bloco, (
        "o stage da régua não está na lista de diagnóstico — vai empurrar erro "
        "de verdade pra fora do painel")


# ─────────────────────────────────────────────────────────────────────────────
#  (4) NULL não é false — nem no banco, nem na tela
# ─────────────────────────────────────────────────────────────────────────────

def test_a_tela_separa_NAO_AVALIADA_de_NAO_COBRA():
    """🚨 'vazio não é falhou'. Somar as não avaliadas ao lado do 'não cobra'
    faria a régua parecer pior do que é — e transformaria ausência de medição
    numa afirmação, que é o que a regra dura nº1 proíbe."""
    admin = os.path.join(_RAIZ, "admin.html")
    if not os.path.isfile(admin):
        admin = os.path.join(os.path.dirname(_BACKEND), "admin.html")
    src = io.open(admin, encoding="utf-8").read()
    i = src.index("function _blocoRegua(")
    bloco = src[i:src.index("\nfunction ", i + 10)]
    assert "nao_avaliadas" in bloco, (
        "a tela da régua parou de ler o contador de entregas não avaliadas")
    assert "não avaliada" in bloco, (
        "a tela não mostra ao Pedro quantas entregas ficaram sem avaliação")


def test_a_coluna_do_banco_documenta_os_TRES_estados():
    """Quem for ler `cobravel` daqui a seis meses precisa saber que NULL existe
    e o que ele significa. O comentário da coluna é onde isso mora."""
    # o comentário foi escrito na migration; aqui garanto que o código que
    # ESCREVE a coluna nunca grava string vazia ou 0 no lugar de booleano
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _carimbar_regua_de_cobranca(")
    corpo = src[i:src.index("\ndef ", i + 10)]
    assert 'bool(n_medidas > 0)' in corpo, (
        "o carimbo deixou de gravar booleano — 0/1/'' viram armadilha na "
        "leitura, porque só o booleano distingue os três estados")


def test_CONTROLE_o_recorte_do_bloco_da_tela_ACHA_o_alvo():
    falso = "x\nfunction _blocoRegua(){\n  const d = COSTS_REGUA;\n}\nfunction outra(){}"
    i = falso.index("function _blocoRegua(")
    bloco = falso[i:falso.index("\nfunction ", i + 10)]
    assert "COSTS_REGUA" in bloco and "outra" not in bloco, bloco
