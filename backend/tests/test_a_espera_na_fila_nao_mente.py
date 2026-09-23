# -*- coding: utf-8 -*-
"""A tela de quem está NA FILA não pode mentir três vezes.

🩸 23/09/2026. O Pedro reclamou do texto ("dizer que está na fila fica feio").
O texto era o menor dos problemas — o card inteiro mentia pra quem esperava:

  • o título fixo dizia "AINDA processando este projeto" sobre um projeto que
    nem tinha começado;
  • "começa em instantes…" prometia um prazo que não controlamos (mediana
    medida ~10 min, pior caso 51 min);
  • a barra parava em 3%, e barra parada lê como travado;
  • 🩸 e aos 5 min a escotilha "Parece que travou?" aparecia com um botão
    mandando RECARREGAR — para quem só precisava esperar.

📊 26 de 150 projetos em 60 dias (17,3%) chegaram com 2 leituras já rodando.

🪤 A condição do alarme morava solta dentro do `setInterval`, onde guarda
nenhum alcançava. Por isso ela é função PURA agora — e por isso estes guardas
CHAMAM o JS de verdade em vez de procurar texto no fonte.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import funcao_js, motor  # noqa: E402

_TELA = "projeto.html"

# Palavras que prometem PRAZO. Nenhuma pode aparecer no texto da espera:
# a vaga abre quando o projeto da frente termina, e isso não é nosso.
_PROMESSAS_DE_PRAZO = (
    "instante", "minuto", "segundo", "breve", "logo mais",
    "já já", "rápido", "poucos",
)

_PRELUDIO_DOM = """
var __el = {};
function __get(id){
  if (!__el[id]) {
    var e = { textContent: '', __classes: {} };
    e.classList = {
      add: function(c){ e.__classes[c] = true; },
      remove: function(c){ delete e.__classes[c]; }
    };
    __el[id] = e;
  }
  return __el[id];
}
var document = { getElementById: __get };
function __estado(){
  var fora = {};
  for (var k in __el) {
    fora[k] = { texto: __el[k].textContent,
                escondido: !!__el[k].__classes['hidden'] };
  }
  return fora;
}
"""


def _motor_com_dom():
    """As 3 funções da espera, rodando de verdade, com o DOM encenado."""
    js = motor(_PRELUDIO_DOM)
    for nome in ("_textoDaEspera", "_deveAlarmarTravamento", "_pintarEspera"):
        js.evaljs(funcao_js(nome, _TELA))
    return js


def _pintar(na_fila, n_arqs):
    js = _motor_com_dom()
    # nasce no estado de PROCESSANDO, como a página serve o HTML
    js.evaljs("__get('proc-titulo').textContent = 'Ainda processando este projeto';")
    js.evaljs("__get('proc-step').textContent = 'Lendo as pranchas';")
    js.evaljs("__get('proc-rodape').textContent = 'Pode deixar esta aba aberta';")
    js.evaljs("__get('proc-trilho'); __get('proc-pct');")
    js.evaljs("_pintarEspera(%s, %s);" % (
        "true" if na_fila else "false", json.dumps(n_arqs)))
    return json.loads(js.evaljs("JSON.stringify(__estado())"))


def _texto(n_arqs):
    js = _motor_com_dom()
    return json.loads(js.evaljs(
        "JSON.stringify(_textoDaEspera(%s))" % json.dumps(n_arqs)))


# ══════════════════════════════════════════════════════════════════════════
#  O TEXTO
# ══════════════════════════════════════════════════════════════════════════
def test_a_espera_NAO_promete_prazo_nenhum():
    """A vaga abre quando o projeto da frente termina — não é nosso de prometer."""
    for n in (None, 1, 13, 33):
        t = _texto(n)
        inteiro = " ".join([t["titulo"], t["passo"], t["rodape"]]).lower()
        for palavra in _PROMESSAS_DE_PRAZO:
            assert palavra not in inteiro, (
                "com %r o texto promete prazo (%r): %s" % (n, palavra, inteiro))


def test_o_titulo_perde_o_AINDA_que_sugeria_demora():
    t = _texto(13)
    assert "ainda" not in t["titulo"].lower(), t["titulo"]
    assert t["titulo"] == "Projeto recebido"


def test_o_texto_diz_QUANTOS_arquivos_chegaram():
    """É o que prova ao cliente que o material já está na nossa mão."""
    assert "13 arquivos" in _texto(13)["passo"]
    assert "33 arquivos" in _texto(33)["passo"]


def test_um_arquivo_so_sai_no_SINGULAR():
    passo = _texto(1)["passo"]
    assert "Seu arquivo chegou e foi conferido." in passo, passo
    assert "1 arquivos" not in passo


def test_sem_a_contagem_a_frase_ainda_fecha():
    """files_count vem null quando o projeto acabou de entrar — não pode quebrar."""
    for vazio in (None, 0, "", "abc"):
        passo = _texto(vazio)["passo"]
        assert passo.startswith("Seus arquivos chegaram e foram conferidos."), (
            vazio, passo)
        assert "null" not in passo
        assert "NaN" not in passo
        assert "undefined" not in passo


def test_o_rodape_promete_e_mail_porque_o_e_mail_SAI():
    """Medido: 85 de 88 concluídos em 30 dias (96,6%) receberam e-mail no fim."""
    assert "e-mail" in _texto(13)["rodape"].lower()


# ══════════════════════════════════════════════════════════════════════════
#  A TELA
# ══════════════════════════════════════════════════════════════════════════
def test_na_fila_a_barra_parada_SOME_da_tela():
    """Barra em 3% que não anda é o que lê como travado."""
    st = _pintar(True, 13)
    assert st["proc-trilho"]["escondido"], st["proc-trilho"]
    assert st["proc-pct"]["escondido"], st["proc-pct"]


def test_na_fila_o_card_inteiro_troca_de_texto():
    st = _pintar(True, 13)
    assert st["proc-titulo"]["texto"] == "Projeto recebido"
    assert "13 arquivos" in st["proc-step"]["texto"]
    assert "e-mail" in st["proc-rodape"]["texto"].lower()


def test_quando_a_VAGA_ABRE_a_tela_volta_ao_normal():
    """Senão 'Projeto recebido' e a barra escondida ficariam pra sempre."""
    st = _pintar(False, 13)
    assert st["proc-titulo"]["texto"] == "Ainda processando este projeto"
    assert not st["proc-trilho"]["escondido"]
    assert not st["proc-pct"]["escondido"]
    assert "aba aberta" in st["proc-rodape"]["texto"]


def test_o_CICLO_inteiro_fila_depois_processando_nao_deixa_resto():
    """O caso real: entra na fila, a vaga abre, e a tela tem que virar."""
    js = _motor_com_dom()
    js.evaljs("__get('proc-titulo'); __get('proc-step'); __get('proc-rodape');")
    js.evaljs("__get('proc-trilho'); __get('proc-pct');")
    js.evaljs("_pintarEspera(true, 13);")
    js.evaljs("_pintarEspera(false, 13);")
    st = json.loads(js.evaljs("JSON.stringify(__estado())"))
    assert st["proc-titulo"]["texto"] == "Ainda processando este projeto"
    assert not st["proc-trilho"]["escondido"], "a barra ficou escondida DEPOIS da fila"
    assert not st["proc-pct"]["escondido"]


# ══════════════════════════════════════════════════════════════════════════
#  O ALARME FALSO
# ══════════════════════════════════════════════════════════════════════════
def _alarme(na_fila, elapsed, last_advance, ja_mostrou, stall=300):
    js = _motor_com_dom()
    return json.loads(js.evaljs(
        "JSON.stringify(_deveAlarmarTravamento(%s,%d,%d,%s,%d))" % (
            "true" if na_fila else "false", elapsed, last_advance,
            "true" if ja_mostrou else "false", stall)))


def test_quem_esta_NA_FILA_nunca_ve_parece_que_travou():
    """Não travou — NÃO COMEÇOU. Mediana de espera medida: ~10 min."""
    # 5 min, 10 min, 30 min, 51 min (o pior caso medido no acervo)
    for esperou in (301, 600, 1800, 3060):
        assert _alarme(True, esperou, 0, False) is False, esperou


def test_quem_esta_PROCESSANDO_e_congelou_CONTINUA_vendo_o_alarme():
    """Controle positivo: o alarme não pode ter morrido junto."""
    assert _alarme(False, 301, 0, False) is True


def test_o_alarme_nao_aparece_duas_vezes():
    assert _alarme(False, 900, 0, True) is False


def test_dentro_do_prazo_o_alarme_fica_quieto():
    assert _alarme(False, 299, 0, False) is False


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — cada um encena o defeito e prova que o guarda REPROVA
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_texto_ANTIGO_seria_reprovado():
    """'Na fila — começa em instantes…' é exatamente a promessa proibida."""
    antigo = "Na fila — começa em instantes…".lower()
    achou = [p for p in _PROMESSAS_DE_PRAZO if p in antigo]
    assert achou, "o guarda do prazo estaria cego — não pegaria o texto antigo"


def test_CONTROLE_o_titulo_ANTIGO_seria_reprovado():
    assert "ainda" in "Ainda processando este projeto".lower()


def test_CONTROLE_sem_o_freio_da_fila_o_alarme_dispara_no_cliente_que_espera():
    """A condição velha, encenada: sem o `if (naFila) return false`."""
    js = _motor_com_dom()
    js.evaljs("""
    function _velho(naFila, elapsed, lastAdvance, jaMostrou, stallSecs) {
      if (jaMostrou) return false;
      return (elapsed - lastAdvance) > stallSecs;
    }""")
    velho = json.loads(js.evaljs("JSON.stringify(_velho(true,600,0,false,300))"))
    assert velho is True, (
        "a condição velha TINHA que disparar na fila — se não dispara, "
        "este controle parou de provar o defeito")


def test_CONTROLE_pintar_sem_restaurar_deixa_a_barra_escondida():
    """Se _pintarEspera(false) não removesse 'hidden', o guarda do ciclo pega."""
    js = _motor_com_dom()
    js.evaljs("__get('proc-trilho'); __get('proc-pct');")
    js.evaljs("""
    function _pintarQuebrado(naFila) {
      if (naFila) {
        document.getElementById('proc-trilho').classList.add('hidden');
        document.getElementById('proc-pct').classList.add('hidden');
      }
    }""")
    js.evaljs("_pintarQuebrado(true); _pintarQuebrado(false);")
    st = json.loads(js.evaljs("JSON.stringify(__estado())"))
    assert st["proc-trilho"]["escondido"], (
        "o controle parou de provar o defeito: a versão quebrada deveria "
        "deixar a barra escondida")
