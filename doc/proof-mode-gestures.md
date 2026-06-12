# Gestures and the magic wand

In ***Proof mode*** you cannot add or delete nodes and edges directly. Instead you transform the diagram by applying ZX rewrites. Besides picking rules from the rewrite panel on the left, ZXLive lets you apply many of the most common rewrites directly on the diagram with quick mouse *gestures*. These are fast and convenient, but they are not easy to discover, so this page collects them in one place.

The proof toolbar has two main tools that control how gestures behave:

```{figure} _static/proof_window_toolbar.png
:alt: The Proof window's toolbar
:align: center

The Proof window's toolbar. 1. Select mode (s), 2. Magic wand (w), 3. The type of spider the magic wand creates when drawn over a plain wire, 4. Undo (Ctrl-U) / Redo (Ctrl-Shift-U).
```

Press `s` for the **Select** tool (drag-and-drop and double-click gestures) and `w` for the **Magic wand** (stroke gestures). Every gesture below adds an entry to the rewrite history on the right, so any step can be reviewed or undone.

## Drag-and-drop gestures (Select mode)

With the Select tool active (`s`), drag one spider on top of an adjacent spider it shares a wire with. ZXLive works out which rewrite applies from the two spiders and their connecting wire, and previews it as you hover before you drop. If a single Hadamard wire connects the two spiders, ZXLive accounts for it automatically.

When more than one rewrite could apply, ZXLive picks the first that matches in the order **fuse > pi copy > push Pauli > strong complementarity (bialgebra)**.

### Spider fusion

Drag a spider onto an adjacent spider **of the same colour** to fuse them into one, adding their phases.

```{figure} _static/drag_fuse.gif
:alt: Fusing two spiders of the same colour
:align: center

Fusing two same-coloured spiders by dragging one onto the other; their phases add.
```

### Strong complementarity (bialgebra)

Drag a Z spider onto a connected X spider (or vice versa) to apply the bialgebra / strong complementarity rule.

```{figure} _static/bialgebra.gif
:alt: The bialgebra rule
:align: center

Applying the bialgebra rule to two complementary spiders by dragging one onto the other.
```

### Pi copy

Drag a Pauli spider (a phaseless spider, or one with a phase of π) onto a connected spider of the opposite colour to copy it through, placing a copy on each of the target spider's other neighbours.

```{figure} _static/drag_copy_pi.gif
:alt: Copying a Pauli spider through a spider of the opposite colour
:align: center

A π spider is copied through the connected spider, leaving a copy on each of its other legs.
```

### Pushing a Pauli

Drag a Pauli spider onto a connected spider of the opposite colour to push it through to the other side, copying it onto the far legs and negating the phase of the spider it passes through.

```{figure} _static/drag_push_pauli.gif
:alt: Pushing a Pauli spider through another spider
:align: center

Pushing a π spider through: it reappears on the far legs and the spider it passed through has its phase negated.
```

## Double-click gestures (Select mode)

Double-click a **Z or X spider** to change its colour (Z ↔ X), introducing Hadamard wires on its legs as required by the colour-change rule.

```{figure} _static/dblclick_color_change.gif
:alt: Changing the colour of a spider
:align: center

Double-clicking a spider flips its colour and turns its wires into Hadamard wires.
```

Double-click a **Hadamard wire** to expand it into an explicit Hadamard box, or double-click a **Hadamard box** to collapse it back into a Hadamard wire.

```{figure} _static/dblclick_hadamard.gif
:alt: Turning a Hadamard wire into a Hadamard box
:align: center

Double-clicking a Hadamard wire expands it into an explicit Hadamard box (and vice versa).
```

## Magic wand gestures

Switch to the magic wand with `w` (or the wand button in the toolbar) and draw a short stroke across the diagram with the left mouse button. What happens depends on what the stroke crosses.

### Add an identity spider

Draw the wand across a single wire to insert a two-legged (identity) spider into it. Use the **Z / X** toggle in the toolbar (item 3 above) to choose the colour of the spider that is added.

```{figure} _static/wand_add_identity.gif
:alt: Adding an identity spider to a wire
:align: center

Drawing the wand across a wire inserts a two-legged identity spider.
```

### Remove an identity spider

Draw the wand across a two-legged spider with a trivial (zero) phase to remove it, reconnecting its two wires. This is the inverse of adding an identity.

```{figure} _static/wand_remove_identity.gif
:alt: Removing an identity spider
:align: center

Drawing the wand across a phaseless two-legged spider removes it and rejoins the wire.
```

### Unfuse a spider

Draw the wand *through* a spider, crossing some of its legs, to split (unfuse) it into two connected spiders of the same colour. The legs on each side of the stroke go to the corresponding new spider, so the stroke decides how the wires are divided.

```{figure} _static/wand_unfuse.gif
:alt: Unfusing a spider into two
:align: center

Drawing the wand through a spider splits its legs between two connected spiders.
```

Hold **Shift** while drawing the stroke to be prompted for the phase to place on the newly split-off spider; the remaining phase stays on the original. Without Shift the whole phase stays on one side.

### Hopf rule (remove parallel edges)

Draw the wand across a bundle of parallel wires running between two connected spiders to apply the Hopf rule, which cancels the wires in pairs.

```{figure} _static/wand_hopf.gif
:alt: Removing parallel wires with the Hopf rule
:align: center

Drawing the wand across parallel wires between complementary spiders cancels them in pairs.
```
