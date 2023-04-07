# What's this?

This is a template project for developing a graphical front-end to the [pyzx](https://github.com/Quantomatic/pyzx) library. There isn't much here yet, but the goal is to develop a fast and user-friendly tool for editing quantum circuits and ZX diagrams and transforming them using the rules of the ZX calculus.

It's functionality is similar in spirit to the original [Quantomatic](https://github.com/Quantomatic/Quantomatic) tool, which was a general purpose diagrammatic proof assistant. The main goals for starting a new project is to build something simpler, faster, focused specifically on quantum computing with ZX, easily hackable in Python, and fun!

More info to come. Watch this space!


## Instructions

To install from source, you need Python >= 3.7 and pip. If you have those, just run:

    git clone https://github.com/Quantomatic/zxlive.git
    cd zxlive
    pip install .

Then, you can run a little demo by typing `python3 -m zxlive`.

If you have trouble with the pip versions of the PySide2 Python bindings for Qt5 (I did), you can install them manually and skip the `pip install .` step above. For example, on Ubuntu run:

    sudo apt install python3-pyside2.qtwidgets

On mac, you should be able to do the same with:

    brew install pyside2
