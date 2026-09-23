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
    doc, auditor = _rec.readfile(filepath)
    n_erros = len(getattr(auditor, "errors", []) or [])
    n_fix = len(getattr(auditor, "fixes", []) or [])
    print(f"[dxf] readfile falhou ({motivo}); ezdxf.recover ABRIU o arquivo — "
          f"{n_fix} conserto(s), {n_erros} erro(s) que nem o recover resolveu")
    return doc


#: O objeto que o libredwg escreve torto. É a tabela de ORDEM DE EXIBIÇÃO das
#: entidades no CAD: não tem geometria, não tem medida, não entra em
#: quantitativo nenhum. Por isso dá pra jogar fora sem perder nada do desenho.
_SORTENTSTABLE = b"SORTENTSTABLE"


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
            # 3º degrau (23/09): tirar a SORTENTSTABLE e tentar de novo. Só
            # entra quando os dois primeiros já falharam — reescrever 110 MB
            # não é barato, e o caminho normal não pode pagar por isso.
            try:
                limpo = f"{filepath}.sem_sortents.dxf"
                n = _dxf_sem_sortentstable(filepath, limpo)
                if n:
                    print(f"[dxf] {filepath}: {n} SORTENTSTABLE removida(s) — "
                          f"tabela de ORDEM DE EXIBIÇÃO, sem geometria")
                    try:
                        return ezdxf.readfile(limpo)
                    except Exception:
                        return recuperar_dxf(limpo, "sem sortentstable")
            except Exception as elimp:
                rec += f" | sem-sortents: {type(elimp).__name__}: {elimp}"
            raise RuntimeError(
                f"não abriu nem com ezdxf.recover: {filepath} — "
                f"normal: {motivo} | recover: {rec}")
