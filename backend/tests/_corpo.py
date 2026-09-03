# -*- coding: utf-8 -*-
"""Recorte de função para os guardas — um lugar só, e correto.

🚨 25/08/2026. A auditoria do dia achou 11 testes com janela de tamanho fixo
(`src[i:i + 1400]`); medindo de verdade, são **17**. Duas formas de errar, e as
duas produzem VERDE FALSO:

  • janela MAIOR que a função → o teste lê o código VIZINHO e passa por causa
    do texto dele. Foi assim que eu apaguei o aviso de falha da rede da regra
    dura nº1 e o guarda continuou verde: ele estava lendo o `warnings` do bloco
    seguinte.
  • janela MENOR que a função → mede um pedaço e não enxerga o que diz guardar.

No mesmo dia eu errei essa janela TRÊS vezes seguidas. Não é descuido pontual:
é o recorte à mão sendo a ferramenta errada. Aqui ele existe uma vez.

🪤 O fim de uma função Python é a próxima definição na COLUNA ZERO — não é um
número de caracteres, não é o próximo decorador, e não é a próxima linha em
branco.
"""
import io
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
_NL = chr(10)


def fonte(arquivo: str = "main.py") -> str:
    """Lê um arquivo do backend (ou da raiz, pros .html)."""
    base = _BACKEND if arquivo.endswith(".py") else _RAIZ
    return io.open(os.path.join(base, arquivo), encoding="utf-8").read()


def corpo_de(nome: str, arquivo: str = "main.py", src: str = None) -> str:
    """A função INTEIRA, do `def` até onde ela realmente acaba.

    Aceita `def` e `async def`, em QUALQUER nível de indentação.

    🪤 A 1ª versão disto só achava definição na coluna zero, e dois guardas
    quebraram na hora: `_peso_aviso` é aninhada dentro do montador de e-mail,
    com 8 espaços. Antes da conversão eles passavam porque a janela fixa de 700
    chars lia a função de fora — ou seja, mediam o vizinho e davam verde.

    O fim de uma função Python é a primeira linha não-vazia com indentação MENOR
    OU IGUAL à do `def` — não é um número de caracteres.
    """
    import re as _re
    src = src if src is not None else fonte(arquivo)
    linhas = src.splitlines(True)
    rx = _re.compile(r"^(\s*)(?:async\s+)?def\s+%s\s*\(" % _re.escape(nome))

    ini = ind = None
    for n, l in enumerate(linhas):
        m = rx.match(l)
        if m:
            ini, ind = n, len(m.group(1))
            break
    if ini is None:
        raise AssertionError("não achei a função %s em %s" % (nome, arquivo))

    fim = len(linhas)
    for n in range(ini + 1, len(linhas)):
        l = linhas[n]
        if not l.strip():
            continue
        if len(l) - len(l.lstrip()) <= ind:
            fim = n
            break
    return "".join(linhas[ini:fim])


def corpo_js(nome: str, arquivo: str = "projeto.html", src: str = None) -> str:
    """A função JS inteira, achando o fim REAL por balanço de chaves.

    🚨 02/09/2026. Mesmo motivo do `corpo_de`: janela de tamanho fixo mede o
    vizinho ou um pedaço, e as duas formas dão VERDE FALSO. Em JS o fim da
    função é a chave que fecha a primeira — não um número de caracteres.

    🪤 Balanço de chaves não entende chave dentro de string ou regex. Nas
    funções que esta casa guarda isso não ocorre, e o teste de controle
    (`o extrator para antes da próxima função`) reprova se passar a ocorrer.
    """
    src = src if src is not None else fonte(arquivo)
    i = src.find("function %s(" % nome)
    if i < 0:
        raise AssertionError("não achei function %s() em %s" % (nome, arquivo))
    prof = 0
    k = src.find("{", i)
    if k < 0:
        raise AssertionError("função %s sem corpo em %s" % (nome, arquivo))
    while k < len(src):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[i:k + 1]
        k += 1
    raise AssertionError("chaves desbalanceadas em %s (%s)" % (nome, arquivo))


def sem_docstring(texto: str) -> str:
    """Tira a docstring.

    🪤 Guardas desta casa citam, na docstring, a frase que estão proibindo — pra
    explicar por que ela saiu. Um teste que lê a docstring acusa a própria
    documentação e me empurra a apagá-la pra calar o alarme."""
    a = texto.find('"""')
    if a < 0:
        return texto
    b = texto.find('"""', a + 3)
    return texto if b < 0 else texto[:a] + texto[b + 3:]


def sem_comentarios(texto: str) -> str:
    return _NL.join(l for l in texto.splitlines()
                    if not l.strip().startswith("#"))


def so_o_que_roda(nome: str, arquivo: str = "main.py") -> str:
    """Corpo da função sem docstring e sem comentário — só o que executa."""
    return sem_comentarios(sem_docstring(corpo_de(nome, arquivo)))
