from setuptools import setup

setup(
    name='gitfourchette',
    version='0.1',
    description='The comfy Git UI',
    author='Iliyas Jorio',
    url='https://github.com/jorio/gitfourchette',
    classifiers=[
        'Topic :: Software Development :: Version Control :: Git',
        'Environment :: X11 Applications :: Qt',
        'Intended Audience :: Developers',
    ],
    package_dir={
        'gitfourchette': 'gitfourchette'
    },
    package_data={
        'gitfourchette.assets': ['*']
    },
    entry_points={
        'console_scripts': ['gitfourchette=gitfourchette.__main__:main']
    },
    python_requires='>= 3.10',
    install_requires=[
        'pygit2 >= 1.12',
        'pyqt6',
    ],
    extras_require={
        'pyqt5': ['pyqt5'],
        'pyside6': ['PySide6 !=6.4.0, !=6.4.0.1, !=6.5.1'],
        'pyside2': ['PySide2'],
        'qtpy': ['qtpy'],  # compatibility layer for older versions of Qt bindings
        'memory-indicator': ['psutil'],
    },
    tests_require=[
        'pytest',
        'pytest-qt',
    ],
)
