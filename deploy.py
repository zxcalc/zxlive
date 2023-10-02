import sys
from cx_Freeze import setup, Executable

# base="Win32GUI" should be used only for Windows GUI app
base = "Win32GUI" if sys.platform == "win32" else None

setup(executables=[Executable("zxlive/__main__.py", base=base, target_name="zxlive")])
