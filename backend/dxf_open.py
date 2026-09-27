# -*- coding: utf-8 -*-
"""Abrir DXF que o `ezdxf.readfile` recusa — num lugar só.

🚨 24/08/2026, caso cliente-19 (job e1c48ed7). O `ezdxf.readfile` morre em
`ezdxf/layouts/layouts.py:219` com KeyError do NOME DO LAYOUT em arquivos
escritos pelo libredwg. As três ocorrências do MESMO job:

    KeyError: 'DO'
    KeyError: '00-Ã\x8dNDICE DO PROJETO'   (o "Í" lido como latin-1)
    KeyError: 'LAYOUT'

🪤 A primeira leitura foi "é nome acentuado" e estava ERRADA: 'LAYOUT' e 'DO'
não têm acento. O comum é o libredwg escrever entradas de layout que o ezdxf
não resolve de volta na própria tabela — o acento é UM dos casos, não a causa.

🚨 POR QUE ESTE ARQUIVO EXISTE: eu consertei isso no `dwg_extractor` e dei o
caso por encerrado. No dia seguinte o log do MESMO cliente mostrou

    [dxf_render] Erro ao abrir 4366-LO-E_libredwg.dxf: 'LAYOUT'

— o mesmo bug, pela segunda porta. O backend abre DXF em 6 lugares; consertar
"o" lugar não é consertar. Quem precisa de resiliência agora importa daqui.

🚪 As duas portas que NÃO usam isto, de propósito:
    main.py `_medir_dxf_geometria` e o teste do libredwg — lá o "abre ou não
    abre no ezdxf cru" É a medição (compara qualidade de conversor). Abrir com
    recover cegaria o diagnóstico. O teste `test_dxf_portas.py` guarda essa
    lista; porta nova tem que escolher um lado conscientemente.
"""
import ezdxf


def recuperar_dxf(filepath: str, motivo: str = ""):
    """Relê tolerando inconsistência estrutural. Só chame DEPOIS que o caminho
    normal já falhou — é mais lento e come mais RAM.

    Devolve o `doc`. Levanta a exceção do recover se nem ele abrir, para o
    chamador poder juntar as DUAS causas na mensagem (a lição do caso cliente-93,
    18/08: a causa real morreu em dois cortes de log).
    """
    import ezdxf.recover as _rec
    try:
        doc, auditor = _rec.readfile(filepath)
    except Exception as _erec:
        # 🩸 27/09/2026 — o 4º degrau: TEXTO COM QUEBRA DE LINHA CRUA. Ver
        # `_dxf_com_textos_emendados`. Mora aqui pelo mesmo motivo do 3º.
        if _pode_ser_texto_com_quebra(_erec):
            emendado = f"{filepath}.texto_emendado.dxf"
            n = _dxf_com_textos_emendados(filepath, emendado)
            if not n:
                raise
            print(f"[dxf] {filepath}: {n} linha(s) solta(s) de TEXTO emendada(s) "
                  f"de volta no valor de onde saíram; relendo")
            try:
                return ezdxf.readfile(emendado)
            except Exception as _e1:
                if not _pode_ser_sortentstable(_e1):
                    return _rec.readfile(emendado)[0]
                # os dois defeitos no mesmo arquivo: tira a tabela do emendado
                limpo = f"{filepath}.sem_sortents.dxf"
                if not _dxf_sem_sortentstable(emendado, limpo):
                    raise
                return ezdxf.readfile(limpo)
        # 🚨 23/09/2026 — O 3º DEGRAU MORA AQUI, NÃO NO `abrir_dxf`.
        # Eu escrevi este conserto primeiro lá em cima e ele NÃO RODOU no
        # caso do cliente: `dwg_extractor.extract_from_file` — o caminho que
        # o motor usa de verdade, dentro do worker isolado — chama
        # `recuperar_dxf` DIRETO, sem passar pelo `abrir_dxf`. É a armadilha
        # que este arquivo documenta no topo desde 24/08 ("o backend abre DXF
        # em 6 lugares; consertar 'o' lugar não é consertar") e na qual eu caí
        # mesmo assim. Aqui é o ponto que TODAS as portas compartilham.
        if not _pode_ser_sortentstable(_erec):
            raise
        limpo = f"{filepath}.sem_sortents.dxf"
        n = _dxf_sem_sortentstable(filepath, limpo)
        if not n:
            raise
        print(f"[dxf] {filepath}: {n} SORTENTSTABLE removida(s) — tabela de "
              f"ORDEM DE EXIBIÇÃO, sem geometria; relendo")
        try:
            return ezdxf.readfile(limpo)
        except Exception:
            doc, auditor = _rec.readfile(limpo)
    n_erros = len(getattr(auditor, "errors", []) or [])
    n_fix = len(getattr(auditor, "fixes", []) or [])
    print(f"[dxf] readfile falhou ({motivo}); ezdxf.recover ABRIU o arquivo — "
          f"{n_fix} conserto(s), {n_erros} erro(s) que nem o recover resolveu")
    return doc


#: O objeto que o libredwg escreve torto. É a tabela de ORDEM DE EXIBIÇÃO das
#: entidades no CAD: não tem geometria, não tem medida, não entra em
#: quantitativo nenhum. Por isso dá pra jogar fora sem perder nada do desenho.
_SORTENTSTABLE = b"SORTENTSTABLE"


def _pode_ser_sortentstable(exc) -> bool:
    """A exceção do ezdxf é a da SORTENTSTABLE desemparelhada?

    🪤 Reescrever 110 MB é caro: só vale quando a causa é ESTA. A mensagem do
    ezdxf fala em "sort handle" e no código de grupo 331.
    🪤 E ela tem um engano de texto no próprio ezdxf (`entities/dxfobj.py`):
    imprime `handle.code` onde queria `sort_handle.code`, então diz sempre
    "331, expected 5". Por isso o reconhecimento é pela PALAVRA, não pelo
    número.
    """
    t = str(exc or "").lower()
    return "sort handle" in t or "sortentstable" in t


def _dxf_sem_sortentstable(origem: str, destino: str) -> int:
    """Reescreve o DXF sem os objetos SORTENTSTABLE. Devolve quantos tirou.

    🚨 23/09/2026, cliente NOVO (job b48999f0, 2 DWG de 110 MB cada). O ODA
    recusou os dois pela tabela de estilos — o defeito conhecido desde 14/09 —
    e o libredwg assumiu, como manda o plano B. Só que o DXF que ele escreve
    traz a SORTENTSTABLE com os pares DESEMPARELHADOS (dois códigos 331
    seguidos, sem o 5 do par), e o ezdxf recusa em
    `entities/dxfobj.py: load_table`:

        DXFStructureError: Invalid sort handle code 331, expected 5

    🪤 E o `recover` NÃO salva este caso — foi a primeira vez que os dois
    degraus da rede caíram juntos. O cliente recebeu "problema técnico do nosso
    lado, reprocessar não resolve" na PRIMEIRA tentativa dele: cadastrou às
    09:23, subiu às 09:30, informou o pé-direito, e ficou com zero item.

    🔑 Varre em PARES (código, valor), como todo DXF ASCII é escrito, e pula do
    `0/SORTENTSTABLE` até o próximo `0/<qualquer coisa>`. Streaming de propósito:
    estes arquivos têm 110 MB e o dyno tem pouca RAM.
    """
    tirados = 0
    with open(origem, "rb") as f_in, open(destino, "wb") as f_out:
        pulando = False
        while True:
            cod = f_in.readline()
            if not cod:
                break
            val = f_in.readline()
            if not val:
                # linha ímpar no fim: não é par, então não é objeto — preserva
                if not pulando:
                    f_out.write(cod)
                break
            if cod.strip() == b"0":
                # 🪤 A decisão é SEMPRE no marcador de objeto: é ele que abre e
                # fecha o trecho. Sem isto, um valor qualquer escrito
                # "SORTENTSTABLE" dentro de outro objeto ligaria o pulo.
                pulando = val.strip() == _SORTENTSTABLE
                if pulando:
                    tirados += 1
            if not pulando:
                f_out.write(cod)
                f_out.write(val)
    return tirados


def _pode_ser_texto_com_quebra(exc) -> bool:
    """A exceção do ezdxf é a do par desalinhado: onde devia vir um CÓDIGO de
    grupo (um número) veio texto? Pela palavra, como a da SORTENTSTABLE."""
    return "invalid group code" in str(exc or "").lower()


def _e_codigo_de_grupo(linha: bytes) -> bool:
    """A linha pode ser um código de grupo DXF? (número inteiro de 0 a 1071)"""
    s = linha.strip()
    if not s or len(s) > 5:
        return False
    try:
        return 0 <= int(s) <= 1071
    except ValueError:
        return False


def _dxf_com_textos_emendados(origem: str, destino: str) -> int:
    """Reescreve o DXF emendando as linhas soltas de texto de volta no VALOR de
    onde saíram. Devolve quantas linhas emendou.

    🩸 27/09/2026, cliente que VOLTOU (jobs a11f9f9a em 16/09 e dfb805c7 hoje —
    a MESMA planta, R16 e R17, 955 m²). O ODA recusou pela tabela de estilos;
    o libredwg assumiu e escreveu um MTEXT cujo texto ("Nº de chapas de gesso /
    12,5 ou 15 mm") ele leu ALÉM do fim — o lixo de memória que vem junto traz
    uma quebra de linha CRUA. Todo DXF ASCII é uma sequência de PARES (código,
    valor), uma linha cada; a quebra no meio do valor empurra o resto do
    arquivo uma linha, e o ezdxf acha texto onde esperava código:

        normal:  Invalid group code "12,5 ou 15 mm…" at line 3015621
        recover: Invalid group code "Embedded Object" at line 3015629

    🪤 O lixo muda de máquina pra máquina: o MESMO DWG, no libredwg 0.14 do
    Windows, sai com "^J" no lugar da quebra e abre normal. Por isso o caso
    não se reproduz fora do servidor sem injetar a quebra.

    🔑 Lê em pares, como o 3º degrau. Depois de cada valor, enquanto a linha
    seguinte NÃO puder ser um código de grupo, ela é continuação do valor e é
    emendada nele (com espaço). Streaming: estes arquivos têm 50 MB.
    """
    emendas = 0
    with open(origem, "rb") as f_in, open(destino, "wb") as f_out:
        cod = f_in.readline()
        while cod:
            val = f_in.readline()
            if not val:
                f_out.write(cod)      # linha ímpar no fim: preserva
                break
            prox = f_in.readline()
            while prox and not _e_codigo_de_grupo(prox):
                fim = b"\r\n" if prox.endswith(b"\r\n") else b"\n"
                val = val.rstrip(b"\r\n") + b" " + prox.rstrip(b"\r\n") + fim
                emendas += 1
                prox = f_in.readline()
            f_out.write(cod)
            f_out.write(val)
            cod = prox
    return emendas


def abrir_dxf(filepath: str):
    """`ezdxf.readfile` com rede embaixo, em TRÊS degraus. Levanta só se os três
    falharem, com as causas na mensagem."""
    try:
        return ezdxf.readfile(filepath)
    except Exception as exc:
        motivo = f"{type(exc).__name__}: {exc}"
        try:
            return recuperar_dxf(filepath, motivo)
        except Exception as erec:
            rec = f"{type(erec).__name__}: {erec}"
            # 🔑 O 3º degrau NÃO mora aqui: mora dentro de `recuperar_dxf`,
            # que é o ponto que todas as portas compartilham. Ver o comentário
            # lá — foi a armadilha de 23/09.
            raise RuntimeError(
                f"não abriu nem com ezdxf.recover: {filepath} — "
                f"normal: {motivo} | recover: {rec}")
