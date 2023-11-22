[app]
# title of your application
title = ZXLive
# project directory. the general assumption is that project_dir is the parent directory
# of input_file
project_dir = ./zxlive/
# source file path
input_file = __main__.py
# directory where exec is stored
exec_directory = ./build/
# path to .pyproject project file
project_file = 

[python]
# python path
python_path = python
# python packages to install
# ordered-set = increase compile time performance of nuitka packaging
# zstandard = provides final executable size optimization
packages = nuitka==1.8.*,ordered_set,zstandard
# buildozer = for deploying Android application
android_packages = buildozer==1.5.*,cython==0.29.*

[qt]
# comma separated path to qml files required
# normally all the qml files are added automatically
qml_files = 
# excluded qml plugin binaries
excluded_qml_plugins = 
# path to pyside wheel
wheel_pyside = 
# path to shiboken wheel
wheel_shiboken = 

[nuitka]
# (str) specify any extra nuitka arguments
# for arm macos add
extra_args = 
	--noinclude-qt-translations
	--nofollow-import-to=IPython
	--nofollow-import-to=scipy
	--nofollow-import-to=pytest
	--nofollow-import-to=matplotlib
	--nofollow-import-to=pandas
	--nofollow-import-to=sympy
	--nofollow-import-to=ipywidgets
	--nofollow-import-to=tkinter
	--deployment
	--disable-console
	--include-package-data=zxlive.icons

[buildozer]
# build mode
# possible options = [release, debug]
# release creates an aab, while debug creates an apk
mode = debug
# contrains path to pyside6 and shiboken6 recipe dir
recipe_dir = 
# path to extra qt android jars to be loaded by the application
jars_dir = 
# if empty uses default ndk path downloaded by buildozer
ndk_path = 
# if empty uses default sdk path downloaded by buildozer
sdk_path = 
# modules used. comma separated
modules = 
# other libraries to be loaded. comma separated.
local_libs = plugins_platforms_qtforandroid
# architecture of deployed platform
# possible values = ["aarch64", "armv7a", "i686", "x86_64"]
arch = 

