# Getting started with ZXLive

ZXLive is a visual proof assistant for ZX-diagrams. ZX-diagrams are a graphical language for reasoning about quantum processes. If you don't know what ZX-diagrams are, check out [the ZX-calculus website](https://zxcalculus.com/).

You can install ZXLive using pip:

```
	pip install zxlive
```

You can then run it using `python -m zxlive`.

:::{warning} 
ZXLive currently does not run on older versions of MacOS, due to a lack of support for the newer versions of Qt.
:::

When you open ZXLive for the first time, you will see a window that looks something like this:

```{figure} _static/mainwindow.png
:scale: 50 %
:alt: The ZXLive editor window

The ZXLive editor window
```
This is the ***editor mode***. In this mode you can freely edit the diagram. There are three main tools

```{figure} _static/toolbar.png
:scale: 100 %
:alt: ZXLive toolbar

The editing tools: Select (s), Add vertex (v), and Add edge (e).
```
With the Select tool active you can select any part of the graph by dragging a box, or directly clicking on vertices or edges, using the left mouse button. Control- or shift-clicking adds to the selection.
With the Add vertex tool or Add edge