from setuptools import setup, find_packages

setup(
    name='jerjerrod',
    description=('Tool to summarise the working state of VCS repo folders, or'
                 ' folders containing multiple VCS repos.'),
    url='https://github.com/phodge/jerjerrod/',
    author='Peter Hodge',
    license='MIT',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Utilities',
    ],
    keywords='tools utilities',
    packages=['jerjerrod'] + ['jerjerrod.{}'.format(p)
                              for p in find_packages('jerjerrod')],
    install_requires=['click', 'simplejson', 'GitPython', 'diskcache', 'xdg'],
    scripts=['bin/jerjerrod'],
    # automatic version number using setuptools_scm
    setup_requires=['setuptools_scm'],
    use_scm_version={
        "write_to": 'jerjerrod/__init__.py',
    },
)
