from .poly import Poly, new_const

from typing import Any, Callable
from lark import Lark, Transformer
from functools import reduce
from operator import add, mul
from fractions import Fraction

poly_grammar = Lark("""
    start      : "(" start ")" | term ("+" term)*
    term       : (intf | frac)? factor ("*" factor)*
    ?factor    : intf | frac | pi | pifrac | var
    var        : CNAME
    intf       : INT
    pi         : "\\pi" | "pi"
    frac       : INT "/" INT
    pifrac     : [INT] pi "/" INT

    %import common.INT
    %import common.CNAME
    %import common.WS
    %ignore WS
    """,
    parser='lalr',
    maybe_placeholders=True)

class PolyTransformer(Transformer[Poly]):
    def __init__(self, new_var: Callable[[str], Poly]):
        super().__init__()

        self._new_var = new_var

    def start(self, items: list[Poly]) -> Poly:
        return reduce(add, items)

    def term(self, items: list[Poly]) -> Poly:
        return reduce(mul, items)

    def var(self, items: list[Any]) -> Poly:
        v = str(items[0])
        return self._new_var(v)

    def pi(self, _: list[Any]) -> Poly:
        return new_const(1)

    def intf(self, items: list[Any]) -> Poly:
        return new_const(int(items[0]))

    def frac(self, items: list[Any]) -> Poly:
        return new_const(Fraction(int(items[0]), int(items[1])))

    def pifrac(self, items: list[Any]) -> Poly:
        numerator = int(items[0]) if items[0] else 1
        return new_const(Fraction(numerator, int(items[2])))

def parse(expr: str, new_var: Callable[[str], Poly]) -> Poly:
    tree = poly_grammar.parse(expr)
    return PolyTransformer(new_var).transform(tree)
