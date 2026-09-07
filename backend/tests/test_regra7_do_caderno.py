# -*- coding: utf-8 -*-
"""O que o CLIENTE especificou sobrevive ao reprocessamento — regra dura nº7.

🚨 25/08/2026. Levantando o terreno pra tela do caderno, apareceram TRÊS
buracos independentes, todos conferidos por leitura de código:

  1. `/add-file` reprocessa no MESMO job_id: **DELETE de todas as linhas** +
     INSERT. A fusão de revisões só roda no caminho do filhote (job_id novo),
     então aqui não havia nada segurando a especificação.
  2. O INSERT chamava `_spec_campos(it.description)` — re-extraía tudo do
     texto e **ignorava** o que o objeto carregava.
  3. `project_items_versoes` (a única cópia que sobra depois do DELETE) tinha
     14 colunas e **nenhuma** das 4 do caderno.

**Ninguém perdeu nada ainda**, e é isso que assusta: `spec_origem` no acervo é
`lido` 483 · `lido:referencia` 73 · null 7.162 — **zero `cliente`**. Não é
conforto, é o relógio. No dia em que a tela subir, o primeiro cliente que
especificar 30 itens e depois anexar uma prancha perde os 30, **calado**, com
e-mail de "planilha atualizada".

🪤 Estes testes RODAM as funções. O guarda antigo desta família conferia
string no fonte e passou verde por meses enquanto a fusão nunca tinha rodado
em produção. Guarda que não prova que reprova não é guarda.
"""
import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_de, so_o_que_roda  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main                                              # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  Um `project_items` de mentira com que o código REAL conversa
# ══════════════════════════════════════════════════════════════════════════
class _Banco:
    """Dubla o PostgREST: guarda linhas, respeita `select=`, APAGA no DELETE."""

    def __init__(self, itens=None):
        self.itens = [dict(l) for l in (itens or [])]
        self.versoes = []          # o que entrou em project_items_versoes
        self.inseridos = []        # o que entrou em project_items
        self.ops = []              # a ordem do que aconteceu

    @staticmethod
    def _cols(qs):
        import urllib.parse as _up
        for parte in qs.split("&"):
            if parte.startswith("select="):
                return [c for c in _up.unquote(parte[7:]).split(",") if c]
        return []

    @staticmethod
    def _proj(linhas, cols):
        return [{c: l.get(c) for c in cols} if cols else dict(l) for l in linhas]

    def rest(self, method, path, params=None, **kw):
        """O caminho `_supa_rest_service` (por baixo do `_supa_rest_tudo`)."""
        p = dict(params or {})
        self.ops.append("rest:%s:%s" % (method, path))
        if path == "project_items" and method == "GET":
            linhas = self.itens
            if str(p.get("spec_origem") or "").startswith("like.cliente"):
                linhas = [l for l in linhas
                          if str(l.get("spec_origem") or "").startswith("cliente")]
            if int(p.get("offset") or 0):
                return 200, []
            return 200, self._proj(linhas, [c for c in str(p.get("select") or "").split(",") if c])
        return 200, []

    def urlopen(self, req, timeout=None):
        """O caminho urllib direto (persist, arquivamento, contagem)."""
        tabela, _, qs = req.full_url.split("/rest/v1/")[-1].partition("?")
        metodo = req.get_method()
        corpo = json.loads(req.data.decode("utf-8")) if getattr(req, "data", None) else None
        self.ops.append("http:%s:%s" % (metodo, tabela))
        if tabela == "project_items":
            if metodo == "GET":
                return _Resp(self._proj(self.itens, self._cols(qs)))
            if metodo == "HEAD":
                return _Resp([], {"Content-Range": "0-0/%d" % len(self.itens)})
            if metodo == "DELETE":
                self.itens = []
                return _Resp([])
            if metodo == "POST":
                self.inseridos = [dict(l) for l in (corpo or [])]
                self.itens = [dict(l) for l in (corpo or [])]
                return _Resp([])
        if tabela == "project_items_versoes":
            if metodo == "GET":
                return _Resp(self.versoes)
            if metodo == "POST":
                self.versoes.extend(dict(l) for l in (corpo or []))
                return _Resp([])
        raise AssertionError("o código bateu numa porta que o teste não conhece: "
                             "%s %s" % (metodo, req.full_url))


class _Resp:
    def __init__(self, dados, headers=None):
        self._b = json.dumps(dados).encode("utf-8")
        self.headers = headers or {}

    def read(self):
        return self._b


def _liga(monkeypatch, banco):
    monkeypatch.setattr(urllib.request, "urlopen", banco.urlopen)
    monkeypatch.setattr(main, "_supa_rest_service", banco.rest)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    return banco


_DESC = "Torneira de mesa bica movel cromado"
#: A linha que o CLIENTE especificou, do jeito que ela está no banco.
_LINHA_DO_CLIENTE = {
    "item_num": "1.1", "description": _DESC, "unit": "un", "quantity": 3.0,
    "observations": "", "ref_sheet": "", "confidence": "confirmado",
    "discipline": "Louças e metais", "section": "10. Louças", "sort_order": 0,
    "marca": "Docol", "codigo_fabricante": "00.123", "cor": "Cromado",
    "spec_origem": "cliente",
}


def _funcao(nome, extra=None):
    """Executa a função REAL, com as dependências injetadas."""
    ns = {"print": lambda *a, **k: None}
    ns.update(extra or {})
    exec(compile(corpo_de(nome), nome, "exec"), ns)
    return ns[nome]


class _It:
    def __init__(self, descricao, **kw):
        self.description = descricao
        self.marca = kw.get("marca", "")
        self.codigo_fabricante = kw.get("codigo_fabricante", "")
        self.cor = kw.get("cor", "")
        self.spec_origem = kw.get("spec_origem", "")


# ══════════════════════════════════════════════════════════════════════════
#  Buraco 2 — o INSERT jogava fora o que o objeto carregava
# ══════════════════════════════════════════════════════════════════════════
def _spec_do_item():
    """A funcao de VERDADE do `main` - com o `_spec_campos` de verdade atras.

    🩸 06/09/2026: antes isto re-executava o corpo com um `_spec_campos`
    reescrito a mao aqui dentro. Duble de dependencia que copia a regra deixa
    de representa-la no dia em que ela muda.
    """
    import main
    return main._spec_do_item


def test_o_que_o_cliente_escolheu_manda_sobre_o_regex():
    """🚨 O caso que a tela do caderno vai criar: a descrição diz Deca, o
    cliente escolheu Docol. Quem vale é o cliente."""
    it = _It("Torneira de mesa bica móvel cromado 1167.C.LNK Deca",
             marca="Docol", codigo_fabricante="00.123", spec_origem="cliente")
    r = _spec_do_item()(it)
    assert r["marca"] == "Docol", "o regex passou por cima da escolha do cliente"
    assert r["codigo_fabricante"] == "00.123"
    assert r["spec_origem"] == "cliente"


def test_item_com_so_a_cor_tambem_e_protegido():
    """222 dos 556 itens do acervo têm especificação só com cor — a guarda
    antiga, que olhava `marca`, deixava todos eles de fora.

    🩸 06/09/2026 — a versão anterior deste guarda punha no objeto a MESMA cor
    que o regex acha na descrição ("Azul Munsell" nos dois lados). Com isso,
    desligar a regra (`if False and ja["spec_origem"]`) dava o mesmo resultado
    e o teste passava VERDE com o defeito aberto. Agora os dois discordam de
    propósito: o texto diz uma cor, o objeto diz outra, e só quem respeita o
    objeto acerta.
    """
    it = _It("Pintura acrílica cor Azul Munsell", cor="Branco Neve",
             spec_origem="lido")
    r = _spec_do_item()(it)
    assert r["cor"] == "Branco Neve", (
        "o regex passou por cima da cor que a linha já carregava (devolveu "
        "%r) — no dia da tela do caderno isso apaga o que o cliente escolheu"
        % r["cor"])
    assert r["spec_origem"] == "lido"
    assert r["marca"] is None, (
        "inventou marca num item que só tinha cor: %r" % r["marca"])


def test_controle_positivo_item_SEM_procedencia_ainda_le_o_texto():
    """🧪 Se a função devolvesse sempre o objeto, ela nunca extrairia nada e
    os testes de cima passariam com o extrator desligado."""
    it = _It("Torneira de mesa bica móvel cromado 1167.C.LNK Deca")
    r = _spec_do_item()(it)
    assert r["marca"] == "Deca" and r["codigo_fabricante"] == "1167.C.LNK"


# ══════════════════════════════════════════════════════════════════════════
#  Buraco 1 — o DELETE do `/add-file`
# ══════════════════════════════════════════════════════════════════════════
def _devolver():
    from _corpo import fonte
    del fonte
    import unicodedata as _ud
    import re as _re_mod
    ns_norm = {"_re": _re_mod, "_ud": _ud}
    exec(compile(corpo_de("_norm_desc"), "_norm_desc", "exec"), ns_norm)
    return _funcao("_devolver_spec_do_cliente", {
        "_norm_desc": ns_norm["_norm_desc"],
        "_log_error": lambda *a, **k: None,
    })


def test_a_especificacao_do_cliente_atravessa_o_swap():
    """🚨 O reprocesso apaga tudo e insere de novo. Sem isto, o cliente que
    especificou perde o trabalho — sem aviso."""
    guardados = {
        "torneira de mesa bica movel cromado": {
            "description": "Torneira de mesa bica móvel cromado",
            "marca": "Docol", "codigo_fabricante": "00.123",
            "cor": None, "spec_origem": "cliente"},
    }
    rows = [
        {"description": "Torneira de mesa bica móvel cromado", "marca": None,
         "codigo_fabricante": None, "cor": None, "spec_origem": None},
        {"description": "Alvenaria em bloco cerâmico", "marca": None,
         "codigo_fabricante": None, "cor": None, "spec_origem": None},
    ]
    casou, perdidos = _devolver()(rows, guardados, "job1")
    assert (casou, perdidos) == (1, 0)
    assert rows[0]["marca"] == "Docol"
    assert rows[0]["spec_origem"] == "cliente"
    assert rows[1]["marca"] is None, "carimbou linha que o cliente não tocou"


def test_o_que_NAO_casou_e_contado_e_gritado():
    """🚨 Resgate que perde linha em silêncio é pior que resgate nenhum: some
    sem ninguém saber, e o cliente ainda recebe "planilha atualizada"."""
    gritos = []
    from _corpo import corpo_de as _c
    import unicodedata as _ud
    import re as _re_mod
    ns_norm = {"_re": _re_mod, "_ud": _ud}
    exec(compile(_c("_norm_desc"), "_norm_desc", "exec"), ns_norm)
    fn = _funcao("_devolver_spec_do_cliente", {
        "_norm_desc": ns_norm["_norm_desc"],
        "_log_error": lambda *a, **k: gritos.append((a, k)),
    })
    guardados = {"item que sumiu da leitura nova": {
        "description": "Item que sumiu da leitura nova", "marca": "Deca",
        "codigo_fabricante": None, "cor": None, "spec_origem": "cliente"}}
    casou, perdidos = fn([{"description": "Outra coisa"}], guardados, "job1")
    assert (casou, perdidos) == (0, 1)
    assert gritos, "perdeu especificação do cliente e não registrou nada"
    assert gritos[0][1].get("severity") == "critical", (
        "perder o que o cliente escreveu não pode ser log de rotina")


def test_sem_nada_do_cliente_o_resgate_nao_faz_nada():
    rows = [{"description": "Alvenaria", "marca": None}]
    assert _devolver()(rows, {}, "job1") == (0, 0)
    assert rows[0]["marca"] is None


# ══════════════════════════════════════════════════════════════════════════
#  Buraco 3 — a tabela de versões é a única cópia que sobra
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("campo", ["marca", "codigo_fabricante", "cor", "spec_origem"])
def test_a_versao_arquivada_guarda_a_especificacao(campo):
    """Depois do DELETE, `project_items_versoes` é a única cópia. Sem estas
    colunas não há de onde voltar."""
    from _corpo import fonte
    src = fonte("main.py")
    i = src.index("_CAMPOS_ITEM_VERSAO = (")
    assert campo in src[i:i + 400], (
        "`%s` saiu da cópia de versão — some no reprocesso sem volta" % campo)


# ══════════════════════════════════════════════════════════════════════════
#  🚨 E O CHAMADOR? — a função certa, não chamada, é código morto
# ══════════════════════════════════════════════════════════════════════════
#  🪤 Escrevi os testes acima, sabotei o código pra conferir, e DUAS das três
#  sabotagens passaram VERDE: trocar `_spec_do_item` de volta por
#  `_spec_campos` no insert, e apagar a chamada do resgate. Os testes exercitam
#  as funções em isolamento e não viam o call site.
#  É a armadilha que eu já tinha registrado ("guarda que só vê se a função
#  existe passa verde com o chamador sabotado") — e caí nela de novo, no mesmo
#  arquivo em que a citei.
def test_o_insert_usa_a_funcao_que_respeita_o_objeto():
    from _corpo import fonte
    src = fonte("main.py")
    assert "**_spec_do_item(it)," in src, (
        "o insert voltou a chamar `_spec_campos(it.description)` — re-extrai "
        "do texto e apaga o que o cliente escolheu")
    assert '**_spec_campos(getattr(it, "description"' not in src


def test_o_resgate_do_swap_e_de_fato_chamado(monkeypatch):
    """🪤 A versão antiga cobrava o prefixo `_devolver_spec_do_cliente(rows,`.
    Trocar o 2º argumento por `{}` mantinha a chamada escrita e o dicionário
    chegava VAZIO — o cliente perdia a especificação igual, com log "0 de 0"."""
    banco = _liga(monkeypatch, _Banco([_LINHA_DO_CLIENTE]))
    main._persist_items_to_supabase("job1", [_It(_DESC)])
    linha = banco.inseridos[0]
    assert linha["marca"] == "Docol", (
        "a especificação do cliente NÃO atravessou o reprocesso (marca=%r)"
        % linha["marca"])
    assert linha["codigo_fabricante"] == "00.123"
    assert linha["spec_origem"] == "cliente"


def test_CONTROLE_o_que_o_MOTOR_leu_nao_e_resgatado(monkeypatch):
    """🧪 Se o resgate carimbasse tudo, os testes de cima passariam com o
    extrator desligado — e a leitura nova nunca mais valeria."""
    velha = dict(_LINHA_DO_CLIENTE, spec_origem="lido", marca="Deca")
    banco = _liga(monkeypatch, _Banco([velha]))
    main._persist_items_to_supabase("job1", [_It(_DESC)])
    assert banco.inseridos[0]["marca"] is None, (
        "o resgate trouxe de volta o que o MOTOR leu — a leitura nova deixa de "
        "valer e todo conserto do extrator morre no reprocesso")


def test_o_resgate_le_ANTES_do_delete():
    """🪤 A ordem é o defeito silencioso: ler DEPOIS do DELETE devolve zero
    linhas, o resgate roda, não acha nada, e o log diz "0 de 0" — parecendo
    que não havia nada a salvar."""
    from _corpo import fonte
    src = fonte("main.py")
    i_le = src.index("_spec_do_cliente_antes_do_swap(job_id)")
    i_del = src.index("rest/v1/project_items?job_id=eq.{job_id}\", method='DELETE'")
    i_devolve = src.index("_devolver_spec_do_cliente(rows,")
    assert i_le < i_del, "a leitura do resgate ficou DEPOIS do DELETE — lê zero"
    assert i_del < i_devolve, "a devolução ficou antes do DELETE"


# ══════════════════════════════════════════════════════════════════════════
#  A fusão do filhote (o outro caminho de reprocesso)
# ══════════════════════════════════════════════════════════════════════════
def test_a_fusao_devolve_a_spec_do_CLIENTE_e_nao_a_do_motor():
    """🔑 A assimetria é de propósito: o que o cliente escolheu volta por
    cima; o que o MOTOR leu não, porque a leitura nova pode ser melhor — e
    hoje é (o extrator mudou 5 vezes só neste dia)."""
    corpo = so_o_que_roda("_fundir_revisoes_do_cliente")
    i = corpo.index('startswith("cliente")')
    trecho = corpo[max(0, i - 200):i + 400]
    for campo in ("alvo.marca", "alvo.codigo_fabricante", "alvo.cor",
                  "alvo.spec_origem"):
        assert campo in trecho, "a fusão não devolve `%s`" % campo
    assert "lido" not in trecho, (
        "a fusão passou a devolver também o que o MOTOR leu — a leitura nova "
        "deixa de valer e o conserto do extrator nunca alcança o filhote")
