from setuptools import setup

setup(
    name='GitFourchette',
    version='0.1',
    package_dir={'': 'gitfourchette'},
    python_requires='>=3',
    install_requires=[
        'PySide6>=6',
        'GitPython>=3',
        'psutil'
    ],
)
