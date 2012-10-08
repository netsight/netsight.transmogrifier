from zope.interface import classProvides, implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import defaultMatcher

from quintagroup.transmogrifier.marshall import MarshallerSection
from quintagroup.transmogrifier.manifest import ManifestExporterSection

from Products.Archetypes.interfaces import IBaseObject

from ZODB.POSException import ConflictError
import unicodedata

class DataCorrectorSection(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.context = transmogrifier.context

        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.fileskey = defaultMatcher(options, 'files-key', name, 'files')
        self.typekey = defaultMatcher(options, 'type-key', name, 'type',
                                      ('portal_type', 'Type'))

    def __iter__(self):

        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            fileskey = self.fileskey(*item.keys())[0]
            typekey = self.typekey(*item.keys())[0]

            if not pathkey:
                yield item; continue

            if fileskey:
                # decode file names properly from OSX
                for fname, info in item[fileskey].items():
                    newfname = unicodedata.normalize(
                        'NFC', unicode(fname, 'utf-8')).encode('utf-8')
                    if newfname != fname:
                        item[fileskey][newfname] = info
                        del(item[fileskey][fname])

            # Remap content types
            REMAPPINGS = {
                'LargeDocument' : 'ContentFolder',
                'ForumsFolder' : 'ContentFolder',
                }
            if typekey:
                # Unfortunately these type switches are borked later on
                # by the CMF demarshaller, which we fix in the 'extras' step
                type_ = item[typekey]
                if type_ in REMAPPINGS.keys():
                    item[typekey] = REMAPPINGS.get(type_)

            yield item

# Our custom manifest exporter to retain folder ordering
# from a catalog source
class OrderedManifestExporterSection(ManifestExporterSection):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        ManifestExporterSection.__init__(self, transmogrifier, name, options, previous)
        # add in pathkey lookup
        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')


    def __iter__(self):
        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            entrieskey = self.entrieskey(*item.keys())[0]
            if not entrieskey:
                yield item; continue

            path = item[pathkey]
            obj = self.context.unrestrictedTraverse(str(path), None)
            if obj is None:         # path doesn't exist
                yield item; continue

            items = list(item[entrieskey])

            # No idea why we get some of these
            if obj.meta_type == 'Plone Factory Tool':
                yield item; continue

            # reordering by objectids
            objids = list(obj.objectIds())
            items.sort(key=lambda x: objids.index(x[0]))

            items = tuple(items)
            manifest = self.createManifest(items)

            if manifest:
                files = item.setdefault('_files', {})
                files # keep pyflakes happy
                item[self.fileskey]['manifest'] = {
                    'name': '.objects.xml',
                    'data': manifest,
                }

            yield item

# Our custom marshaller to control fields on a per-type basis
class MarshallerSection(MarshallerSection):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __iter__(self):
        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]

            if not pathkey:
                yield item; continue

            path = item[pathkey]
            obj = self.context.unrestrictedTraverse(str(path), None)
            if obj is None:         # path doesn't exist
                yield item; continue

            if IBaseObject.providedBy(obj):
                # get list of excluded fields given in options and in item
                excludekey = self.excludekey(*item.keys())[0]
                atns_exclude = tuple(self.exclude)
                if excludekey:
                    atns_exclude = tuple(set(item[excludekey]) | set(atns_exclude))

                try:
                    content_type, length, data = self.atxml.marshall(obj, atns_exclude=atns_exclude)
                except ConflictError:
                    raise
                except Exception:
                    data = None

                if data or data is None:
                    # None value has special meaning for
                    # IExportDataCorrector adapter for topic criterias
                    item.setdefault(self.fileskey, {})
                    item[self.fileskey]['marshall'] = {
                        'name': '.marshall.xml',
                        'data': data,
                    }

            yield item




