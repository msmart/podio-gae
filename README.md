podio-gae
=========
A webapp request handler for one way syncing from podio apps to a app engine models.

Proof of concept.

Installation
============
- Clone the git repository
- Create your app engine models (eg models.py and corresponding Podio apps (via the web)
- Map your models to a reference name in main.py (see MODEL_FACTORY)
- Enter your podio credentials and site configuration in main.py (get the urls right)
- Visit: /podiohook/ ie BASE_URL and add new syncs by mapping the reference name of models to app_ids of podio
- Map the podio fields and you are done
- Check with the Datastore viewer whether you can add content via podio


Remarks
=======
- This is pre-alpha
- Only strings and numbers are currently supported
- Your app engine models needs an IntegerProperty named "item_id"
- No security evaluation at all
- The newest httplib2 version is needed
- pypodio2 was slightly altered

Next steps
==========
- Add more field types, especially relational & binary stuff
- Clean up code & put handler in seperate module with all dependencies
- Think about licensing
- Create import all podio content method 



Log
===
Di  7 Jun 2011 08:43:48 CEST - 0-1

   
