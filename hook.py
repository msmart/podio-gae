# -*- coding: utf-8 -*-
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import memcache
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import template
from google.appengine.ext.db import djangoforms
from google.appengine.api import memcache
import simplejson as json
import logging
import httplib2
import pypodio2
import yaml

# USER CREDENTIALS
CLIENT_ID = "your-id"
CLIENT_SECRET = "your-secret"
USERNAME = "your@login"
PASSWORD = "your-password"
DOMAIN = "http://your-app-id.appspot.com"
BASE_URL = "podiohook"

# MODEL MAPPING
from main import Page, Menu
MODEL_FACTORY = {'Page': Page, 'Menu':Menu }

# Add more mapping
PODIO_IMPORT = {
  'StringProperty': ['text','title'],
  'TextProperty': ['text' ],
  'IntegerProperty': ['number']}


class PodioSync(db.Model):
    name = db.StringProperty()
    app_id = db.IntegerProperty()
    create_hook = db.IntegerProperty()
    update_hook = db.IntegerProperty()
    delete_hook = db.IntegerProperty()
    status = db.StringProperty()
    mapping = db.TextProperty()

    def __str__(self):
      return self.name or 'No Name'

class PodioInterface(object):

  def config(self, *args, **kwargs):
    from pypodio2 import api
    self.client = api.OAuthClient( CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD )

  def init_hook(self, sync):
      """Init hook after a sync model entry was created."""
      setattr(sync, 'status', 'pending') 
      for hook_type in ['item.create','item.update','item.delete']:
        res = self.client.Hook.create('app', sync.app_id,\
                        {'url':'%s/%s/%s/%s' % (DOMAIN, BASE_URL, hook_type, sync.name), 'type':hook_type})
        hook_id = res.get('hook_id')
        self.client.Hook.verify(hook_id)
        setattr(sync, '%s_hook' % hook_type.split('.')[1], hook_id)
      sync.save()

  def delete_hooks(self, sync):
    for hook in ['create_hook', 'update_hook', 'delete_hook']:
      self.client.Hook.delete(getattr(sync, hook))

  def init_map_options(self, sync):
    """Detect what field types are available in the selected app."""
    app =  self.client.Application.find(sync.app_id) 
    fields = app.get('fields')
    map_options = {}
    [ map_options.update({ x.get('field_id'):
                         { 'external_id': x.get('external_id'),
                           'type':        x.get('type')}}) for x in fields ]
    return map_options

  def verify_hook(self, path):
    action, sync = path.split('/')
    sync = PodioSync.all().filter("name =", sync).get()
    hook_id = getattr(sync, "%s_hook" % action.split('.')[1])
    code = self.request.get('code')
    logging.info('sending code %s to hook %s' % (code, hook_id))
    self.client.Hook.validate(hook_id, code)
    setattr(sync, 'status', 'verified')
    sync.save()

  def update_item(self, path):
    """Update the app engine model."""
    action, model= path.split('/')
    item_id = int(self.request.get('item_id'))
    logging.debug('looking for item %s' % item_id)
    item = self.client.Item.find(item_id)			
    sync = PodioSync.all().filter("name =", model).get()
    mapping = yaml.load(sync.mapping)
    entry = MODEL_FACTORY.get(model).all().filter("item_id =",item_id).get()
                                                  
    if not entry:
      # Create new entry
      entry = MODEL_FACTORY.get(model)()
      setattr(entry,'item_id',item_id)

    logging.debug("Received %s" % item)
    fields = item.get('fields')
    for label, field_id in mapping.items():
      field_found = False
      for field in fields:
        if field_id == str(field.get('field_id')):
          # Implement conversions in sperate class TODO
          if field.get('type') == 'number':
            setattr(entry, label, int(float(field.get('values')[-1].get('value',''))))
          else:
            logging.debug("updating %s in field %s" % (label, field.get('field_id')))
            setattr(entry, label, field.get('values')[-1].get('value',''))
          field_found = True
        if not field_found: 
          # Field value might be None, implement reset TODO
          setattr(entry, label, None)
          
    entry.save()

  def delete_item(self, path):
    action, model= path.split('/')
    item_id = int(self.request.get('item_id'))
    entry = MODEL_FACTORY.get(model).all().filter("item_id =",item_id).get()
    entry.delete()

class PodioHookHandler(webapp.RequestHandler, PodioInterface):
  
  def get(self, path):
    """Display the forms for interaction with the user."""
    self.config()
    if not path:
      self.response.out.write(template.render('templates/base.html',\
                                              {'syncs':PodioSync.all(),
                                               'msg':self.request.get('msg',''),
                                               'BASE_URL':BASE_URL}))
      return
    action, sync = path.split('/')
    getattr(self,action,logging.error)(sync)

  def post(self, path):
    """ Should handle:
      1. Create a sync configuration: %s/create_sync/
      2. Create/udpate a mapping configuration: %/update_mapping/MODEL
      3. Receives the webhooks from podio
    """
    self.config()
    logging.info("receiving post hook info %s" % self.request)
    typ = self.request.get('type')
    run = { 'hook.verify': self.verify_hook, 'item.create':self.update_item, \
            'item.update':self.update_item,'item.delete':self.delete_item }
    if typ in run:
      run[typ](path)
    elif "update_mapping" in path:
      action, model = path.split('/')
      self.update_mapping(model)
    else:
      logging.error('received unknown hook type')
 
  def sync_mapping(self, sync):
    """Interacts with the user to determine the field mapping."""
    sync = PodioSync.all().filter("name =", sync).get()
    model = MODEL_FACTORY.get(sync.name)
    model_props = model().properties()
    model_fields = []
    map_options = self.init_map_options(sync)
    logging.debug("found %s map options" % map_options)
    for field in model_props:
      # Ugly hack TODO
      prop_class = str(model_props.get(field).__class__).split('.')[-1].split("'")[0]
      logging.debug("found class %s" % prop_class)
      allowed_types = PODIO_IMPORT.get(prop_class,'')
      opt = []
      try:
        current_mapping = yaml.load(sync.mapping)
        if not current_mapping:
          current_mapping = {} 
      except:
        current_mapping = {'ERROR':'ERROR'}
      for id, info in map_options.items():
        if info.get('type', '') in allowed_types and field != "item_id":
          opt_value = {'value':id, 'label':info.get('external_id') }
          if current_mapping.get(field,'') == str(id):
            opt_value.update({'selected': True })
          opt.append(opt_value) 
      if opt:
        model_fields.append({'name':field, 'options':opt })
    self.response.out.write(template.render('templates/map.html',
                                              {'sync':sync, 
                                               'current_mapping':current_mapping,
                                               'BASE_URL': BASE_URL,
                                               'model_fields': model_fields }))
  def update_mapping(self, sync):
    """Handles the post from the sync mapping form."""
    sync = PodioSync.all().filter("name =", sync).get()
    model = MODEL_FACTORY.get(sync.name)
    mapping = {}
    for x in model().properties().keys():
      if self.request.get(x):
        mapping.update({x:self.request.get(x)})
    sync.mapping = yaml.dump(mapping)
    sync.save()
    self.redirect("/%s/" % BASE_URL)
    
  def create_sync(self, sync):
    """Creates the sync configuration that links an app engine model with a podio app."""
    sync = PodioSync.all().filter("name =", sync).get()
    
    if self.request.get('delete'):
      try:
        self.delete_hooks(sync)
      except:
        pass
      sync.delete()

    elif not sync and self.request.get('app_id'):
      # Create new sync
      test = PodioSync.all().filter('name =', self.request.get('name')).get()
      if test:
        self.redirect('/%s/?msg=Error: sync exists' % BASE_URL)
        return 
      sync = PodioSync(name=self.request.get('name'), mapping=self.request.get('mapping'), \
                       app_id=int(self.request.get('app_id')))
      sync.save()
      self.init_hook(sync)
      self.redirect('/%s/sync_mapping/%s' % (BASE_URL, sync.name ))
    else:
      return self.response.out.write(template.render('templates/model.html',
                                             {'sync':sync, 
                                              'BASE_URL': BASE_URL,
                                              'modelfactory':MODEL_FACTORY}))
    self.redirect('/%s/' % BASE_URL)

application = webapp.WSGIApplication([
                        ('/%s/(.*)$' % BASE_URL, PodioHookHandler),
                        ], debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
    
