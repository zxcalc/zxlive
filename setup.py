# type: ignore
import setuptools

# read description from README.md
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


data_files = []

setuptools.setup(
    name="zxlive",
    version="0.1",
    author="Aleks Kissinger",
    author_email="aleks0@gmail.com",
    description="An interactive tool for the ZX calculus",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Quantomatic/zxlive",
    project_urls={
        "Bug Tracker": "https://github.com/Quantomatic/zxlive/issues",
    },
    license="Apache2",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    packages=["zxlive"],
    package_data={'': ['*.svg']},
    data_files=data_files,
    install_requires=["PySide2>=5.14", "pyzx>=0.7.3"],
    python_requires=">=3.7",
    entry_points={'console_scripts': 'zxlive=zxlive.app:main'},
)
