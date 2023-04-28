from __future__ import annotations
from PySide2.QtCore import QByteArray, QSettings
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import pyzx as zx
from pyzx.utils import EdgeType, VertexType, toggle_edge, toggle_vertex
import copy
import numpy as np



def phase_change(v, input):
    '''
    g: BaseGraph[[VT.ET]]
    v: vertex or node, from VT
    input: Phase in fraction/integer, viewed as a multiple of pi
    returns: the graph after the change of phase
    '''
    g = v.g
    v = v.v
    g.set_phase(v, input)
    return g

def edit_node_color(v):
    '''
    g: baseGraph[[VT,ET]]
    v: vertex or node
    returns: toggled node color
    '''
    g = v.g
    v = v.v
    g.set_type(v, toggle_vertex(g.type(v)))
    return g

def color_change(v):
    '''
    g: BaseGraph[[VT.ET]]
    v: node or vertex
    returns: Applies hadamard on the edges and changes the color of the node
    '''
    g = v.g
    v = v.v
    g.set_type(v, toggle_vertex(g.type(v)))
    for e in g.incident_edges(v):
        et = g.edge_type(e)
        g.set_edge_type(e, toggle_edge(et))
    return g

def bialgebra(v_list):
    '''
    g: BaseGraph[[VT,ET]]
    v_list: list of vertex where bialgebra needs to be applied
    returns: The graph with bialgebra rule applied if the vertices provided can be simplified by this rule
    '''
    g = v_list[0].g
    phases = g.phases()
    x_vertices = []
    z_vertices = []

    for v in v_list:
        if phases[v.v]!=0:
            return g
        if g.type(v.v)==VertexType.X:
            x_vertices.append(v.v)
        else:
            z_vertices.append(v.v)
    
    # print([g.qubit(x) for x in x_vertices])
    # print([g.row(x) for x in x_vertices])
    xqr = (max(min([g.qubit(x) for x in x_vertices]),0), max(min([g.row(x) for x in x_vertices]),0))
    zqr = (max([g.qubit(z) for z in z_vertices]), max([g.row(z) for z in z_vertices]))
    
    x_len = len(x_vertices)
    z_len = len(z_vertices)
    for v in x_vertices:
        if g.vertex_degree(v)!=z_len+1:
            return g
        for z in z_vertices:
            if v not in g.neighbors(z):
                return g
        for u in x_vertices:
            if (min(u,v),max(u,v)) in g.edge_set():
                return g
            elif g.edge_type(g.edge(u,v)) == EdgeType.HADAMARD:
                return g
    for v in z_vertices:
        if g.vertex_degree(v)!=x_len+1:
            return g
        for x in x_vertices:
            if v not in g.neighbors(x):
                return g
        for u in z_vertices:
            if (min(u,v),max(u,v)) in g.edge_set():
                return g
            elif g.edge_type(g.edge(u,v)) == EdgeType.HADAMARD:
                return g

    u = x_vertices[0]
    v = x_vertices[-1]
    # r = 0.5*(g.row(u) + g.row(v))
    # q = 0.5*(g.qubit(u) + g.qubit(v))
    # print("zqr : ", zqr)
    (q,r) = zqr

    a = g.add_vertex(VertexType.Z,q,r)
    for v in x_vertices:
        for n in g.neighbors(v):
            g.add_edge((min(a,n),max(a,n)),1)
        g.remove_vertex(v)

    u = z_vertices[0]
    v = z_vertices[-1]
    # r = 0.5*(g.row(u) + g.row(v))
    # q = 0.5*(g.qubit(u) + g.qubit(v))
    # print("xqr : ", xqr)
    (q,r) = xqr
    b = g.add_vertex(VertexType.X,q,r)
    for v in z_vertices:
        for n in g.neighbors(v):
            g.add_edge((min(b,n),max(b,n)),1)
        g.remove_vertex(v)
    return g

def Hadamard_slide(v):
    '''
    g: BaseGraph[[VT,ET]]
    v: node or vertex 
    returns: absorbs the hadamard appropriately if the node phase is pi/2
    '''
    g = v.g
    v = v.v
    if g.vertex_degree(v)!=2:
        print('out1')
        return g
    elif abs(g.phase(v))!= 1/2:
        return g
    elif g.edge_type(g.incident_edges(v)[0])==EdgeType.SIMPLE and g.edge_type(g.incident_edges(v)[1])==EdgeType.SIMPLE :
        print('out3')
        return g
    g.set_phase(v,-g.phase(v))
    for u in g.neighbors(v):
        e = g.edge(u,v)
        if g.edge_type(e)==EdgeType.SIMPLE:
            a = g.add_vertex(toggle_vertex(g.type(v)), g.qubit(v), g.row(v)+1, g.phase(v))
        else:
            g.set_edge_type(e,toggle_edge(e))
    g.add_edge(g.edge(v,a),1)
    g.add_edge(g.edge(u,a),1)
    g.remove_edge(e)
    return g


def add_node(u,v):
    '''
    g: BaseGraph[[VT,ET]]
    u: node 1
    v: node 2
    returns: Adds a node between these two nodes and connect it via regular edge
    '''
    g = u.g
    u = u.v
    v = v.v
    
    if (u,v) not in g.edge_set():
        g.add_edge((min(u,v), max(u,v)),1)
    e = g.edge(u,v)
    et = g.edge_type(e)
    r = 0.5*(g.row(u) + g.row(v))
    q = 0.5*(g.qubit(u) + g.qubit(v))
    w = g.add_vertex(VertexType.Z, q,r, 0)
    if et==EdgeType.SIMPLE:
        g.add_edge((min(u,w), max(u,w)),1)
        g.add_edge((min(v,w), max(v,w)),1)
    elif g.type(u)==g.type(v) :
        g.add_edge((min(u,w), max(u,w)),1)
        g.add_edge((min(v,w), max(v,w)),2)
    else:
        return g
    g.remove_edge(g.edge(u,v))
    return g

def add_wire(u,v):
    '''
    g: BaseGraph[[VT,ET]]
    u: node 1
    v: node 2
    returns: Toggles the wire between two nodes. If the nodes are of different colors, then toggles the edge, otherwise does nothing.
    '''
    g = u.g
    u = u.v
    v = v.v
    if g.type(u) == g.type(v):
        g.add_edge((min(u,v), max(u,v)),1)
    elif (min(u,v),max(u,v)) in g.edge_set():
        g.remove_edge(g.edge(u,v))
    else:
        g.add_edge((min(u,v), max(u,v)),1)

    return g

def swap(a,b):
    t = a
    a = b
    b = t
    return (a,b)


def fusion(a,b):
    '''
    g: BaseGraph[[VT,ET]]
    a: node 1
    b: node 2
    returns: fuses two nodes if of the same type, otherwise does nothing
    '''
    g = a.g
    v = a.v
    w = b.v
    if g.type(v)!=g.type(w):
        return g
    else:
        if w<v:
            (v,w) = swap(v,w)
        if (v,w) in g.edge_set():
            e = g.edge(v,w)
            if g.edge_type(e)!= EdgeType.SIMPLE:
                return g
            else :
                g.add_to_phase(v, g.phase(w))
            for u in g.neighbors(w):
                # #print("neigh : ", u, w, v)
                if u != v:
                    if (min(u,v), max(u,v)) in g.edge_set():
                        g.remove_edge(g.edge(u,v))
                        # #print("removed : ", u, v)
                    else:
                        g.add_edge((min(u,v), max(u,v)), 1)
                        # #print("added : ", u, v)


            g.remove_edge(e)
            g.remove_vertex(w)
            # #print("removed2 : ", e)

    return g

def identity(a):
    '''
    g: BaseGraph[[VT,ET]]
    a: node 
    returns: If node is bivalent then removes the node
    '''
    g = a.g
    a = a.v
    if g.vertex_degree(a)==2:
        if g.phase(a) == 0:
            (u,v) = g.neighbors(a)
            if g.edge_type(g.edge(a,u)) == g.edge_type(g.edge(a,u)):
                if g.edge_type(g.edge(a,u)) == EdgeType.SIMPLE:
                    g.add_edge((min(u,v),max(u,v)),1)
                    g.remove_vertex(a)
    return g

def GH_graph(g):
    '''
    g: BaseGraph[[VT,ET]]
    returns: returns the graph with only Z spiders and hadamard appropriately
    '''
    lst_vertices = list(g.vertices())
    for v in lst_vertices:
        if g.type(v) == VertexType.X:
            g.set_type(v, toggle_vertex(g.type(v)))
            for e in g.incident_edges(v):
                et = g.edge_type(e)
                g.set_edge_type(e, toggle_edge(et))
    return g

    
