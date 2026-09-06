# -*- coding: utf-8 -*-
"""O KPI "pranchas enviadas" tem que contar o que o cliente ENVIOU.

🚨 24/08/2026, caso cliente-19 (job e1c48ed7). Ele enviou 7 arquivos DWG. A tela do
projeto mostrava, sob o rótulo "pranchas enviadas", o número 4.

O 4 era `collectCadFiles(items).size` — quantas pranchas RENDERAM item. As
outras 3 morreram na leitura (KeyError de layout do libredwg). Ou seja: o
número que faltava era exatamente a notícia, e o rótulo jurava outra coisa.

Olhando a tela, o cliente-19 não tinha como saber que perdeu quase metade do projeto.
E o e-mail dele também não contou (o aviso que dizia isso era o 3º de 7, e o
e-mail mandava só os 2 primeiros — ver test_avisos_chegam_ao_cliente).

Pedro, 24/08: *"e quando morrer, temos que explicar isso para os clientes né"*.
Um KPI que mostra 4 quando o cliente mandou 7 não explica: esconde.
"""
import io
import os

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _projeto():
    return io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()


def test_o_numero_grande_e_o_que_o_cliente_enviou():
    src = _projeto()
    assert "setKpi('kpi-arquivos', String(_enviadas || _renderam || '--'));" in src, (
        "o KPI voltou a liderar com as pranchas que renderam item — o cliente-19 "
        "enviou 7 e a tela dizia 4")
    assert "setKpi('kpi-arquivos', String(_files.size || p.files_count" not in src, (
        "a ordem antiga (renderam primeiro) está de volta")


def test_a_diferenca_vira_aviso_na_tela():
    """Trocar 4 por 7 sem dizer nada seria pior: esconderia a perda."""
    src = _projeto()
    assert "' não renderam itens'" in src, (
        "a tela mostra 7 mas não conta que 3 não renderam nada")


def test_o_aviso_so_aparece_quando_ha_perda():
    """Controle negativo: num projeto em que tudo entrou, dizer '0 não
    renderam' seria ruído que ensina o cliente a ignorar o aviso."""
    src = _projeto()
    i = src.index("' não renderam itens'")
    trecho = src[max(0, i - 400):i]
    assert "_renderam < _enviadas" in trecho, (
        "o aviso não está condicionado à perda real")


def test_o_rotulo_tem_id_pra_poder_mudar():
    src = _projeto()
    assert 'id="kpi-arquivos-sub"' in src


def test_a_classe_de_alerta_ja_existe_no_build_do_tailwind():
    """🪤 Tailwind aqui é build ESTÁTICO (/tailwind.min.css). Classe que não
    esteja no build nasce INERTE — o texto mudaria e a cor não. Confere que
    text-amber-600 já é usada em outro lugar da própria página."""
    src = _projeto()
    assert src.count("text-amber-600") >= 2, (
        "text-amber-600 aparece só no código novo — pode não estar no CSS "
        "compilado e o alerta sairia sem cor")


def test_nao_quebrou_o_outro_contador_de_arquivos():
    """`m-files` (escondido) continua com a contagem de quem rendeu item — são
    perguntas diferentes e as duas têm dono."""
    src = _projeto()
    assert "document.getElementById('m-files').textContent = _files.size" in src
