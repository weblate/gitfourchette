from setuptools import setup

setup(
    name='GitFourchette',
    version='0.1',
    package_dir={'': 'gitfourchette'},
    python_requires='>=3',
    install_requires=[
        'PySide2>=5',
        'pygit2>=1.7.0',
        'psutil',
    ],
    tests_require=[
        'pytest',
        'pytest-qt',
    ],
)
