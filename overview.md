# ZXLive Codebase Overview

## Project Description

ZXLive is an interactive tool for working with the ZX-calculus, a graphical language for quantum computations. It provides a visual interface for drawing ZX-diagrams, applying rewrite rules, and building proofs. The application is built using PySide6 (Qt) and integrates with the PyZX library for ZX-calculus operations.

## Architecture Overview

### Core Architecture
- **GUI Framework**: PySide6 (Qt6) for cross-platform desktop application
- **Backend**: PyZX library for ZX-calculus operations and graph manipulation
- **Language**: Python 3.9+ with type hints
- **Build System**: setuptools with pyproject.toml configuration

### Main Entry Points
- `zxlive/app.py`: Main application class (`ZXLive`) and entry points
- `zxlive/__main__.py`: Command-line entry point
- `zxlive/mainwindow.py`: Main window and application shell

## Core Components

### 1. Application Layer (`app.py`)
- **ZXLive Class**: Main QApplication subclass
- Handles application lifecycle, window management, and command-line arguments
- Supports both standalone and embedded (Jupyter notebook) modes
- Manages global application settings and resources

### 2. Main Window (`mainwindow.py`)
- **MainWindow Class**: Central application window with tabbed interface
- Manages multiple document tabs (graphs, proofs, rules)
- Handles file operations (open, save, export)
- Provides menu system and keyboard shortcuts
- Manages undo/redo functionality across all panels

### 3. Panel System

#### Base Panel (`base_panel.py`)
- **BasePanel Class**: Abstract base for all panel types
- Provides common functionality: toolbar, undo stack, graph display
- Handles graph operations: copy, paste, delete, select
- Manages splitter layouts and panel-specific settings

#### Edit Panel (`edit_panel.py`)
- **GraphEditPanel Class**: Interactive graph editing mode
- Supports vertex/edge creation and manipulation
- Circuit input functionality (QASM, Spider QASM)
- "Start Derivation" button to begin proof construction

#### Proof Panel (`proof_panel.py`)
- **ProofPanel Class**: Interactive proof construction mode
- Magic wand tool for applying rewrite rules
- Drag-and-drop vertex operations for rule application
- Integration with proof step view and rewrite action tree

#### Rule Panel (`rule_panel.py`)
- **RulePanel Class**: Custom rule editor
- Side-by-side editing of left-hand and right-hand sides
- Rule validation and export functionality
- Auto-detection of input/output boundaries

### 4. Graph Visualization System

#### Graph Scene (`graphscene.py`)
- **GraphScene Class**: Qt graphics scene for graph rendering
- **EditGraphScene Class**: Extended scene with editing capabilities
- Manages vertex and edge graphics items
- Handles mouse events for editing operations
- Supports selection, dragging, and context menus

#### Graph View (`graphview.py`)
- **GraphView Class**: Qt graphics view for graph display
- **ProofGraphView Class**: Extended view for proof mode with scalar display
- **RuleEditGraphView Class**: Specialized view for rule editing
- Handles zooming, panning, and view transformations
- Implements magic wand tool and sparkle effects

#### Graphics Items
- **VItem** (`vitem.py`): Vertex graphics items with different types (Z, X, H-box, W-nodes, etc.)
- **EItem** (`eitem.py`): Edge graphics items with curve support
- **PhaseItem**: Text labels for vertex phases
- Support for animations and visual feedback

### 5. Proof System

#### Proof Model (`proof.py`)
- **ProofModel Class**: Qt model for proof step management
- **Rewrite Class**: Individual proof step representation
- **ProofStepView Class**: List view for proof steps with git-style visualization
- Supports step grouping, renaming, and navigation
- Serialization to/from JSON format

#### Rewrite Actions (`rewrite_action.py`)
- **RewriteAction Class**: Individual rewrite rule representation
- **RewriteActionTree Class**: Hierarchical organization of rules
- **RewriteActionTreeModel Class**: Qt model for rule tree display
- **RewriteActionTreeView Class**: Tree view for rule selection
- Supports custom rules and built-in PyZX rules

### 6. Command System (`commands.py`)
- **BaseCommand Class**: Abstract base for undoable operations
- **SetGraph/UpdateGraph**: Graph replacement and modification
- **AddNode/AddEdge**: Graph construction operations
- **MoveNode/ChangeEdgeCurve**: Graph manipulation operations
- **AddRewriteStep**: Proof construction operations
- **ProofModeCommand**: Wrapper for proof-specific commands

### 7. Custom Rules (`custom_rule.py`)
- **CustomRule Class**: User-defined rewrite rules
- Graph isomorphism matching using NetworkX
- Symbolic parameter handling
- Rule validation and verification
- Support for unfusable rules and boundary detection

### 8. Common Utilities (`common.py`)
- Type definitions and constants
- Settings management (QSettings integration)
- Coordinate system conversions
- TikZ import/export functionality
- Graph creation and manipulation helpers

## Key Features

### Interactive Graph Editing
- Visual graph construction with drag-and-drop
- Multiple vertex types: Z-spiders, X-spiders, H-boxes, W-nodes, boundaries
- Edge types: simple, Hadamard, W-IO connections
- Grid snapping and alignment tools
- Real-time graph validation

### Proof Construction
- Interactive proof building with visual feedback
- Magic wand tool for rule application
- Step-by-step proof navigation
- Proof step grouping and organization
- Export to TikZ and GIF formats

### Custom Rule System
- Visual rule editor with side-by-side editing
- Graph isomorphism matching
- Symbolic parameter support
- Rule validation and testing
- Import/export of custom rules

### File Format Support
- Native ZXLive format (.zxg, .zxp, .zxr)
- TikZ format for LaTeX integration
- QASM circuit format
- JSON serialization
- Matrix export functionality

### User Interface
- Tabbed document interface
- Dark/light theme support
- Customizable toolbars and shortcuts
- Sound effects and animations
- Context menus and tooltips

## Dependencies

### Core Dependencies
- **PySide6**: Qt6 Python bindings for GUI
- **PyZX**: ZX-calculus library for graph operations
- **NetworkX**: Graph algorithms and isomorphism matching
- **NumPy**: Numerical computations
- **Shapely**: Geometric operations

### Optional Dependencies
- **pyperclip**: Clipboard operations
- **imageio**: GIF export functionality

## Development and Testing

### Code Quality
- Type hints throughout the codebase
- MyPy static type checking
- Flake8 linting
- Pytest for unit testing

### Documentation
- Sphinx-based documentation
- MyST parser for Markdown support
- ReadTheDocs integration
- Inline code documentation

## File Organization

```
zxlive/
├── app.py              # Main application class
├── mainwindow.py       # Main window and shell
├── base_panel.py       # Base panel functionality
├── edit_panel.py       # Graph editing panel
├── proof_panel.py      # Proof construction panel
├── rule_panel.py       # Custom rule editor panel
├── graphscene.py       # Graph visualization scene
├── graphview.py        # Graph display view
├── vitem.py           # Vertex graphics items
├── eitem.py           # Edge graphics items
├── proof.py           # Proof model and views
├── rewrite_action.py  # Rewrite rule system
├── commands.py        # Undo/redo command system
├── custom_rule.py     # Custom rule implementation
├── common.py          # Shared utilities
├── settings.py        # Application settings
├── dialogs.py         # Dialog boxes
├── animations.py      # Animation system
├── sfx.py            # Sound effects
├── tikz.py           # TikZ export
├── construct.py      # Graph construction helpers
└── icons/            # Application icons
```

## Extension Points

### Custom Rules
- Implement custom rewrite rules by extending the rule system
- Support for complex graph transformations
- Integration with the visual rule editor

### File Formats
- Add new import/export formats by extending the dialog system
- Support for additional circuit description languages
- Custom serialization formats

### UI Customization
- Theme system for visual customization
- Customizable toolbars and menus
- Plugin architecture for additional tools

This architecture provides a solid foundation for an interactive ZX-calculus tool with extensibility for future enhancements and customizations.
