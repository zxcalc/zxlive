from .poly import Poly, new_var, new_const

from typing import List, Any
from lark import Lark, Transformer
from functools import reduce
from operator import add, mul
from fractions import Fraction

poly_grammar = Lark("""
    start      : "(" start ")" | term ("+" term)*
    term       : factor ("*" factor)*
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

class PolyTransformer(Transformer):
    def start(self, items: List[Poly]) -> Poly:
        return reduce(add, items)

    def term(self, items: List[Poly]) -> Poly:
        return reduce(mul, items)

    def var(self, items: List[Any]) -> Poly:
        v = str(items[0])
        # TODO: implement is_bool logic here
        return new_var(v, is_bool=True)

    def pi(self, _: List[Any]) -> Poly:
        return new_const(1)

    def intf(self, items: List[Any]) -> Poly:
        return new_const(int(items[0]))

    def frac(self, items: List[Any]) -> Poly:
        return new_const(Fraction(int(items[0]), int(items[1])))

    def pifrac(self, items: List[Any]) -> Poly:
        numerator = int(items[0]) if items[0] else 1
        return new_const(Fraction(numerator, int(items[2])))

def parse(expr: str) -> Poly:
    tree = poly_grammar.parse(expr)
    return PolyTransformer().transform(tree)
