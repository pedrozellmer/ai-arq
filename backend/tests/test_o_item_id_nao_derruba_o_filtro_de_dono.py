# -*- coding: utf-8 -*-
"""Um `#` no item_id apagava o filtro de dono — e a escrita saía com service_role.

🚨 08/09/2026, auditoria de segurança. Gravidade ALTA, confirmada por dois
céticos independentes e reproduzida por mim.

A rota `POST /api/items/{job_id}/review/{item_id}` montava:

    project_items?id=eq.{item_id}&job_id=eq.{job_id}

com o `item_id` CRU, vindo do caminho da URL. O uvicorn faz `unquote`, então
`%23` chega ao handler como `#` literal. E o `urllib.request` **corta a URL no
`#`** — pra ele é fragmento. O que saía na rede:

    project_items?id=eq.<uuid>          ← sem `&job_id=`

🔑 O comentário do próprio código descrevia esse `&job_id=` como o conserto do
IDOR: *"Sem o &job_id, um dono passaria o próprio job_id + o item_id de OUTRO
projeto"*. **Era contornável com um caractere.**

Um cliente autenticado, dono de QUALQUER projeto, chamava a rota com o job_id
dele e `item_id=<uuid-da-vítima>%23`:
  · `action=edit`   → PATCH em linha de outro cliente;
  · `action=reject` → DELETE em linha de outro cliente.
E a escrita usa `SUPABASE_SERVICE_ROLE_KEY`, que passa por cima de toda a RLS.

🪤 Limite real, e é o que separa ALTA de CRÍTICA: precisa saber o UUID da linha
alvo. Não dá pra enumerar — `id=eq.<lixo>` não é uuid e o PostgREST recusa.

🪤 O que mostra que foi ESQUECIMENTO e não escolha: 20 linhas acima, na consulta
de dedupe, o MESMO `item_id` já passava por `quote()`.
"""
import io
import os
import re
import urllib.request

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_BACKEND, "main.py")


def _fonte():
    return io.open(_MAIN, encoding="utf-8").read()


def _rota():
    src = _fonte()
    i = src.index('@app.post("/api/items/{job_id}/review/{item_id}")')
    j = src.index("\n@app.", i + 10)
    return src[i:j]


def _regua():
    """Executa a régua de uuid do main.py — sem importar o módulo."""
    src = _fonte()
    # 🪤 Âncora com quebra de linha dos dois lados DE PROPÓSITO: o comentário
    # logo acima CITA essa mesma linha pra explicar o porquê, e ancorar no
    # texto solto pegava o comentário — a fatia saía com um `#` no meio e
    # morria em SyntaxError. Quarta vez no dia que texto citado engana um
    # guarda meu.
    ini = "\nimport re as _re_uuid\n"
    i = src.index(ini) + 1
    j = src.index("\n\n", src.index("_UUID_RX", i))
    ns = {"__name__": "uuid_ns"}
    exec(compile(src[i:j], "main_uuid_slice", "exec"), ns)
    return ns["_UUID_RX"]


_UUID_BOM = "3eb748e3-1111-4222-8333-444444444444"


# ══════════════════════════════════════════════════════════════════════════
#  O MECANISMO — se um dia o urllib mudar, quero saber por aqui
# ══════════════════════════════════════════════════════════════════════════
def test_o_urllib_REALMENTE_corta_a_url_no_cerquilha():
    """🧪 Este é o fato que tornava o ataque possível. Sem ele, todo o resto
    deste arquivo estaria protegendo contra nada — e é por isso que ele vem
    primeiro."""
    r = urllib.request.Request(
        "https://x/rest/v1/project_items?id=eq.AAA#&job_id=eq.MEU", method="DELETE")
    assert r.selector == "/rest/v1/project_items?id=eq.AAA", (
        "o urllib parou de cortar no '#': " + r.selector)
    assert "job_id" not in r.selector, "o filtro de dono sobreviveu — bom, mas confira o resto"


# ══════════════════════════════════════════════════════════════════════════
#  A régua recusa o ataque e aceita o legítimo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("ataque", [
    _UUID_BOM + "#",                       # o ataque exato da auditoria
    _UUID_BOM + "#&job_id=eq.outro",
    _UUID_BOM + "?",
    _UUID_BOM + "&job_id=eq.outro",
    _UUID_BOM + " ",
    _UUID_BOM + "\n",
    "*", "", "eq.qualquer", "../../etc/passwd",
])
def test_a_regua_RECUSA_item_id_que_nao_e_uuid(ataque):
    assert not _regua().fullmatch(ataque), (
        "passou um item_id que não é uuid canônico: %r" % ataque)


@pytest.mark.parametrize("bom", [
    _UUID_BOM,
    _UUID_BOM.upper(),
    "00000000-0000-0000-0000-000000000000",
])
def test_CONTROLE_uuid_legitimo_continua_passando(bom):
    """Recusar tudo passaria em todos os testes acima e quebraria a revisão."""
    assert _regua().fullmatch(bom), "recusou um uuid válido: %r" % bom


# ══════════════════════════════════════════════════════════════════════════
#  A rota valida ANTES de montar qualquer URL
# ══════════════════════════════════════════════════════════════════════════
def test_a_rota_valida_o_item_id_ANTES_de_montar_url():
    """🔑 A ORDEM é o conserto. Validar depois de montar a primeira URL não
    protege a primeira URL — e são três montagens nesta rota."""
    corpo = _rota()
    i_val = corpo.find("_UUID_RX.fullmatch(item_id")
    assert i_val > 0, "a rota não valida o item_id"

    primeira_url = min(
        [p for p in (corpo.find("id=eq.{item_id}"),
                     corpo.find("project_items?id=eq.")) if p > 0] or [len(corpo)])
    assert i_val < primeira_url, (
        "a validação está DEPOIS da primeira montagem de URL — a primeira "
        "continua exposta")


def test_a_rota_recusa_com_400_e_nao_500():
    """🪤 A 1ª versão olhava 260 caracteres à frente e a mutação passou batida:
    havia OUTRO `HTTPException(400` dentro da janela. Peneira larga não prova
    nada — agora olho o PRIMEIRO `raise` depois da validação, que é o dela.
    """
    corpo = _rota()
    i = corpo.find("_UUID_RX.fullmatch(item_id")
    assert i > 0, "a rota não valida o item_id"
    j = corpo.find("raise HTTPException(", i)
    assert 0 < j < i + 200, "não achei o raise da validação logo abaixo dela"
    primeiro = corpo[j:j + 60]
    assert primeiro.startswith("raise HTTPException(400"), (
        "a recusa do item_id inválido não é 400: " + primeiro)


def test_a_regua_e_ancorada_dos_DOIS_lados():
    """🪤 Com `fullmatch` o `$` é redundante — tirar ele é mutante equivalente
    HOJE. Mas ele é a segunda trava: se alguém trocar `fullmatch` por `match`
    ou `search` amanhã (e a mutação mostrou que essa troca é fácil de fazer),
    a âncora é a única coisa entre o ataque e a URL. Este teste usa `search` DE
    PROPÓSITO, pra que o `$` tenha quem o defenda.
    """
    rx = _regua()
    assert not rx.search(_UUID_BOM + "#&job_id=eq.outro"), (
        "o padrão não está ancorado no fim — com `search` o ataque volta")
    assert not rx.search("lixo" + _UUID_BOM), (
        "o padrão não está ancorado no início")
    assert rx.search(_UUID_BOM), "controle: o uuid limpo tem que casar"


def test_as_tres_montagens_continuam_com_o_filtro_de_dono():
    """CONTROLE POSITIVO: o `&job_id=` é o guarda que o `#` derrubava. Ele não
    pode sumir por 'agora validamos o formato' — as duas defesas somam."""
    corpo = _rota()
    assert corpo.count("id=eq.{item_id}&job_id=eq.{job_id}") >= 3, (
        "sumiu o filtro &job_id= de alguma das montagens — achei %d de 3"
        % corpo.count("id=eq.{item_id}&job_id=eq.{job_id}"))


def test_a_regua_de_uuid_e_UMA_SO():
    """🪤 O financeiro já validava uuid com o mesmo padrão, 4.600 linhas abaixo
    e com nome de outro assunto (`_FIN_UUID_RX`). Duas cópias da mesma régua é
    como as coisas se separam — e foi assim que a frase da escala e a régua
    dela divergiram hoje de manhã."""
    src = _fonte()
    padrao = r"\[0-9a-fA-F\]\{8\}-"
    quantas = len(re.findall(padrao, src))
    assert quantas <= 2, (
        "o padrão de uuid foi copiado %d vezes — cada cópia é uma régua que "
        "pode divergir" % quantas)
