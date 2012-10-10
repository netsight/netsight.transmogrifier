netsight.transmogrifier
=======================

Tools and Extensions for collective.transmogrifier

This is a work-in-progress egg that provides some example code and utilities for using collective.transmogrifier in large-scale plone sites. Comments, questions, suggestions and forks welcome.

Installation
------------

No releases yet - so you may want to set up [mr.developer](http://pypi.python.org/pypi/mr.developer) to integrate this into your buildout.

    [buildout]
    ...
    eggs = netsight.transmogrifier

    [sources]
    netsight.transmogrifier = git git://github.com/netsight/netsight.transmogrifier.git


Using it
--------

This egg is designed to run on both the source plone site and the target plone site.

The egg register two browser views - one for exporting (from the source site) and one for importing (into the target site).

    http://localhost:8001/plonesite/@@netsight_do_export?path=/path/to/content

This export view will use the catalog to find content at /path/to/content and run it through the export pipeline. Content is exported to XML in /home/zope/transmogrifer_export/

    http://localhost:8001/plonesite/@@netsight_do_import

This view will list the available exports from /home/zope/transmogrifier_export and allow you to select one of them to run through the import pipeline.
