# Exporting to TikZ and LaTeX

ZXLive allows you to export your ZX-diagrams and proofs to TikZ format, which can be included in LaTeX documents. This is particularly useful for creating papers, presentations, and other academic materials.

## Exporting from ZXLive

To export a proof to TikZ:

1. Open a proof in ZXLive (you must be in "Proof mode" to export proofs)
2. Go to **File > Export proof to tikz**
3. Choose a location and filename for your `.tikz` file
4. Save the file

The exported file will contain TikZ code that represents your entire proof as a series of diagrams with rewrite steps labeled between them.

## Setting up LaTeX

To use the exported TikZ diagrams in your LaTeX documents, you need to set up your preamble with the required packages and style definitions.

### Quick Start: Download the Style File

The easiest way to get started is to download our pre-made style file:

[Download zxlive-tikz-styles.sty](_static/zxlive-tikz-styles.sty)

Place this file in the same directory as your LaTeX document and include it in your preamble:

```latex
\usepackage{zxlive-tikz-styles}
```

That's it! You can now include your exported TikZ diagrams.

### Manual Setup (Alternative)

If you prefer to include the styles directly in your document, follow the instructions below.

### Required Packages

Add these packages to your LaTeX document preamble:

```latex
\usepackage{tikz}
\usetikzlibrary{cd}
\usetikzlibrary{calc}
```

### TikZ Style Definitions

You need to define the styles used by ZXLive's TikZ export. Add these definitions to your preamble:

```latex
% Define layers for nodes and edges
\pgfdeclarelayer{nodelayer}
\pgfdeclarelayer{edgelayer}
\pgfsetlayers{nodelayer,edgelayer}

% ZX-calculus node styles
\tikzstyle{none}=[inner sep=0pt]
\tikzstyle{Z dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{X dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{Z phase dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{X phase dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{hadamard}=[rectangle, fill=yellow!50, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{Z box}=[rectangle, fill=white, draw=black, line width=0.8pt, minimum size=8mm]
\tikzstyle{W triangle}=[regular polygon, regular polygon sides=3, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{W input}=[regular polygon, regular polygon sides=3, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{text}=[inner sep=2pt]

% Edge styles
\tikzstyle{hadamard edge}=[-, draw=blue, line width=1.2pt, dashed]
\tikzstyle{W io edge}=[-, draw=black, line width=1.2pt, double]
```

### Complete LaTeX Template

Here's a complete minimal LaTeX document template that you can use:

```latex
\documentclass{article}
\usepackage{tikz}
\usetikzlibrary{cd}
\usetikzlibrary{calc}
\usetikzlibrary{shapes.geometric}  % For triangles and polygons

% Define layers
\pgfdeclarelayer{nodelayer}
\pgfdeclarelayer{edgelayer}
\pgfsetlayers{nodelayer,edgelayer}

% ZX-calculus node styles
\tikzstyle{none}=[inner sep=0pt]
\tikzstyle{Z dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{X dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{Z phase dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{X phase dot}=[circle, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{hadamard}=[rectangle, fill=yellow!50, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{Z box}=[rectangle, fill=white, draw=black, line width=0.8pt, minimum size=8mm]
\tikzstyle{W triangle}=[regular polygon, regular polygon sides=3, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{W input}=[regular polygon, regular polygon sides=3, fill=white, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{text}=[inner sep=2pt]

% Edge styles
\tikzstyle{hadamard edge}=[-, draw=blue, line width=1.2pt, dashed]
\tikzstyle{W io edge}=[-, draw=black, line width=1.2pt, double]

\begin{document}

% Include your exported TikZ file
\input{your-exported-diagram.tikz}

\end{document}
```

## Including TikZ Files in Your Document

Once you have set up the preamble, you can include your exported TikZ files using the `\input` command:

```latex
\input{myproof.tikz}
```

Or you can directly paste the TikZ code into your document:

```latex
\begin{figure}[h]
\centering
\begin{tikzpicture}
    % ... TikZ code from your export ...
\end{tikzpicture}
\caption{My ZX-diagram proof}
\end{figure}
```

## Customizing Styles

You can customize the appearance of your diagrams by modifying the TikZ style definitions. For example:

- Change node colors by modifying the `fill` parameter
- Adjust node sizes with the `minimum size` parameter
- Change line widths and styles
- Modify edge appearance

### Example Customizations

To make Z spiders green and X spiders red:

```latex
\tikzstyle{Z dot}=[circle, fill=green!30, draw=black, line width=0.8pt, minimum size=5mm]
\tikzstyle{X dot}=[circle, fill=red!30, draw=black, line width=0.8pt, minimum size=5mm]
```

## Customizing Styles in ZXLive

ZXLive also allows you to customize the TikZ class names used during export. You can configure this in:

**Settings > TikZ > Export**

This allows you to use custom style names that match your existing LaTeX style definitions.

## Layout Settings

You can adjust the layout of exported proofs in:

**Settings > TikZ > Layout**

Available settings:
- **Horizontal spacing**: Space between diagrams in a proof horizontally
- **Vertical spacing**: Space between rows of diagrams
- **Maximum width**: Maximum width before wrapping to a new row

## Rule Name Customization

When exporting proofs, rewrite rule names appear between diagrams. You can customize these labels in:

**Settings > TikZ > Rule names**

This is useful for using shorter notation (e.g., "f" for "fuse spiders", "b" for "bialgebra") in your exported diagrams.

## Troubleshooting

### Compilation Errors

If you encounter compilation errors:

1. **Missing packages**: Make sure all required packages are installed (tikz, calc, shapes.geometric)
2. **Undefined styles**: Verify that all style definitions are in your preamble
3. **Missing layers**: Ensure pgfdeclarelayer commands are before \begin{document}

### Diagram Appearance

If diagrams don't look right:

1. Check that you've included the shapes.geometric library for triangular nodes
2. Verify that style names in ZXLive's export settings match your LaTeX definitions
3. Try adjusting the minimum size parameters if nodes appear too large or small

### Using with TikZit

ZXLive's TikZ exports are compatible with [TikZit](https://tikzit.github.io/), a graphical tool for creating and editing TikZ diagrams. You can:

1. Export from ZXLive to a `.tikz` file
2. Open the file in TikZit for further editing
3. Use TikZit's style editor to create custom styles

## Additional Resources

- [TikZ & PGF Manual](http://mirrors.ctan.org/graphics/pgf/base/doc/pgfmanual.pdf)
- [TikZit Project](https://tikzit.github.io/)
- [ZX-calculus Website](https://zxcalculus.com/)
- [PyZX Documentation](https://pyzx.readthedocs.io/)
