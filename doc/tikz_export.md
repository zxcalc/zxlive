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

### Setting Up Your LaTeX Document

1. Download the [tikzit.sty](_static/tikzit.sty) file and place it in the same directory as your LaTeX document.
2. Include the following in your LaTeX document preamble:

```latex
\usepackage{tikzit}
```

### Quick Start: Download the Style File

The easiest way to get started is to download our pre-made style file:

[Download zx.tikzstyles](_static/zx.tikzstyles)

Place this file in the same directory as your LaTeX document and include it in your preamble:

```latex
\usepackage{tikzit}
\input{zx.tikzstyles}
```

That's it! You can now include your exported TikZ diagrams.

### Complete LaTeX Template

Here's a complete minimal LaTeX document template that you can use:

```latex
\documentclass{article}
\usepackage{tikzit}
\input{zx.tikzstyles} % or define your own styles here

\begin{document}

% Include your exported TikZ file
A tikz picture as an equation:
\begin{equation}
  \tikzfig{your-exported-diagram.tikz}
\end{equation}

A centered tikz picture:
\ctikzfig{your-exported-diagram.tikz}

\end{document}
```

## Using with TikZit

ZXLive's TikZ exports are compatible with [TikZit](https://tikzit.github.io/), a graphical tool for creating and editing TikZ diagrams. You can:

1. Export from ZXLive to a `.tikz` file
2. Open the file in TikZit for further editing
3. Use TikZit's style editor to create custom styles

## TikZ export settings in ZXLive

### Customizing style names

ZXLive allows you to customize the TikZ class names used during export. You can configure this in:

**Settings > TikZ > Export**

### Layout Customization

This allows you to use custom style names that match your existing LaTeX style definitions.

You can adjust the layout of exported proofs in:

**Settings > TikZ > Layout**

Available settings:
- **Horizontal spacing**: Space between diagrams in a proof horizontally
- **Vertical spacing**: Space between rows of diagrams
- **Maximum width**: Maximum width before wrapping to a new row

### Rule Name Customization

When exporting proofs, rewrite rule names appear between diagrams. You can customize these labels in:

**Settings > TikZ > Rule names**

This is useful for using shorter notation (e.g., "f" for "fuse spiders", "b" for "bialgebra") in your exported diagrams.

## Troubleshooting

If you encounter compilation errors:

1. **Missing packages**: Make sure tikzit.sty is included and accessible in your LaTeX document directory.
2. **Undefined styles**: Verify that all style definitions are in your .tikzstyles file and that the style names match those in ZXLive's export settings

