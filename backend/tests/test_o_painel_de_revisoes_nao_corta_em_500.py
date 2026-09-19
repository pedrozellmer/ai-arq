# -*- coding: utf-8 -*-
"""O painel de revisões conta o acervo INTEIRO — o teto de 500 já cortava.

🩸 19/09/2026 — item 13 da fila. A rota `/api/admin/revision-feedback` lia
`item_reviews` com `?order=reviewed_at.desc&limit=500`. Quando a fila anotou o
risco o acervo tinha **433** registros e o teto parecia folgado. Medido hoje:

    no banco ............................ 624
    dentro da janela de 500 ............. 500
    JOGADOS FORA EM SILÊNCIO ............ 124  (20%)
    crescimento .................. ~193 por semana

Dos 124 fora: 75 `approve` e 49 `edit`. **Nenhum `reject`, nenhum `faltou`,
nenhum recado humano** — os sinais raros ainda estavam dentro da janela. Em uma
semana não estariam. O defeito, hoje, era as CONTAGENS mentirem para menos.

🔑 A conta passou para o banco (RPC `admin_revisao_inline`, cópia comentada em
`migrations_pendentes/`). Duas coisas que este arquivo protege:

  1. 🪤 A RÉGUA DO RECADO CONTINUA NUM LUGAR SÓ. Quem sabe distinguir o texto
     que o cliente escreveu do texto que a NOSSA tela escreve é
     `recado_digitado` — reimplementá-la em SQL criaria uma segunda verdade que
     diverge calada. Como só 8 registros em 624 têm texto, a RPC devolve TODOS
     e o Python decide.
  2. 🪤 LEITURA FALHADA ≠ ACERVO VAZIO. Se a RPC cai, a ficha diz "não consegui
     ler", nunca zero — é a mesma lição do `volume` de 31/08.

🚫 Não cobre a SQL da RPC (a bancada não roda SQL).
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _jsbancada import funcao_js, motor  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "admin.html")


# ─────────────────────────────────────────────────────────────────────────────
#  (1) O backend: conta no banco, sem teto
# ─────────────────────────────────────────────────────────────────────────────

# 🔑 As listas vêm CRUAS da RPC, como a tabela tem — quem monta o retrato é o
# Python, porque a bancada não roda SQL e os guardas de 31/08 e 05/09 precisam
# EXECUTAR essa montagem.
_RPC = {
    "total_no_banco": 624, "aprovacoes": 301, "edicoes": 122,
    "exclusoes": 200, "faltou": 1, "projetos": 38,
    "exclusoes_cruas": [{"job_id": "aaa11111", "item_id": "i1", "action": "reject",
                         "reviewed_at": "2026-09-18T12:00:00Z", "comment": "",
                         "edits": {"_antes": {"description": "Poço de visita",
                                              "unit": "un", "quantity": 2,
                                              "discipline": "Hidráulicas",
                                              "confidence": "estimado"}}}],
    "faltou_cruas": [{"job_id": "bbb22222", "item_id": "i2", "action": "faltou",
                      "reviewed_at": "2026-09-10T12:00:00Z",
                      "comment": "faltou o rodapé do hall", "edits": {}}],
    "edits_crus": [{"job_id": "ccc33333", "item_id": "i3", "action": "edit",
                    "reviewed_at": "2026-09-17T12:00:00Z",
                    "edits": {"quantity": 12}, "comment": ""}],
    # 8 em 624 têm texto; só UM é de gente.
    "candidatos_a_recado": [
        {"job_id": "ddd44444", "item_id": "i4", "action": "approve",
         "reviewed_at": "2026-09-02T19:30:00Z", "edits": {},
         "comment": "faça a separação dos tipo, cada um para cada item"},
        {"job_id": "eee55555", "item_id": "i5", "action": "approve",
         "reviewed_at": "2026-09-01T10:00:00Z", "edits": {},
         "comment": "Usuário marcou como EXISTENTE"},
    ],
}


def _rota(monkeypatch, resposta=(200, _RPC), feedback=(200, [])):
    import main
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: resposta)

    import json as _j
    import urllib.request as _u

    class _R:
        def read(self):
            return _j.dumps(feedback[1]).encode()

    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: _R())
    return main.admin_revision_feedback(request=None)


def test_a_conta_e_do_ACERVO_INTEIRO_nao_das_500_ultimas(monkeypatch):
    """🚨 O número que o teto escondia. 624 no banco, e o painel dizia 500."""
    ri = _rota(monkeypatch)["revisao_inline"]
    assert ri["total_no_banco"] == 624, ri
    assert ri["aprovacoes"] == 301 and ri["edicoes"] == 122, ri
    assert ri["exclusoes"] == 200, "as exclusões são o sinal mais direto de erro do motor"
    assert ri["projetos"] == 38, ri
    assert ri["aprovacoes"] + ri["edicoes"] + ri["exclusoes"] + ri["faltou"] == 624


def test_a_regua_do_RECADO_continua_no_Python(monkeypatch):
    """🪤 Dos 8 registros com texto, só um é de gente — o resto é a frase que a
    NOSSA tela escreve. Quem separa é `recado_digitado`; a RPC não tenta."""
    ri = _rota(monkeypatch)["revisao_inline"]
    assert ri["recados"] == 1, ri["recados_itens"]
    assert "separação dos tipo" in ri["recados_itens"][0]["texto"]
    assert all("marcou como EXISTENTE" not in (r.get("texto") or "")
               for r in ri["recados_itens"])


def test_as_listas_raras_chegam_inteiras(monkeypatch):
    """Exclusão, "faltou" e recado são raros por natureza — vão inteiros, com o
    retrato do que foi apagado (o item já não existe em project_items).

    🔑 E a MONTAGEM do retrato acontece no Python: este guarda executa
    `_antes_do_item`. Na 1ª versão do conserto ela morava no SQL e este teste
    ficava verde sem provar nada — a revisão pegou."""
    ri = _rota(monkeypatch)["revisao_inline"]
    assert ri["exclusoes_itens"][0]["descricao"] == "Poço de visita"
    assert ri["exclusoes_itens"][0]["selo"] == "estimado"
    assert ri["exclusoes_itens"][0]["unidade"] == "un"
    assert ri["exclusoes_itens"][0]["quantidade"] == 2
    assert ri["faltou_recados"][0]["texto"] == "faltou o rodapé do hall"
    assert ri["ultimos_edits"][0]["edits"] == {"quantity": 12}


def test_exclusao_SEM_retrato_nao_derruba_o_painel(monkeypatch):
    """🪤 Exclusão antiga, gravada antes de 31/08, não tem `_antes`. A ficha sai
    com descrição vazia — o painel não pode quebrar por causa dela."""
    sem = dict(_RPC, exclusoes_cruas=[
        {"job_id": "fff66666", "item_id": "i9", "action": "reject",
         "reviewed_at": "2026-08-01T12:00:00Z", "comment": "", "edits": {}}])
    ri = _rota(monkeypatch, resposta=(200, sem))["revisao_inline"]
    assert ri["exclusoes_itens"][0]["descricao"] is None
    assert ri["exclusoes"] == 200


def test_CONTROLE_leitura_falhada_nao_vira_acervo_vazio(monkeypatch):
    """🪤 Zero aqui seria "nenhum cliente revisou nada" — que é notícia muito
    diferente de "não consegui ler"."""
    for resposta in ((500, None), (200, None), (401, {"e": 1}), (200, [])):
        ri = _rota(monkeypatch, resposta=resposta)["revisao_inline"]
        assert ri.get("erro"), resposta
        assert "aprovacoes" not in ri, resposta


def test_CONTROLE_a_rota_nao_puxa_mais_a_tabela_inteira():
    """🪤 O guarda do FATO: se alguém voltar a ler `item_reviews` por HTTP com
    limite, o teto volta em silêncio. Lê o código sem comentário, pra não
    aprovar a própria anotação (já aconteceu 5 vezes nesta casa)."""
    from _corpo import sem_comentarios
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    limpo = sem_comentarios(fonte)
    i = limpo.index("def admin_revision_feedback")
    corpo = limpo[i:limpo.index("\n@app.", i + 10)]
    assert "rpc/admin_revisao_inline" in corpo, "a rota parou de usar a RPC"
    assert not re.search(r"item_reviews[^\"']*limit=", corpo), (
        "voltou a ler item_reviews com teto por HTTP — o corte silencioso volta junto")


# ─────────────────────────────────────────────────────────────────────────────
#  (2) A tela: mostra o total, e acusa ação que ninguém somou
# ─────────────────────────────────────────────────────────────────────────────

def _js():
    js = motor("true;")
    js.evaljs(funcao_js("linhaDoAcervoDeRevisoes", _ADMIN))
    return js


def _linha(ri):
    return _js().evaljs("linhaDoAcervoDeRevisoes(%s)" % json.dumps(ri))


def test_a_tela_mostra_o_tamanho_do_acervo():
    out = _linha({"total_no_banco": 624, "aprovacoes": 301, "edicoes": 122,
                  "exclusoes": 200, "faltou": 1})
    assert "624 revisões no total" in out, out
    assert "não somada" not in out, out


def test_a_tela_ACUSA_acao_que_ninguem_somou():
    """🔑 O defeito de hoje pelo avesso: se amanhã nascer um botão novo na tela
    de revisão e o resumo não acompanhar, o painel tem que gritar — em vez de
    esconder a diferença, que foi o que o teto de 500 fez por semanas."""
    out = _linha({"total_no_banco": 700, "aprovacoes": 301, "edicoes": 122,
                  "exclusoes": 200, "faltou": 1})
    assert "76 não somadas aqui" in out, out
    assert "text-amber-700" in out, out


def test_CONTROLE_sem_o_total_a_linha_e_VAZIA():
    """Backend velho não manda `total_no_banco`. Não inventa número."""
    for sem in ({"aprovacoes": 10}, {}, {"total_no_banco": None},
                {"total_no_banco": "muitas"}):
        assert _linha(sem) == "", sem


def test_CONTROLE_o_painel_CHAMA_a_linha():
    """Guarda de prato: a função pode estar certa e não ser chamada.

    🩸 A 1ª versão deste guarda procurava `linhaDoAcervoDeRevisoes(ri)` no
    arquivo — e a DECLARAÇÃO da função contém exatamente essa string. Ele
    casava consigo mesmo: apagar a chamada do painel deixava o guarda verde.
    A sabotagem W09 sobreviveu e entregou o defeito. Agora procura a CHAMADA
    dentro do template, e exige que ela apareça além da declaração."""
    from _corpo import sem_comentarios_js
    src = sem_comentarios_js(io.open(_ADMIN, encoding="utf-8").read())
    assert "projetos${linhaDoAcervoDeRevisoes(ri)}" in src, (
        "o painel parou de mostrar o tamanho do acervo")
    assert src.count("linhaDoAcervoDeRevisoes(") >= 2, (
        "só existe a declaração da função — ninguém a chama")
