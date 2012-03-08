#!/usr/bin/env python
import logging
#!/usr/bin/env python
# Copyright 2012 Brooklyn Code Incorporated. See LICENSE.md for usage
# the license can also be found at http://brooklyncode.com/LICENSE.md
import os
from time import time
import json
import magic
import md5
from brubeck.auth import authenticated
from brubeck.request_handling import WebMessageHandler, JSONMessageHandler

##
## This should be in Brubeck soon
##
def lazyprop(method):
    """ A nifty wrapper to only load preoperties when accessed
    uses the lazyProperty pattern from: 
    http://j2labs.tumblr.com/post/17669120847/lazy-properties-a-nifty-decorator
    inspired by  a stack overflow question:
    http://stackoverflow.com/questions/3012421/python-lazy-property-decorator
    This is to replace initializing common variable from cookies, query string, etc .. 
    that would be in the prepare() method.
    THIS SHOULD BE IN BRUBECK CORE
    """
    attr_name = '_' + method.__name__
    @property
    def _lazyprop(self):
        if not hasattr(self, attr_name):
            attr = method(self)
            setattr(self, attr_name, method(self))
            # filter out our javascript nulls
            if getattr(self, attr_name) == 'undefined':
                setattr(self, attr_name, None)
        return getattr(self, attr_name)
    return _lazyprop    


##
## Our file upload handler class definitions
##

class TemporaryImageViewHandler(WebMessageHandler):
    """this is built to be compatible with fileuploader.js"""

    @lazyprop
    def settings(self):
        """get our settings
        """
        return self.application.get_settings('uploader')


    def get(self, file_name):
        """serve our temporary files"""
        logging.debug("TemporaryImageViewHandler get")
        try:

            requested_file_name = self.application.project_dir + '/' + self.settings['TEMP_UPLOAD_DIR'] + '/' + file_name

            fp = open(requested_file_name)
            file_contents =  fp.read()
        
            # get our mime-type
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(requested_file_name)

            logging.debug("filename: %s" % file_name)
            logging.debug("hash: %s" % hash)
            logging.debug("requested_file_name: %s" % requested_file_name)
            logging.debug("mime_type: %s" % mime_type)

            self.set_status(200)
            self.set_body(file_contents)
            self.headers['Content-Type'] = mime_type
            self.headers['Content-Length'] = len(file_contents)

        except Exception as e:
            raise
            logging.debug(e.message)
            self.set_status(404)

        return self.render()

class TemporaryImageUploadHandler(JSONMessageHandler):
    """this is built to be compatible with fileuploader.js"""

    def prepare(self):
        logging.debug(os.getenv('HTTP_REFERER'))
        logging.debug(self.message.headers)
        self.headers['Access-Control-Allow-Origin'] = '*'
        self.headers['Access-Control-Allow-Credentials'] = 'true'
        self.headers['Access-Control-Allow-Headers'] = 'Referer, User-Agent, Origin, X-Requested-With, X-File-Name, Content-Type'
        self.headers['Access-Control-Max-Age'] = '1728000'
        self.headers['Content-Type'] = 'text/plain; charset=UTF-8'


    @lazyprop
    def settings(self):
        """get our settings
        """
        return self.application.get_settings('uploader')

    def options(self):
        """just return OK"""
        logging.debug("TemporaryImageUploadHandler options")
        self.set_status(200)
        return self.render()

    def post(self):
        """upload a temporary files"""
        logging.debug("TemporaryImageUploadHandler post")
        try:
            qqfile = self.get_argument('qqfile', None)
            file_contents = self.message.body
            logging.debug(self.settings)
            if len(file_contents) > 0:
                fn = qqfile
                hash = str(md5.new(fn + str(time())).hexdigest())
                download_file_name = self.application.project_dir + '/' + self.settings['TEMP_UPLOAD_DIR'] + '/' + hash

                fd = os.open(download_file_name, os.O_RDWR|os.O_CREAT)
                os.write(fd, file_contents)
    
                # get our mime-type
                mime = magic.Magic(mime=True)
                mime_type = mime.from_file(download_file_name)

                logging.debug("filename: %s" % fn)
                logging.debug("hash: %s" % hash)
                logging.debug("download_file_name: %s" % download_file_name)
                logging.debug("mime_type: %s" % mime_type)

                if not mime_type in self.settings['ACCEPTABLE_UPLOAD_MIME_TYPES']:
                    raise Exception("unacceptable mime type: %s" % mime_type)
                    os.remove(download_file_name)
                message = 'The file "' + fn + '" was uploaded successfully'
                self.add_to_payload('success', True)
                self.add_to_payload('message', message)
                self.add_to_payload('hash', hash)
                self.set_status(200)
    
            else:
                raise Exception('No file was uploaded')

        except Exception as e:
            raise
            logging.debug(e.message)
            self.set_status(500)
            self.add_to_payload('error', e.message)

        return self.render()
