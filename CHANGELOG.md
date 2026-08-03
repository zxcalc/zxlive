# ZXLive changelog


## Unreleased

- Fixed TikZ proof export so that graphs offset from the origin are normalised, equal signs are vertically centred between adjacent steps, and row wrapping works correctly (#198).


## v1.0.0
This is the first version where changes were tracked. This version 1.0.0 release brings with it many new features, including:

- First-class support for working with multigraphs: you can now apply complementarity to your heart's content.
- Support for parametrised phases: you can give spiders a phase that contains parameters, such as expressions like `pi/2+a*pi`, where you can specify that `a` has to be a Boolean phase. Several standard rewrites understand when they should apply to parametrised phases.
- Creating custom rewrite rules and using them in your proofs. 
- Saving your proofs or exporting them to tikz to be used in your papers.
- Visualising and calculating with Pauli webs on Clifford diagrams.
- Ability to save parts of a diagram as a pattern, to be easily added later to new diagrams.
- Many, many bug fixes and improvements to usability