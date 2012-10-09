BASE_DIR = '/home/zope/transmogrifer_export/'

# patches
import logging
logger = logging.getLogger('netsight.transmogrifier:patches')

# make sure we unicode all filenames
from quintagroup.transmogrifier.binary import FileExporterSection
old_extractFile = FileExporterSection.extractFile


def extractFile(self, obj, field):
    raw = obj.getField(field).getRaw(obj)
    field = obj.getField(field)
    fname = field.getFilename(obj)
    ct = field.getContentType(obj)
    value = str(raw)

    return fname, ct, value

from quintagroup.transmogrifier.binary import FileExporterSection
FileExporterSection.extractFile = extractFile
logger.info('Make sure quintagroup.transmogrifier uses unicode for filenames')

# let's pretend all file fields with text in are binary
from Products.Archetypes.utils import shasattr


def isBinary(self, key):
    """Return wether a field contains binary data.
    """
    field = self.getField(key)
    # pretend that all file fields are binary
    # so that they are migrated separately
    if field and field.widget.getName() == 'FileWidget':
        return 1

    element = getattr(self, key, None)
    if element and shasattr(element, 'isBinary'):
        try:
            return element.isBinary()
        except TypeError:
            pass

    mimetype = self.getContentType(key)
    if mimetype and shasattr(mimetype, 'binary'):
        return mimetype.binary
    elif mimetype and mimetype.find('text') >= 0:
        return 0
    return 1

from Products.Archetypes.BaseObject import BaseObject
BaseObject.isBinary = isBinary
logger.info('Patching Products.Archetypes.BaseObject.isBinary so that all file fields are written to disk')


# Catch and log issues with references at the end
from Products.CMFCore.utils import getToolByName
from Products.Archetypes import config as atcfg
from quintagroup.transmogrifier.adapters.importing import EXISTING_UIDS, REFERENCE_QUEUE
ERRORS_FILENAME = '%s/issues.log' % BASE_DIR
from datetime import datetime


def patched_iter(self):
    for item in self.previous:
        yield item
    # finalization of importing references
    rc = getToolByName(self.context, atcfg.REFERENCE_CATALOG)
    uc = getToolByName(self.context, atcfg.UID_CATALOG)
    uids = uc.uniqueValuesFor('UID')
    existing = set(uids)
    for suid, rel_fields in REFERENCE_QUEUE.items():
        instance = rc.lookupObject(suid)
        if instance is None:
            error = 'Could not find ob to set references for for %s %s' % (suid, rel_fields)
            print error
            open(ERRORS_FILENAME, 'a+').write('%s %s\n' % (datetime.now(), error))
            continue

        for fname, tuids in rel_fields.items():
            # now we update reference field only if all target UIDs are valid
            # but may be it is better to update with as much as possible valid
            # target UIDs (do existing.intersection(set(tuids)))
            if set(tuids).issubset(existing):
                mutator = instance.Schema()[fname].getMutator(instance)
                mutator(tuids)
            else:
                error = 'Could not find all references for %s [%s] (%s)' % ('/'.join(instance.getPhysicalPath()), fname, tuids)
                print error
                open(ERRORS_FILENAME, 'a+').write('%s %s\n' % (datetime.now(), error))
    EXISTING_UIDS.clear()
    REFERENCE_QUEUE.clear()

from quintagroup.transmogrifier.references import ReferencesImporterSection
ReferencesImporterSection.__iter__ = patched_iter
logger.info('Patching quintagroup.transmogrifier.references to log and write reference issues')

# Patch references import with unicode support
from quintagroup.transmogrifier.adapters.importing import ReferenceImporter
old_importReferences = ReferenceImporter.importReferences

def importReferences(self, data):
    if not isinstance(data, unicode):
        data = unicode(data, 'utf-8', 'ignore')
    data = data.encode('utf-8')
    return old_importReferences(self, data)

ReferenceImporter.importReferences = importReferences
logger.info('Patching quintagroup.transmogrifier.adapters.importing.ReferenceImporter to support dodgy characters')

from Products.Archetypes.ExtensibleMetadata import ExtensibleMetadata
def notifyModified(self):
    pass
ExtensibleMetadata.notifyModified = notifyModified
logger.info('Patching Archetypes.ExtensibleMetadata to avoid updating modified')
