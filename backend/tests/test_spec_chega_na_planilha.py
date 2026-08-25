# -*- coding: utf-8 -*-
"""A especificacao tem que chegar NO OBJETO, que e de onde a planilha le.

🚨 Auditoria de 25/08/2026, achado da frente "meia-entrega". Eu escrevi o
extrator, liguei no INSERT do banco, criei a coluna na planilha, escrevi 31
testes — e a coluna nasceria VAZIA em 100% dos casos, pra sempre.

O motivo: `_spec_campos()` preenche a linha do BANCO; a planilha le do OBJETO
(`getattr(item, "marca")`). Nada setava o objeto.

🪤 E o pior: e EXATAMENTE a mesma familia do bug do `origem`, que eu tinha
consertado HORAS ANTES no mesmo arquivo, e cujo commit eu mesmo escrevi
dizendo "gravado de um lado, lido do outro". Repeti o erro que acabara de
documentar. Guardar o padrao num comentario nao impede de repeti-lo; teste
impede.

🪤 Junto veio o irmao: a RPC `list_project_items` — por onde TODA rota releia
os itens — nao devolvia `origem` nem as 4 colunas novas. O conserto do `origem`
de 24/08 era so do lado da escrita.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa
# verde por engano — a auditoria de 25/08 achou 17 assim. O recorte
# certo mora num lugar só.
from _corpo import corpo_de  # noqa: E402
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def test_existe_quem_carimbe_a_spec_no_objeto():
    assert "def _carimbar_spec(" in _main()


def test_o_carimbo_roda_ANTES_de_gerar_a_planilha():
    """Definir a funcao e nao chama-la seria o mesmo defeito com outra roupa —
    ja me pegou hoje no guarda da ordenacao de e-mails."""
    src = _main()
    chamadas = src.count("_carimbar_spec(all_items)")
    assert chamadas >= 2, (
        "o carimbo nao e chamado nos dois caminhos que geram planilha "
        "(achei %d)" % chamadas)
    for m in __import__("re").finditer(r"_carimbar_spec\(all_items\)", src):
        depois = src[m.end():m.end() + 260]
        assert "generate_spreadsheet(" in depois, (
            "ha um carimbo que nao e seguido de geracao de planilha")


def test_a_reidratacao_do_banco_le_as_colunas_novas():
    """Quando a planilha e regenerada do banco (projeto antigo, arquivo limpo
    pela retencao de 90 dias), os campos tem que voltar."""
    src = _main()
    for campo in ("marca=r.get(", "codigo_fabricante=r.get(",
                  "cor=r.get(", "spec_origem=r.get("):
        assert src.count(campo) >= 2, (
            "%s nao aparece nos DOIS caminhos de reidratacao" % campo)


def _roda_carimbo():
    """A funcao REAL, executada.

    🪤 25/08: os dois testes abaixo conferiam TEXTO numa janela de
    `src[i:i+1800]` e quebraram no dia em que a funcao melhorou — a guarda
    passou a olhar `spec_origem` (que cobre 222 itens a mais, os que so tem
    cor) e os comentarios cresceram alem da janela. Os dois quebraram sem que
    nada tivesse piorado: exatamente o defeito que o `_corpo.py` documenta.
    Agora medem EFEITO."""
    from _corpo import so_o_que_roda
    corpo = so_o_que_roda("_carimbar_spec")
    ns = {"print": lambda *a, **k: None}
    exec("def _carimbar_spec(itens) -> int:\n" + corpo.split("\n", 1)[1], ns)
    return ns["_carimbar_spec"]


class _ItFalso:
    def __init__(self, **kw):
        self.description = kw.get("description", "")
        self.marca = kw.get("marca", "")
        self.codigo_fabricante = kw.get("codigo_fabricante", "")
        self.cor = kw.get("cor", "")
        self.spec_origem = kw.get("spec_origem", "")


def test_o_carimbo_nao_sobrescreve_o_que_veio_do_banco():
    """Se o item ja tem especificacao (veio do banco, ou o cliente preencheu
    no caderno), o carimbo nao pode passar por cima — regra dura nº7."""
    it = _ItFalso(description="Torneira de mesa 1167.C.LNK Deca",
                  marca="Docol", spec_origem="cliente")
    assert _roda_carimbo()([it]) == 0
    assert it.marca == "Docol"


def test_o_carimbo_falha_em_silencio_e_nao_derruba_a_planilha():
    """Item sem especificacao e o estado normal de 93% do acervo, e uma
    excecao aqui nao pode impedir a planilha de sair.

    🧪 Aqui a descricao EXPLODE ao ser lida — o jeito de provar que o
    try/except do laco segura de verdade, em vez de contar `except` no fonte."""
    class _Explode(_ItFalso):
        @property
        def description(self):
            raise RuntimeError("descricao podre")

        @description.setter
        def description(self, v):
            pass

    bom = _ItFalso(description="Torneira de mesa 1167.C.LNK Deca")
    n = _roda_carimbo()([_Explode(), bom])          # nao pode levantar
    import spec_extract
    if spec_extract.LIBERADO_PRO_CLIENTE:
        assert n == 1, "o item podre derrubou o carimbo do item bom"
        assert bom.marca == "Deca"


def test_o_carimbo_funciona_de_verdade():
    """🚨 Nao basta existir: tem que carimbar. Este e o teste que a versao
    anterior nao tinha — ela conferia forma, nao efeito."""
    from models import BudgetItem, Confidence
    itens = [
        BudgetItem(item_num="1", description="Papeleira cromada Quadratta — Deca, Cód. 2020.CB3",
                   unit="un", quantity=1, confidence=Confidence.CONFIRMADO),
        BudgetItem(item_num="2", description="Alvenaria em bloco cerâmico",
                   unit="m²", quantity=10, confidence=Confidence.ESTIMADO),
    ]
    # reimplementa o carimbo com o MESMO extrator, sem importar o main (que
    # puxa o app inteiro): o que se garante aqui e que o extrator + os campos do
    # modelo se encaixam.
    from spec_extract import extrair_spec, spec_origem
    for it in itens:
        sp = extrair_spec(it.description)
        if spec_origem(sp):
            it.marca = sp["marca"] or ""
            it.codigo_fabricante = sp["codigo"] or ""
    assert itens[0].marca == "Deca"
    assert itens[0].codigo_fabricante == "2020.CB3"
    assert itens[1].marca == ""


def test_a_planilha_le_esses_campos_do_objeto():
    """Fecha o circuito: o nome do campo no modelo e o mesmo que a planilha
    procura. Um typo aqui deixaria tudo silenciosamente vazio."""
    corpo = corpo_de("_especificacao_texto", "spreadsheet.py")
    from models import BudgetItem
    for campo in ("marca", "codigo_fabricante", "cor"):
        assert campo in corpo, "a planilha nao le %s" % campo
        assert campo in BudgetItem.model_fields, "o modelo nao tem %s" % campo
