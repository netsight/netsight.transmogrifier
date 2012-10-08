from zope.interface import classProvides, implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import defaultMatcher
from xml.dom import minidom

from netsight.transmogrifier import BASE_DIR

try:
    from plone.app.linkintegrity.parser import extractLinks
except ImportError:
    pass # not supported in plone 2.5 (but we don't use it)

from Products.Archetypes import atapi
from Products.CMFCore.utils import getToolByName
from pickle import dumps, loads


def create_object(mtype, container, rename_after=False, **kwargs):
    """ creates an object of 'mtype' inside 'container' using portal factory """
    tempid = container.generateUniqueId(mtype)
    container.invokeFactory(mtype, tempid, **kwargs)
    ob = container[tempid]
    if rename_after:
        ob._renameAfterCreation()
    return ob

USER_PREFS = [
    'favFunctionalGroups',
    'favProjects',
    'favPages',
    'favLinks',
    ]

IMAGE_SIZE_MAPPING = {
    'small':'thumb',
    'medium':'standard',
    'large':'full-width',
}


# Our custom class to dump some extra info into a pickle
class ExtrasExporterSection(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.context = transmogrifier.context

        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.fileskey = options.get('files-key', '_files').strip()

    def __iter__(self):

        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]

            if not pathkey:
                yield item; continue

            path = item[pathkey]
            obj = self.context.unrestrictedTraverse(path, None)
            if obj is None:         # path doesn't exist
                yield item; continue

            extradata = {}

            if obj.meta_type == 'LargeDocument':
                # store next/prev setting and default page
                extradata['nextprev'] = True
                objectids = obj.objectIds()
                if objectids:
                    extradata['default_page'] = objectids[0]

            if obj.meta_type == 'CSRNomination':
                # store next/prev setting and default page
                extradata['ratings'] = obj.getRatings()

            # ROLES EXPORT
            # for groups/projects/usergroups
            if obj.meta_type in ['Project', 'FunctionalGroup', 'UserGroup', ]:
                # member times
                extradata['membertimes'] = getattr(obj, '_membertimes', {})

                # the roles
                portal_groups = getToolByName(obj, 'portal_groups')
                # members
                extradata['members'] = \
                    portal_groups.getGroupMembers(obj.getUserGroupId())
                # contributors
                extradata['contributors'] = obj.getContributors()
                # reviewers
                extradata['reviewers'] = obj.getReviewers()
                # admins
                extradata['administrators'] = obj.getAdministrators()
                # shared access groups
                extradata['sharedaccess'] = \
                    [ x for x in obj.getUserGroupIds() \
                          if x != obj.getUserGroupId() ]
            # for other types
            elif obj.meta_type not in ['Plone Site', ]:
                # all local roles
                try:
                    local_roles = obj.get_local_roles()
                except AttributeError:
                    local_roles = []
                if local_roles:
                    extradata['local_roles'] = dict(local_roles)
                    # skip 'admin' group roles on restricted folders
                    portal_workflow = getToolByName(obj, 'portal_workflow')
                    if portal_workflow.getInfoFor(obj, 'review_state', '') \
                            == 'restricted':
                        admin_groupid = obj.getAdminUserGroupId()
                        if admin_groupid in extradata['local_roles'].keys():
                            del(extradata['local_roles'][admin_groupid])

            # dump to pickle
            data = dumps(extradata)

            files = item.setdefault(self.fileskey, {})
            files # make pyflakes happy
            item[self.fileskey]['extras'] = {
                'name': '.extras.pickle',
                'data': data,
                }

            yield item


class ExtrasImporterSection(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.context = transmogrifier.context

        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.fileskey = defaultMatcher(options, 'files-key', name, 'files')

    def __iter__(self):

        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            fileskey = self.fileskey(*item.keys())[0]

            if not (pathkey and fileskey):
                yield item; continue
            if 'extras' not in item[fileskey]:
                yield item; continue

            path = item[pathkey]
            obj = self.context.unrestrictedTraverse(path, None)
            if obj is None:         # path doesn't exist
                yield item; continue

            data = item[fileskey]['extras']['data']
            extras = loads(data)
            reindex = False
            reindex_security = False

            # Fix up type screwups between our type switching
            # and the CMF marshaller
            if hasattr(obj, '_getPortalTypeName'):
                cmf_type = obj._getPortalTypeName()
                if cmf_type != obj.meta_type:
                    obj._setPortalTypeName(obj.meta_type)
                    reindex = True

            # ROLES import
            # for groups/projects/usergroups
            if obj.meta_type in ['Project', 'FunctionalGroup', 'UserGroup', ]:
                # member times
                if extras.get('membertimes'):
                    setattr(obj, '_membertimes', extras['membertimes'])

                # roles stuff
                acl_users = getToolByName(obj, 'acl_users')
                groupinfo = obj.getACLUsersGroupInfo()

                # members/admins
                if extras.get('members'):
                    acl_users.source_groups.manage_addPrincipalsToGroup(
                        group_id=groupinfo['Members']['gid'],
                        principal_ids=extras['members'],
                        )
                    reindex_security = True
                    reindex = True
                # admins
                if extras.get('administrators'):
                    acl_users.source_groups.manage_addPrincipalsToGroup(
                        group_id=groupinfo['Administrators']['gid'],
                        principal_ids=extras['administrators'],
                        )
                    reindex_security = True
                    reindex = True
                # contributors
                for userid in extras.get('contributors', []):
                    obj.manage_setLocalRoles(userid, ['Contributor', ])
                    reindex_security = True
                    reindex = True
                # reviewers
                for userid in extras.get('reviewers', []):
                    obj.manage_setLocalRoles(userid, ['Reviewer', ])
                    reindex_security = True
                    reindex = True
                # shared access groups
                for UID in extras.get('sharedaccess', []):
                    # translate old 'UID' group name to new 'UID-Members'
                    obj.manage_setLocalRoles('%s-Members' % UID, ['Member', ])
                    reindex_security = True
                    reindex = True

            # LOCAL ROLES
            for userid, roles in extras.get('local_roles', {}).items():
                obj.manage_setLocalRoles(userid, roles)
                reindex_security = True
                reindex = True

            # RESTRICTED FOLDERS
            if obj.meta_type != 'Plone Site':
                portal_workflow = getToolByName(obj, 'portal_workflow')
                if portal_workflow.getInfoFor(obj, 'review_state', '') \
                        == 'restricted':
                    if hasattr(obj, 'getACLUsersGroupInfo'):
                        agid = obj.getACLUsersGroupInfo()['Administrators']['gid']
                        obj.manage_setLocalRoles(agid, ['Manager', ])

            # Technical Portal field changes
            if obj.meta_type in ['TechnicalTicket',
                                 'TechnicalTicketResponse', ]:
                if 'marshall' in item[fileskey]:
                    manifest = item[fileskey]['marshall']['data']
                    for field, info in self.parseManifest(manifest).items():
                        if field == 'attachmentLink' and info['_alltext']:
                            newfield = obj.getField('link')
                            newfield.getMutator(obj)(info['_alltext'])
                            reindex = True

                mapping = {
                    'attachmentFile':'attachmentFile1',
                    'attachment1':'attachmentFile1',
                    'attachment2':'attachmentFile2',
                    'attachment3':'attachmentFile3',
                    }
                if 'file-fields' in item[fileskey]:
                    # remap attachment fields
                    manifest = item[fileskey]['file-fields']['data']
                    for field, info in self.parseManifest(manifest).items():
                        if field in mapping:
                            fname = info['filename']
                            ct = info['mimetype']
                            data = item[fileskey][fname]['data']
                            newfield = obj.getField(mapping[field])
                            newfield.getMutator(obj)(data, filename=fname,
                                                     mimetype=ct)
                            reindex = True

            # update geolocation fields to new format
            if obj.meta_type in ['BusinessUnit', 'MapMarker', ]:
                location = obj.getGeolocation()
                if isinstance(location, list):
                    location = ', '.join(location)
                    obj.setGeolocation(location)
                    reindex = True

            # update blog messages to 'html'
            if obj.meta_type == 'BlogMessage':
                message = obj.message
                if message.getContentType() == 'text/plain':
                    rawmessage = obj.getRawMessage()
                    if rawmessage.startswith('<'):
                        # looks like it is already html
                        message.setContentType(obj, 'text/html')
                    else:
                        portal_transforms = getToolByName(obj,
                                                          'portal_transforms')
                        data = portal_transforms.convertTo('text/html',
                                                           rawmessage,
                                                           mimetype='text/plain')
                        htmlmessage = data.getData()
                        obj.setMessage(htmlmessage, mimetype='text/html')
                    reindex = True

            # Set default page of previously-known-as 'LargeDocument'
            if extras.has_key('default_page'):
                obj.setDefaultPage(extras['default_page'])
                reindex = True

            # enable next previous nav
            if extras.has_key('nextprev'):
                obj.setNextPreviousEnabled(extras['nextprev'])
                reindex = True

            # Force pages to text/html
            if obj.meta_type in ['Page', 'NewsItem', 'HelpPage', ]:
                body = obj.body
                if body.getContentType() == 'text/plain':
                    body.setContentType(obj, 'text/html')

            # CSR nom ratings
            if obj.meta_type == 'CSRNomination':
                ratings = extras.get('ratings', {})
                obj.setRatings(ratings)

            # Video file remapping
            if obj.meta_type in ['Video' ] \
                    and 'file-fields' in item[fileskey]:
                manifest = item[fileskey]['file-fields']['data']
                mapping = {
                    'preview':'video',
                    'video':'original',
                    }
                for field, info in self.parseManifest(manifest).items():
                    if field in mapping:
                        fname = info['filename']
                        ct = info['mimetype']
                        data = item[fileskey][fname]['data']
                        newfield = obj.getField(mapping[field])
                        newfield.getMutator(obj)(data, filename=fname,
                                                 mimetype=ct)
                        reindex = True

            # Add Page image fields as content items
            if obj.meta_type in ['Page', 'BlogMessage', ] \
                    and 'file-fields' in item[fileskey]:
                portal_workflow = getToolByName(obj, 'portal_workflow')
                manifest = item[fileskey]['file-fields']['data']
                images = []
                if obj.meta_type == 'BlogMessage':
                    folder = obj.inBlog()
                    bodyfieldname = 'message'
                else:
                    folder = obj.aq_parent
                    bodyfieldname = 'body'

                for field, info in self.parseManifest(manifest).items():
                    if not field.startswith('image'):
                        continue
                    fname = info['filename']
                    ct = info['mimetype']
                    #if fname in item[fileskey]:
                    data = item[fileskey][fname]['data']
                    imageob = create_object('Image', folder,
                                            rename_after=True,
                                            title=fname,
                                            )
                    imageob.setImage(data, filename=fname, mimetype=ct)
                    if obj.meta_type != 'BlogMessage':
                        # blog images are auto-published
                        portal_workflow.doActionFor(imageob, 'make_visible')
                    imageob.setDatePublished(obj.created())
                    imageob.reindexObject('getDatePublished')
                    # mimic the published data of the original item
                    images.append([field, imageob])

                # replace old links in document with new ones
                body = obj.getField(bodyfieldname).getAccessor(obj)()
                if not isinstance(body, unicode):
                    body = unicode(body, 'utf-8', 'ignore')
                for fieldname, imageob in images:
                    body = body.replace(
                        '%s/%s' % (obj.getId(), fieldname),
                        'resolveuid/%s/image' % (imageob.UID()),
                        )
                    # replace sizes
                    for oldsize, newsize in IMAGE_SIZE_MAPPING.items():
                        body = body.replace(
                            'image_%s' % oldsize,
                            'image_%s' % newsize,
                            )

                # fix inpage image styles
                body = body.replace('inpage-image-right', 'image-right')
                body = body.replace('inpage-image-left', 'image-left')

                # fix table styles
                body = body.replace("<TABLE class=inline",
                                    "<table class='listing'")

                obj.getField(bodyfieldname).getMutator(obj)(body, mimetype='text/html')

            # Remove hard-coded links to old site
            OLD_DOMAIN = 'https://oldsitename'
            if hasattr(obj, 'Schema'):
                schema = obj.Schema()
                for fieldname in schema.keys():
                    field = schema[fieldname]
                    if not isinstance(field, atapi.TextField):
                        continue
                    value = field.getAccessor(obj)()
                    if not isinstance(value, unicode):
                        value = unicode(value, 'utf-8', 'ignore')
                    value_changed = False
                    links = extractLinks(value)
                    for link in links:
                        if link.startswith(OLD_DOMAIN):
                            newlink = link.replace(OLD_DOMAIN, '')
                            value = value.replace(link, newlink)
                            value_changed = True
                    if value_changed:
                        mimetype = field.getContentType(obj)
                        field.getMutator(obj)(value, mimetype=mimetype)

            if reindex_security:
                obj.reindexObjectSecurity(skip_self=True)
            if reindex:
                try:
                    obj.reindexObject()
                except:
                    ERRORS_FILENAME = '%s/reindex_errors.txt' % BASE_DIR
                    error = 'Could not reindex %s' % obj.absolute_url()
                    from datetime import datetime
                    open(ERRORS_FILENAME, 'a+').write('%s %s\n' % (datetime.now(), error))

            yield item

    def parseManifest(self, manifest):
        # pinched from quintagroup.transmogrifier.binary
        doc = minidom.parseString(manifest)
        fields = {}
        for elem in doc.getElementsByTagName('field'):
            field = fields.setdefault(str(elem.getAttribute('name')), {})
            field['_alltext'] = self.text_from_node(elem).strip()
            for child in elem.childNodes:
                if child.nodeType != child.ELEMENT_NODE:
                    continue
                if child.tagName == u'filename':
                    field['filename'] = child.firstChild.nodeValue.strip().encode('utf-8')
                elif child.tagName == u'mimetype':
                    field['mimetype'] = str(child.firstChild.nodeValue.strip())

        return fields

    def text_from_node(self, node):
        return " ".join(t.nodeValue for t in node.childNodes if t.nodeType == t.TEXT_NODE)
