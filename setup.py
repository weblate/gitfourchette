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
    python_requires='>=3',
    install_requires=[
        'pygit2>=1.11.0',
        'PySide6>=6.4.1',
        'PySide6 !=6.4.0, !=6.4.0.1, !=6.5.1',
    ],
    extras_require={
        'pyqt6': ['qtpy', 'pyqt6'],
        'pyqt5': ['qtpy', 'pyqt5'],
        'pyside2': ['qtpy', 'PySide2'],
        'memory-indicator': ['psutil'],
    },
    tests_require=[
        'pytest',
        'pytest-qt',
        'qtpy',
    ],
)
