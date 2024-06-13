# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'zxlive'
copyright = '2024, ZXLive team'
author = 'ZXLive team'
release = '0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
              'sphinx.ext.autodoc',
              'sphinx.ext.mathjax',
              'sphinx.ext.napoleon',
              'sphinx_rtd_theme',
              'sphinx_autodoc_typehints',
              'sphinxcontrib.rsvgconverter',
              'myst_parser'
]

myst_enable_extensions = ["colon_fence"]

add_function_parentheses = False
set_type_checking_flag = True
napoleon_use_rtype = False

add_module_names = False

source_suffix = ['.rst', '.md']

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

pygments_style = 'sphinx'


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

htmlhelp_basename = 'zxlivedoc'