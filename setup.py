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
        'qtpy',
        'pygit2>=1.11.0',
    ],
    extras_require={
        'memory-indicator': ['psutil'],
    },
    tests_require=[
        'pytest',
        'pytest-qt',
    ],
)
