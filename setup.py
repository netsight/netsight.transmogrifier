from setuptools import setup, find_packages
import os

version = '0.1'

setup(name='netsight.transmogrifier',
      version=version,
      description="",
      long_description=open("README.md").read() + "\n" +
                       open(os.path.join("docs", "HISTORY.txt")).read(),
      # Get more strings from
      # http://pypi.python.org/pypi?:action=list_classifiers
      classifiers=[
          "Programming Language :: Python",
        ],
      keywords='',
      author='',
      author_email='mattss@netsight.co.uk',
      url='https://github.com/netsight/netsight.transmogrifier',
      license='GPL',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['netsight'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          # -*- Extra requirements: -*-
          'collective.transmogrifier',
          'plone.app.transmogrifier',
          'quintagroup.transmogrifier',
      ],
      entry_points="""
      # -*- Entry points: -*-
      [z3c.autoinclude.plugin]
      target = plone
      """,
      )
