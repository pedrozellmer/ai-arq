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
    chamador poder juntar as DUAS causas na mensagem (a lição do caso Patrick,
    18/08: a causa real morreu em dois cortes de log).
    """
    import ezdxf.recover as _rec
    doc, auditor = _rec.readfile(filepath)
    n_erros = len(getattr(auditor, "errors", []) or [])
    n_fix = len(getattr(auditor, "fixes", []) or [])
    print(f"[dxf] readfile falhou ({motivo}); ezdxf.recover ABRIU o arquivo — "
          f"{n_fix} conserto(s), {n_erros} erro(s) que nem o recover resolveu")
    return doc


def abrir_dxf(filepath: str):
    """`ezdxf.readfile` com rede embaixo. Levanta se nem o recover abrir, com as
    DUAS causas na mensagem."""
    try:
        return ezdxf.readfile(filepath)
    except Exception as exc:
        motivo = f"{type(exc).__name__}: {exc}"
        try:
            return recuperar_dxf(filepath, motivo)
        except Exception as erec:
            raise RuntimeError(
                f"não abriu nem com ezdxf.recover: {filepath} — "
                f"normal: {motivo} | recover: {type(erec).__name__}: {erec}")
