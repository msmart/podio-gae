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

class Page(db.Model):
    title = db.StringProperty()
    slug = db.StringProperty()
    item_id = db.IntegerProperty()
    description = db.TextProperty()
    content = db.TextProperty()

class Menu(db.Model):
    title = db.StringProperty()
    slug = db.StringProperty()
    item_id = db.IntegerProperty()
    order = db.IntegerProperty()

class ContentHandler(webapp.RequestHandler):
  
  def get(self, path):
    menu = Menu.all().order("order")
    p =  Page.all().filter("slug =", path).get()
    if not p:
        page = template.render('templates/example.html',{'page':
                                                          {'title': 'Seite nicht gefunden',
                                                           'content':'Sorry, page was not found'},
                                                           'menu':menu})
        self.response.set_status(404)
 
    else:
        page = template.render('templates/example.html',{'page':p, 'menu':menu})
    self.response.out.write(page)

application = webapp.WSGIApplication([
                        ('(.*)$' , ContentHandler),
                        ], debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
    
