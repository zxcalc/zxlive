# ZXLive changelog


## Unreleased

### New features

- Added fault-equivalent rewrites, a set of rewrites that preserve the fault tolerance of a diagram, together with a fault weight threshold for the rewrites that are only fault-equivalent up to a given weight (#427).
- The edge tool now lets you draw multiple parallel edges simultaneously by selecting multiple vertices before clicking and dragging (#521).
- Added an interactive tutorial that guides you through the basics of ZXLive, which is shown on first launch and can be accessed again from the **Help > Tutorial** menu (#530).
- Added a "View > Features" menu for showing or hiding optional features (fault-equivalent rewrites, ZW-calculus vertices and Pauli webs) (#553).
- Optional features are now all disabled by default, and ZXLive asks which ones you want on first launch, right after the tutorial (#563).
- Added an auto-arrange command that rearranges vertices using a spring layout algorithm, accessible from the Edit menu (#500).
- The patterns sidebar now shows a rendered diagram preview when hovering over a pattern entry (#574).
- Added a dedicated font-size setting for graph vertex labels (spider phases and dummy vertex text), independent of the application UI font (#575).
- Added an option to always expand all sections of the rewrite rules sidebar when entering proof mode (#567).

### Improvements

- Changed graph canvases to start around their diagrams and grow dynamically, so diagrams far from the origin remain visible when entering proof mode (#526).
- Changed the Ctrl+A shortcut to only select vertices and no longer select edges in order to improve performance (#515)
- Selection is now preserved when applying rewrites in proof mode, so users no longer need to re-select after each step (#506).
- When nothing is selected in proof mode, rewrites now apply to the full graph rather than being ignored (#525).
- Windows release binaries are now code-signed (certificate provided by SignPath Foundation), removing "potential malware" warnings for most Windows users (#524).
- Applying the Hopf rule now displays a fade-out animation for the removed parallel edges (#496).
- When pasting TikZ from the clipboard encounters parse errors, ZXLive now lets users choose to retry ignoring the errors instead of failing silently (#539).

### Fixes

- Fixed TikZ proof export so that graphs offset from the origin are normalised, equal signs are vertically centred between adjacent steps, and row wrapping works correctly (#198).
- Fixed a bug which caused the list of available rewrites in proof mode to not be updated until the mouse was hovered over the rewrite panel (#465)
- Fixed closing a tab leaking its panel, so proofs no longer retain their diagram, history and rewrite worker thread after being closed (#562).
- Fixed release binaries missing runtime assets (icons, data files), which could cause errors on first launch (#554).
- Fixed a crash that occurred when reapplying a rewrite that had been saved as a lemma (#520).
- Fixed visual tearing of the background grid that occurred while scrolling (#546).
- Fixed a bug where symbolic parameters were not correctly matched to phases when applying custom rewrite rules (#548).
- Fixed the magic wand's Hopf rule failing to match diagrams with X spiders (#551).
- Fixed phase labels on boundary vertices sometimes showing stale values (#479, fixes #462).
- Fixed right-clicking empty canvas space opening "Add selection to patterns" instead of creating a new vertex when other items were selected (#570).


## v1.0.0
This is the first version where changes were tracked. This version 1.0.0 release brings with it many new features, including:

- First-class support for working with multigraphs: you can now apply complementarity to your heart's content.
- Support for parametrised phases: you can give spiders a phase that contains parameters, such as expressions like `pi/2+a*pi`, where you can specify that `a` has to be a Boolean phase. Several standard rewrites understand when they should apply to parametrised phases.
- Creating custom rewrite rules and using them in your proofs.
- Saving your proofs or exporting them to tikz to be used in your papers.
- Visualising and calculating with Pauli webs on Clifford diagrams.
- Ability to save parts of a diagram as a pattern, to be easily added later to new diagrams.
- Many, many bug fixes and improvements to usability