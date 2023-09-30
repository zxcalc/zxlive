from fractions import Fraction
from typing import Union

class Var:
    name: str
    is_bool: bool

    def __init__(self, name, data: bool | dict[str, bool]):
        self.name = name
        if isinstance(data, dict):
            self._types_dict = data
            self._frozen = False
            self._is_bool = False
        else:
            self._types_dict = None
            self._frozen = True
            self._is_bool = data

    @property
    def is_bool(self) -> bool:
        if self._frozen:
            return self._is_bool
        else:
            return self._types_dict[self.name]

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        if int(self.is_bool) == int(other.is_bool):
            return self.name < other.name
        return int(self.is_bool) < int(other.is_bool)

    def __hash__(self):
        # Variables with the same name map to the same type
        # within the same graph, so no need to include is_bool
        # in the hash.
        return hash(self.name)

    def __eq__(self, other) -> bool:
        return self.__hash__() == other.__hash__()

    def freeze(self) -> None:
        if not self._frozen:
            self._is_bool = self._types_dict[self.name]
            self._frozen = True
            self._types_dict = None

    def __copy__(self):
        if self._frozen:
            return Var(self.name, self.is_bool)
        else:
            return Var(self.name, self._types_dict)

    def __deepcopy__(self, _memo):
        return self.__copy__()

class Term:
    vars: list[tuple[Var, int]]

    def __init__(self, vars):
        self.vars = vars

    def freeze(self) -> None:
        for var, _ in self.vars:
            var.freeze()

    def free_vars(self) -> set[Var]:
        return set(var for var, _ in self.vars)

    def __repr__(self) -> str:
        vs = []
        for v, c in self.vars:
            if c == 1:
                vs.append(f'{v}')
            else:
                vs.append(f'{v}^{c}')
        return '*'.join(vs)

    def __mul__(self, other):
        vs = dict()
        for v, c in self.vars + other.vars:
            if v not in vs: vs[v] = c
            else: vs[v] += c
            # TODO deal with fractional / symbolic powers
            if v.is_bool and c > 1:
                vs[v] = 1
        return Term([(v, c) for v, c in vs.items()])

    def __hash__(self):
        return hash(tuple(sorted(self.vars)))

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()


class Poly:
    terms: list[tuple[Union[int, float, Fraction], Term]]

    def __init__(self, terms):
        self.terms = terms

    def freeze(self) -> None:
        for _, term in self.terms:
            term.freeze()

    def free_vars(self) -> set[Var]:
        output = set()
        for _, term in self.terms:
            output.update(term.free_vars())
        return output

    def __add__(self, other):
        if isinstance(other, (int, float, Fraction)):
            other = Poly([(other, Term([]))])
        counter = dict()
        for c, t in self.terms + other.terms:
            if t not in counter: counter[t] = c
            else: counter[t] += c
            if all(tt[0].is_bool for tt in t.vars):
                counter[t] = counter[t] % 2

        # remove terms with coefficient 0
        for t in list(counter.keys()):
            if counter[t] == 0:
                del counter[t]
        return Poly([(c, t) for t, c in counter.items()])

    __radd__ = __add__

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            other = Poly([(other, Term([]))])
        p = Poly([])
        for c1, t1 in self.terms:
            for c2, t2 in other.terms:
                p += Poly([(c1 * c2, t1 * t2)])
        return p

    __rmul__ = __mul__

    def __repr__(self):
        ts = []
        for c, t in self.terms:
            if t == Term([]):
                ts.append(f'{c}')
            elif c == 1:
                ts.append(f'{t}')
            else:
                ts.append(f'{c}{t}')
        return ' + '.join(ts)

    def __eq__(self, other):
        if isinstance(other, (int, float, Fraction)):
            if other == 0:
                other = Poly([])
            else:
                other = Poly([(other, Term([]))])
        return set(self.terms) == set(other.terms)

    @property
    def is_pauli(self):
        for c, t in self.terms:
            if not all(v.is_bool for v, _ in t.vars):
                return False
            if c % 1 != 0:
                return False
        return True

def new_var(name, types_dict):
    return Poly([(1, Term([(Var(name, types_dict), 1)]))])

def new_const(coeff):
    return Poly([(coeff, Term([]))])
