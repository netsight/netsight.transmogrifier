from Products.Five import BrowserView
from collective.transmogrifier.transmogrifier import configuration_registry
from collective.transmogrifier.interfaces import ITransmogrifier
import tempfile
import logging
import os
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName

from netsight.transmogrifier import BASE_DIR

logger = logging.getLogger('netsight.transmogrifier')

# used to keep a pointer to the temp file
CONFIGFILE = None


class Utils(BrowserView):

    import_template = ViewPageTemplateFile('import-options.pt')

    # mostly swiped from quintagroup.transmogrifier
    def registerDummyConfig(self, config, name):
        global CONFIGFILE
        # monkey in a config pipeline from a string
        if name in configuration_registry._config_ids:
            configuration_registry._config_ids.remove(name)
            del configuration_registry._config_info[name]

        # register new
        if config is not None:
            title = description = u'Persistent pipeline %s' % name
            tf = tempfile.NamedTemporaryFile('w+t', suffix='.cfg')
            tf.write(config)
            tf.seek(0)
            configuration_registry.registerConfiguration(name, title, description, tf.name)
            CONFIGFILE = tf
            return name
        else:
            return None

    def _allow_add(self, content_type, container_type):
        portal = self.context
        # manually update the allowed types of a container
        portal_types = getToolByName(portal, 'portal_types')
        container_info = portal_types[container_type]
        allowed_content_types = list(container_info.allowed_content_types)
        allowed_content_types.append(content_type)
        container_info.allowed_content_types = tuple(allowed_content_types)

    def run_pipeline(self, pipeline):
        portal = self.context
        transmogrifier = ITransmogrifier(portal)

        logger.info('Running transmogrifier pipeline %s' % pipeline)
        transmogrifier(pipeline)
        logger.info('Transmogrifier pipeline %s complete' % pipeline)

    def do_export(self, path=None):
        if not path:
            return 'Please provide a path (e.g. path=/plonesite/path/to/folder)'

        normpath = path.replace('/', '_')
        if normpath.startswith('_'):
            normpath = normpath[1:]

        temp_pipeline_id = 'export-netsight-%s' % normpath
        output_dir = BASE_DIR + temp_pipeline_id

        config = """
[transmogrifier]
include = export-netsight
pipeline += %(pipeid)s

[catalogsource]
path = query= %(path)s

[writer]
path = %(output_dir)s

[%(pipeid)s]
blueprint = quintagroup.transmogrifier.logger
keys =
    _type
    _path
        """.strip() % {
            'pipeid': temp_pipeline_id,
            'path': path,
            'output_dir': output_dir,
            }

        self.registerDummyConfig(config, temp_pipeline_id)
        self.run_pipeline(temp_pipeline_id)
        return 'Export of %s complete\nOutput dir: %s' % (path, output_dir)

    def do_import(self, source_id=None):
        if not source_id:
            return self.import_template()

        temp_pipeline_id = 'import-netsight-%s' % source_id
        source_dir = BASE_DIR + source_id

        config = """
[transmogrifier]
include = import-netsight
pipeline += %(pipeid)s

[reader]
path = %(source_dir)s

[%(pipeid)s]
blueprint = quintagroup.transmogrifier.logger
keys =
    _type
    _path
        """.strip() % {
            'pipeid': temp_pipeline_id,
            'source_dir': source_dir,
            }

        self.registerDummyConfig(config, temp_pipeline_id)
        self.run_pipeline(temp_pipeline_id)
        return 'Import of %s complete\nSource dir: %s' % (source_id, source_dir)

    def available_imports(self):
        filenames = os.listdir(BASE_DIR)
        return [x for x in filenames if x.startswith('export-')]
