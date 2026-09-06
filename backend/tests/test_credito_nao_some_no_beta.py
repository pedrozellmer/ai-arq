# -*- coding: utf-8 -*-
"""Crédito não se gasta em produto grátis, e baixa de crédito devolve troco.

🩸 06/09/2026 — o único defeito da auditoria da cobrança com DANO DE CLIENTE
sem a cobrança estar ligada. Dois erros que se somavam:

(1) NO BETA, O CRÉDITO ERA QUEIMADO NUM PROJETO QUE SAIRIA GRÁTIS.
    Em dashboard.html, `creditCoversAll` entrava no primeiro ramo ANTES do
    `else if (BETA_FREE)`. Quem tinha saldo pagava com ele um projeto que
    qualquer outra pessoa recebe de graça — e não via sumir, porque a pill do
    saldo está com display:none desde que o cashback saiu do palco.

(2) A BAIXA QUEIMAVA A LINHA INTEIRA, SEM TROCO.
    `_consume_credits` marcava `used_at` na linha toda e somava o valor CHEIO.
    Quem tivesse R$2.000 e usasse R$97 perdia R$1.903 em silêncio.

Juntos: a próxima cortesia de R$2.000 viraria R$97 usados e R$1.903 perdidos no
primeiro clique. O Pedro concedeu cortesia 3× em maio, quando o produto falhou
com cliente — e as três diziam "1 mês de uso ilimitado".
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


def _dash():
    p = os.path.join(_RAIZ, "dashboard.html")
    return io.open(p, encoding="utf-8").read()


# ─────────────────────────────────────────────────────────────────────────────
#  (1) No beta, crédito não se gasta
# ─────────────────────────────────────────────────────────────────────────────

def test_no_beta_o_credito_NAO_e_consumido():
    """A decisão de gastar crédito tem que depender de a cobrança estar ligada.
    Guarda de FATO: a variável que desvia o fluxo olha o BETA_FREE."""
    src = _dash()
    m = re.search(r"^\s*const creditoPaga\s*=.*$", src, re.M)
    assert m, "a variável que decide se o crédito paga sumiu de dashboard.html"
    assert "BETA_FREE" in m.group(0), (
        "a decisão de gastar crédito voltou a ignorar o beta: %s" % m.group(0).strip())


def test_o_ramo_gratuito_usa_a_variavel_nova_e_nao_a_crua():
    """🪤 Não basta criar a variável: o `if` tem que passar a usá-la. Deixar o
    `creditCoversAll` cru na condição mantém o defeito inteiro."""
    src = _dash()
    m = re.search(r"^\s*if \(isFree \|\| isUnlimited \|\| (\w+)\)", src, re.M)
    assert m, "o ramo do projeto gratuito mudou de forma; ajuste este guarda"
    assert m.group(1) == "creditoPaga", (
        "o ramo gratuito ainda decide por %r — o crédito volta a ser queimado "
        "no beta" % m.group(1))


def test_CONTROLE_a_versao_ANTIGA_reprovaria():
    """O guarda acima só vale se souber acusar a linha que existia até hoje."""
    antiga = "    if (isFree || isUnlimited || creditCoversAll) {"
    m = re.search(r"if \(isFree \|\| isUnlimited \|\| (\w+)\)", antiga)
    assert m and m.group(1) == "creditCoversAll", (
        "o padrão parou de reconhecer a versão antiga — o controle positivo "
        "deixou de provar qualquer coisa")


# ─────────────────────────────────────────────────────────────────────────────
#  (2) A baixa devolve troco
# ─────────────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _preparar(monkeypatch, creditos):
    """Espiona a baixa e a devolução. Devolve (patches, inserts)."""
    patches, inserts = [], []
    monkeypatch.setattr(main, "_get_available_credits", lambda u: creditos)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    def _falso_insert(tabela, dados):
        inserts.append((tabela, dados))
        return True
    monkeypatch.setattr(main, "_supabase_insert", _falso_insert)

    import urllib.request as _ur

    def _falso_urlopen(req, timeout=None):
        patches.append(req.full_url)
        return _FakeResp()
    monkeypatch.setattr(_ur, "urlopen", _falso_urlopen)
    return patches, inserts


def test_usar_97_de_um_credito_de_2000_devolve_1903(monkeypatch):
    """O caso exato das cortesias que existiam: R$2.000 de saldo, projeto de
    R$97. Antes, o cliente perdia R$1.903 sem ver."""
    patches, inserts = _preparar(monkeypatch, [
        {"id": 1, "amount_cents": 200000, "source": "admin_courtesy",
         "source_ref": "x", "expires_at": "2026-12-31T00:00:00Z"}])
    consumido = main._consume_credits("user-1", 9700, "job-1")
    assert consumido == 9700, ("consumiu %d em vez de 9700 — a linha inteira "
                               "foi queimada de novo" % consumido)
    assert len(inserts) == 1, "o troco não foi devolvido"
    _tab, _d = inserts[0]
    assert _tab == "user_credits"
    assert _d["amount_cents"] == 190300, _d
    assert _d["user_id"] == "user-1"


def test_o_troco_herda_a_validade_do_original(monkeypatch):
    """🪤 O troco não pode ganhar sobrevida que o crédito original não tinha —
    senão uma cortesia de 30 dias vira eterna por fatiamento."""
    _p, inserts = _preparar(monkeypatch, [
        {"id": 1, "amount_cents": 200000, "source": "admin_courtesy",
         "source_ref": "ref-x", "expires_at": "2026-06-04T00:00:00Z"}])
    main._consume_credits("user-1", 9700, "job-1")
    _d = inserts[0][1]
    assert _d["expires_at"] == "2026-06-04T00:00:00Z", _d
    assert _d["source"] == "admin_courtesy" and _d["source_ref"] == "ref-x", _d


def test_credito_exato_NAO_gera_troco(monkeypatch):
    """Sem sobra, sem linha nova — senão a tabela enche de zeros."""
    _p, inserts = _preparar(monkeypatch, [
        {"id": 1, "amount_cents": 9700, "source": "cashback",
         "source_ref": None, "expires_at": None}])
    consumido = main._consume_credits("user-1", 9700, "job-1")
    assert consumido == 9700
    assert inserts == [], "gerou troco de zero"


def test_saldo_insuficiente_consome_tudo_e_nao_inventa_troco(monkeypatch):
    _p, inserts = _preparar(monkeypatch, [
        {"id": 1, "amount_cents": 5000, "source": "cashback",
         "source_ref": None, "expires_at": None}])
    consumido = main._consume_credits("user-1", 9700, "job-1")
    assert consumido == 5000
    assert inserts == []


def test_a_baixa_MANTEM_a_trava_contra_baixa_dupla(monkeypatch):
    """🚨 O filtro `used_at=is.null` na URL é o que impede baixa dupla numa
    corrida — e o dashboard tem histórico de duplo clique medido. Ele não pode
    se perder no meio do conserto do troco."""
    patches, _i = _preparar(monkeypatch, [
        {"id": 7, "amount_cents": 200000, "source": "x",
         "source_ref": None, "expires_at": None}])
    main._consume_credits("user-1", 9700, "job-1")
    assert patches, "nenhuma baixa foi tentada"
    assert "used_at=is.null" in patches[0], patches[0]


def test_troco_que_NAO_grava_avisa_em_vez_de_sumir(monkeypatch):
    """Escrita de dinheiro que falha calada é o defeito que a casa mais paga.
    Se o troco não voltar, alguém tem que ficar sabendo."""
    avisos = []
    monkeypatch.setattr(main, "_get_available_credits", lambda u: [
        {"id": 1, "amount_cents": 200000, "source": "x",
         "source_ref": None, "expires_at": None}])
    monkeypatch.setattr(main, "_supabase_insert", lambda t, d: False)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: avisos.append(stage))
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=None: _FakeResp())
    main._consume_credits("user-1", 9700, "job-1")
    assert "credito:troco-perdido" in avisos, avisos


def test_a_ordem_e_BAIXA_e_depois_TROCO(monkeypatch):
    """🚨 Invertida, uma queda no meio DUPLICARIA o saldo (troco criado sem a
    baixa ter acontecido). Nesta ordem, a queda perde o troco — mesmo prejuízo
    de antes, nunca pior. Falha fechada."""
    ordem = []
    monkeypatch.setattr(main, "_get_available_credits", lambda u: [
        {"id": 1, "amount_cents": 200000, "source": "x",
         "source_ref": None, "expires_at": None}])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda t, d: ordem.append("troco") or True)
    import urllib.request as _ur

    def _u(req, timeout=None):
        ordem.append("baixa")
        return _FakeResp()
    monkeypatch.setattr(_ur, "urlopen", _u)
    main._consume_credits("user-1", 9700, "job-1")
    assert ordem == ["baixa", "troco"], ordem


def test_CONTROLE_o_espiao_enxerga_a_ausencia_de_troco(monkeypatch):
    """Prova que os testes acima falhariam se o troco deixasse de ser gravado."""
    _p, inserts = _preparar(monkeypatch, [])
    consumido = main._consume_credits("user-1", 9700, "job-1")
    assert consumido == 0 and inserts == []
