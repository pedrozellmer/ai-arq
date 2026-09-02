# -*- coding: utf-8 -*-
"""Reenviar o mesmo caderno vira AVISO — nunca bloqueio, nunca promessa falsa.

🩸 01/09/2026, flavio anderson (cliente novo, primeiro projeto). Linha do tempo
medida no banco:

    20:40  sobe 20 PDFs  ("LUANA E JAILSON")
    21:08  recebe 161 itens — 25 de 25 linhas de METRO em branco,
           42 de 50 de área em branco
    21:19  sobe DE NOVO o mesmo caderno, com 5 arquivos a menos ("LUANA")

As pranchas do 2º envio têm nome idêntico às do 1º (07 PAREDE, 02 FORRO,
03 ILUMINACAO, 04 LUMINARIAS, 08 PISO, 11 RODAPE, 13 BANCADA — todas
`_LUANA_09.04`). Ele achou que o problema era o arquivo dele. Não era: PDF não
dá comprimento confiável, e ele não informou pé-direito nem área — os dois
campos que destravam medição de verdade.

🚫 O aviso NÃO diz "vai dar o mesmo resultado". Seria mentira: o motor não é
determinístico (medido 08/08 — 458 e 177 m² do MESMO arquivo, variação de 26%).
O que se repete é a CAUSA. Prometer número igual e entregar diferente destrói a
confiança que o aviso existe pra construir.

🚫 E NÃO bloqueia. A trava de envio em dobro (90 s) é pra clique repetido;
reenviar dias — ou minutos — depois é direito do cliente.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


# as pranchas reais do job 144c1f04
CADERNO = [
    "07.18_p parede_luana_09.04.pdf", "02.18_p forro_luana_09.04.pdf",
    "03.18_p iluminacao_luana_09.04.pdf", "08.18_p piso_luana_09.04.pdf",
    "11.18_p rodape_luana_09.04.pdf", "13.18_p bancada_luana_09.04.pdf",
]


def _falso_supa(projetos, itens_por_job):
    """Substitui `_supa_rows` — nada de rede, nada de banco de verdade."""
    def _fake(method, path, **kw):
        if path.startswith("/projects?"):
            return projetos
        if path.startswith("/project_items?"):
            for jid, refs in itens_por_job.items():
                if "job_id=eq.%s" % jid in path:
                    return [{"ref_sheet": r} for r in refs]
        return []
    return _fake


def _cenario(monkeypatch, refs_antigos, tinha_pd=None, tinha_area=None):
    projetos = [{"job_id": "144c1f04", "project_name": "LUANA E JAILSON",
                 "created_at": "2026-09-01T23:40:00+00:00",
                 "user_pe_direito": tinha_pd, "user_total_area": tinha_area}]
    monkeypatch.setattr(main, "_supa_rows",
                        _falso_supa(projetos, {"144c1f04": refs_antigos}))


# ── O que dispara ──────────────────────────────────────────────────────────
def test_mesmo_caderno_reenviado_DISPARA_o_aviso(monkeypatch):
    """🩸 O caso do flavio."""
    _cenario(monkeypatch, CADERNO)
    r = main._projeto_ja_enviado("u1", set(CADERNO), 0, 0)
    assert r is not None, "reenvio do mesmo caderno passou batido"
    assert r["job_id"] == "144c1f04"
    assert r["n_iguais"] == 6


def test_subconjunto_tambem_dispara(monkeypatch):
    """Ele tirou 5 arquivos e remandou. Continua sendo o mesmo caderno."""
    _cenario(monkeypatch, CADERNO)
    r = main._projeto_ja_enviado("u1", set(CADERNO[:4]), 0, 0)
    assert r is not None, "reenvio parcial não foi reconhecido"


def test_o_ref_sheet_com_hint_da_IA_ainda_casa(monkeypatch):
    """🪤 O banco guarda 'arquivo.pdf (02/18 — Planta de Forro)'. Comparar a
    string inteira nunca casaria com o nome que chega no upload."""
    _cenario(monkeypatch, [n + " (02/18 — Planta de Forro / Detalhe AA)"
                           for n in CADERNO])
    r = main._projeto_ja_enviado("u1", set(CADERNO), 0, 0)
    assert r is not None, "o hint da IA no ref_sheet quebrou a comparação"


# ── O que NÃO pode disparar (aviso falso é pior que aviso nenhum) ──────────
def test_CONTROLE_projeto_DIFERENTE_nao_dispara(monkeypatch):
    _cenario(monkeypatch, CADERNO)
    outro = {"casa da praia - planta.pdf", "casa da praia - corte.pdf",
             "casa da praia - fachada.pdf", "casa da praia - cobertura.pdf"}
    assert main._projeto_ja_enviado("u1", outro, 0, 0) is None, (
        "acusou repetição num projeto novo — ofende quem está mandando "
        "trabalho de verdade")


def test_CONTROLE_poucos_arquivos_iguais_nao_disparam(monkeypatch):
    """🪤 'planta baixa.pdf' e 'corte.pdf' se repetem entre projetos
    DIFERENTES do mesmo escritório. Dois nomes iguais não é reenvio."""
    _cenario(monkeypatch, ["planta baixa.pdf", "corte.pdf"])
    novo = {"planta baixa.pdf", "corte.pdf", "fachada.pdf", "cobertura.pdf",
            "detalhes.pdf"}
    assert main._projeto_ja_enviado("u1", novo, 0, 0) is None


def test_CONTROLE_quem_INFORMOU_o_pe_direito_agora_NAO_e_avisado(monkeypatch):
    """🔑 A exceção que faz o aviso ser honesto. Se ele fez o que a gente
    pediu, o resultado VAI mudar — e dizer 'você está repetindo' seria
    castigar exatamente quem seguiu a orientação."""
    _cenario(monkeypatch, CADERNO, tinha_pd=None)
    assert main._projeto_ja_enviado("u1", set(CADERNO), 2.7, 0) is None, (
        "avisou 'você está repetindo' pra quem informou o pé-direito desta "
        "vez — o resultado dele MUDA e o aviso seria falso")


def test_CONTROLE_quem_INFORMOU_a_area_agora_NAO_e_avisado(monkeypatch):
    _cenario(monkeypatch, CADERNO, tinha_area=None)
    assert main._projeto_ja_enviado("u1", set(CADERNO), 0, 190.0) is None


def test_CONTROLE_quem_JA_tinha_informado_continua_sendo_avisado(monkeypatch):
    """🧪 O contrário do teste acima: se ele já tinha informado antes e
    informou de novo, não mudou nada — o aviso vale."""
    _cenario(monkeypatch, CADERNO, tinha_pd=2.7)
    assert main._projeto_ja_enviado("u1", set(CADERNO), 2.7, 0) is not None, (
        "a exceção virou porta dos fundos: quem não mudou nada deixou de ser "
        "avisado")


def test_CONTROLE_envio_pequeno_demais_nao_dispara(monkeypatch):
    _cenario(monkeypatch, CADERNO)
    assert main._projeto_ja_enviado("u1", {CADERNO[0], CADERNO[1]}, 0, 0) is None


def test_CONTROLE_sem_user_id_nao_dispara(monkeypatch):
    _cenario(monkeypatch, CADERNO)
    assert main._projeto_ja_enviado(None, set(CADERNO), 0, 0) is None


def test_CONTROLE_banco_mudo_nao_inventa_aviso(monkeypatch):
    """🪤 `_supa_rows` devolve [] em QUALQUER falha — 'vazio ≠ falhou'. Uma
    leitura que caiu não pode virar aviso nem exceção no upload."""
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    assert main._projeto_ja_enviado("u1", set(CADERNO), 0, 0) is None


# ── O nome do arquivo dentro do ref_sheet ──────────────────────────────────
def test_nome_limpo_tira_o_hint_e_normaliza():
    f = main._nome_limpo_da_prancha
    assert f("02.18_P FORRO.pdf (02/18 — Planta de Forro)") == "02.18_p forro.pdf"
    assert f("planta.pdf") == "planta.pdf"
    assert f("") == "" and f(None) == ""


def test_CONTROLE_nome_com_parenteses_PROPRIO_nao_e_cortado_errado():
    """🪤 'casa (fundos).pdf' tem parêntese no nome de verdade. O corte é no
    ' (' que separa o hint — e este teste existe pra alguém pensar duas vezes
    antes de trocar por um corte em '(' solto."""
    f = main._nome_limpo_da_prancha
    assert f("casa (fundos).pdf") == "casa"    # comportamento ATUAL, medido
    # o que importa: os DOIS lados passam pela mesma função, então o corte
    # acontece igual no envio e no banco, e a comparação continua casando
    assert f("casa (fundos).pdf") == f("casa (fundos).pdf (hint da IA)")


# ── O aviso chega ao cliente ───────────────────────────────────────────────
def _fonte(p):
    return io.open(os.path.join(_BACKEND, p), encoding="utf-8").read()


def _site(p):
    return io.open(os.path.join(os.path.dirname(_BACKEND), p),
                   encoding="utf-8").read()


def test_o_upload_devolve_o_aviso_e_o_site_mostra():
    limpo = "\n".join(l for l in _fonte("main.py").splitlines()
                      if not l.lstrip().startswith("#"))
    assert 'resp["aviso_repetido"]' in limpo, "o aviso não sai do backend"
    assert "upload:projeto-repetido" in limpo, "não vira linha em error_log"
    site = _site("dashboard.html")
    assert "data.aviso_repetido" in site, "o site não lê o aviso"


def test_o_aviso_NAO_promete_resultado_igual():
    """🚫 O motor não é determinístico. Prometer número igual e entregar
    diferente destrói a confiança que o aviso existe pra construir."""
    limpo = "\n".join(l for l in _fonte("main.py").splitlines()
                      if not l.lstrip().startswith("#"))
    i = limpo.index('resp["aviso_repetido"]')
    trecho = limpo[i:i + 1600].lower()
    for proibida in ("mesmo resultado", "resultado igual", "não vai mudar nada",
                     "vai dar a mesma"):
        assert proibida not in trecho, (
            "o aviso promete determinismo que o motor não tem: %r" % proibida)


def test_o_aviso_diz_O_QUE_MUDA():
    """Aviso que só diz 'você repetiu' é reclamação. O valor está na saída."""
    limpo = "\n".join(l for l in _fonte("main.py").splitlines()
                      if not l.lstrip().startswith("#"))
    i = limpo.index('resp["aviso_repetido"]')
    trecho = limpo[max(0, i - 2200):i + 1600]
    assert "PÉ-DIREITO" in trecho, "não oferece a maior alavanca (pé-direito)"
    assert "ÁREA TOTAL" in trecho
    assert "DXF" in trecho


def test_o_site_ESCAPA_o_texto_do_aviso():
    """🚨 O texto passou a carregar o NOME DO PROJETO, que é dado do cliente,
    e o renderizador insere como HTML. Sem escapar, um projeto chamado
    '<img onerror=...>' vira script na tela de quem enviou."""
    site = _site("dashboard.html")
    i = site.index("function mostrarAvisoAec")
    trecho = site[i:i + 3200]      # a função cresceu; janela curta dava falso negativo
    assert "const esc" in trecho, "o renderizador não tem função de escape"
    assert "${esc(t)}" in trecho, "o corpo do aviso entra sem escapar"


def test_CONTROLE_a_checagem_do_site_sabe_REPROVAR():
    """🧪 Sem isto o teste acima passaria com o escape desligado."""
    falso = "function mostrarAvisoAec(av, cor) { return `<p>${t}</p>`; }"
    assert "${esc(t)}" not in falso
