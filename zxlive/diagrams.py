import pyzx as zx


def to_tikz(g):
  '''
  g: BaseGraph[[VT,ET]]
  returns: A string representing 'g' as a tikz diagram
  '''
  return zx.to_tikz(g)

def tikz_to_graph(s,
                  warn_overlap= True,
                  fuse_overlap = True,
                  ignore_nonzx= False):
  '''
  s: String containing well-defined tikz diagram
  warn_overlap: If True raises a Warning if two vertices have the exact same position.
  fuse_overlap: If True fuses two vertices that have the exact same position. Only has effect if fuse_overlap is False.
  ignore_nonzx: If True suppresses most errors about unknown vertex/edge types and labels.
  returns: BaseGraph for the tikz diagram provided
  '''
  return zx.tikz_to_graph(s,warn_overlap, fuse_overlap, ignore_nonzx)
  
