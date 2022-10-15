from setuptools import setup

setup(
    name='GitFourchette',
    version='0.1',
    package_dir={'': 'gitfourchette'},
    python_requires='>=3',
    install_requires=[
        'qtpy',
        'pygit2>=1.8.0',
        'psutil',
    ],
    tests_require=[
        'pytest',
        'pytest-qt',
    ],
)
