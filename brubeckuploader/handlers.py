#!/usr/bin/env python
# Copyright 2012 Brooklyn Code Incorporated. See LICENSE.md for usage
# the license can also be found at http://brooklyncode.com/LICENSE.md
import json
import logging
import magic
import md5
import os
import re
import urllib2
from BeautifulSoup import BeautifulSoup
from brubeck.auth import authenticated
from brubeck.request_handling import (
    MessageHandler,
    WebMessageHandler,
    JSONMessageHandler,
)
from brubeckservice.base import ServiceMessageHandler
from brubeckuploader.base import Uploader
from math import log
from PIL import Image as PILImage
from time import time
from urlparse import urlparse

# list of content-type we support
_IMAGE_CONTENT_TYPES = [
        'image/jpeg',
        'image/gif',
        'image/png',
    ]

## This should be in Brubeck soon
##
def lazyprop(method):
    """ A nifty wrapper to only load properties when accessed
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

class BrubeckUploaderBaseHandler(MessageHandler):
    """Intended to provide some common functionality for handlers"""
    @lazyprop
    def settings(self):
        """get our settings
        """
        try:
            return self.application.get_settings('uploader')
        except:
            pass
        return None

    @lazyprop
    def uploader(self):
        return Uploader(self.settings)

    @lazyprop
    def echo_parameters(self):
        """ a list of query string parameters to echo back in the response """
        echo_parameters = self.message.get_argument('echo_parameters', '')
        echo_parameters =  echo_parameters.split(',')
        logging.debug(echo_parameters)
        return echo_parameters

    def human_readable_file_size(self, num):
        """Human friendly file size"""
        unit_list = zip(['bytes', 'kB', 'MB', 'GB', 'TB', 'PB'], [0, 0, 1, 2, 2, 2])
        if num > 1:
            exponent = min(int(log(num, 1024)), len(unit_list) - 1)
            quotient = float(num) / 1024**exponent
            unit, num_decimals = unit_list[exponent]
            format_string = '{:.%sf} {}' % (num_decimals)
            return format_string.format(quotient, unit)
        if num == 0:
            return '0 bytes'
        if num == 1:
            return '1 byte'

    def prepare(self):
        logging.debug(os.getenv('HTTP_REFERER'))
        logging.debug(self.message.headers)
        self.headers['Access-Control-Allow-Origin'] = '*'
        self.headers['Access-Control-Allow-Credentials'] = 'true'
        self.headers['Access-Control-Allow-Headers'] = 'Referer, User-Agent, Origin, X-Requested-With, X-File-Name, Content-Type'
        self.headers['Access-Control-Max-Age'] = '1728000'
        self.headers['Content-Type'] = 'text/plain; charset=UTF-8'

    def options(self):
        """just return OK"""
        logging.debug("TemporaryImageUploadHandler options")
        self.set_status(200)
        return self.render()

    def saveFile(self, file_name, is_url=False, hash=None, file_content=None):
        """Save an uploaded file or downloads a file from a url and places it in the TMP directory"""
        if is_url:
            hash = self.uploader.download_image_from_url(file_name, hash)
        else:
            if hash is None:
                hash = str(md5.new(file_name + str(time())).hexdigest())

        download_file_name = self.application.project_dir + '/' + self.settings['TEMP_UPLOAD_DIR'] + '/' + hash
        fd = os.open(download_file_name, os.O_RDWR|os.O_CREAT)

        if file_content is None:
            file_content = self.message.body
        if is_url is False:
            os.write(fd, file_content)

        # get our mime-type
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(download_file_name)

        logging.debug("filename: %s" % file_name)
        logging.debug("hash: %s" % hash)
        logging.debug("download_file_name: %s" % download_file_name)
        logging.debug("mime_type: %s" % mime_type)

        logging.debug("checking mime_type: %s" % mime_type)
        if not mime_type in self.settings['ACCEPTABLE_UPLOAD_MIME_TYPES']:
            raise Exception("unacceptable mime type: %s" % mime_type)
            os.remove(download_file_name)
        logging.debug("mime_type OK")

        width, height = PILImage.open(open(download_file_name)).size
        logging.debug("width: %s" % width)
        logging.debug("height: %s" % height)

        message = 'The file "' + file_name + '" was uploaded successfully'

        file_size = os.fstat(fd).st_size
        human_readable_file_size = self.human_readable_file_size(file_size)

        # spit back our parameters sent with the file
        for param_name in self.echo_parameters:
            self.add_to_payload(param_name, self.message.get_argument(param_name, ''))

        self.add_to_payload('success', True)
        self.add_to_payload('message', message)
        self.add_to_payload('filename', file_name)
        self.add_to_payload('file_size', file_size)
        self.add_to_payload('human_readable_file_size', human_readable_file_size)
        self.add_to_payload('hash', hash)
        self.add_to_payload('mime_type', mime_type)
        self.add_to_payload('width', width)
        self.add_to_payload('height', height)
        self.set_status(200)


class TemporaryImageViewHandler(WebMessageHandler, BrubeckUploaderBaseHandler):
    """this is built to be compatible with fileuploader.js"""

    def get(self, file_name):
        """serve our temporary files"""
        logging.debug("TemporaryImageViewHandler get")
        try:

            requested_file_name = self.application.project_dir + '/' + self.settings['TEMP_UPLOAD_DIR'] + '/' + file_name

            fp = open(requested_file_name)
            file_content =  fp.read()

            # get our mime-type
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(requested_file_name)

            logging.debug("filename: %s" % file_name)
            logging.debug("hash: %s" % hash)
            logging.debug("requested_file_name: %s" % requested_file_name)
            logging.debug("mime_type: %s" % mime_type)

            self.set_status(200)
            self.set_body(file_content)
            self.headers['Content-Type'] = mime_type
            self.headers['Content-Length'] = len(file_content)

        except Exception as e:
            logging.debug(e.message)
            self.set_status(404)

        return self.render()


class TemporaryImageUploadHandler(JSONMessageHandler, BrubeckUploaderBaseHandler):
    """this is built to be compatible with fileuploader.js"""

    def post(self):
        """upload a temporary files"""
        logging.debug("TemporaryImageUploadHandler post")
        try:
            qqfile = self.message.get_argument('qqfile', None)

            file_content = self.message.body
            logging.debug(self.settings)
            if len(file_content) > 0:
                fn = qqfile
                self.saveFile(fn, is_url=False)

            else:
                raise Exception('No file was uploaded')

        except Exception as e:
            raise
            logging.debug(e.message)
            self.set_status(500)
            self.add_to_payload('error', e.message)

        return self.render()


class TemporaryImageFromURLUploadHandler(JSONMessageHandler, BrubeckUploaderBaseHandler):
    """downloads an image give a URL and saves it to the temp directory
    this is built to be compatible with fileuploader.js"""

    @lazyprop
    def fetch_image_url(self):
        fetch_image_url = self.message.get_argument('fetch_image_url', None)
        return fetch_image_url

    def post(self):
        """upload a temporary files"""
        logging.debug("TemporaryImageUploadHandler post")
        try:
            if self.fetch_image_url is not None and len(self.fetch_image_url) > 0:
                self.saveFile(self.fetch_image_url, is_url=True)
            else:
                raise Exception('No fetch_image_url parameter found.')

        except Exception as e:
            raise
            logging.debug(e.message)
            self.set_status(500)
            self.add_to_payload('error', e.message)

        return self.render()


class ImageURLFetcherHandler(JSONMessageHandler, BrubeckUploaderBaseHandler):
    """get a list of image urls for a given url"""

    @lazyprop
    def fetch_image_urls(self):
        fetch_from_url = self.get_arguments('fetch_image_url', [])
        return fetch_from_url

    def get(self):
        """fetch image URL from given pages"""
        logging.debug("ImageURLFetcherHandler get")
        try:
            image_urls = []
            for fetch_image_url in self.fetch_image_urls:
                try:
                    response = urllib2.urlopen(fetch_image_url)

                    content_type = response.info()['content-type']
                    if content_type in _IMAGE_CONTENT_TYPES:
                        image_urls.append(fetch_image_url)
                    else:
                        the_page = response.read()
                        pool = BeautifulSoup(the_page)
                        image_urls += (self.get_url_images(pool, fetch_image_url))

                except Exception as e:
                        logging.debug('Unable to fetch images for %s' % fetch_image_url);
                        raise

            logging.debug('image_urls: %s' % image_urls);
            self.add_to_payload('image_urls', image_urls)

        except Exception as e:
            logging.debug(e.message)
            self.set_status(500)
            raise

        self.set_status(200)
        return self.render()

    def get_url_images(self, pool, fetch_image_url):
        """get images urls from a BeatifulSoup 'pool'"""
        image_urls = []
        logging.debug('get_url_images %s' % fetch_image_url);
        tags = pool.findAll('meta',
                    attr={ 'property': re.compile('(?i)og:image')
                }
            )
        def _get_tag_attr(tag, attr):
            """used to get an attribute and avoid errors"""
            try:
                return tag[attr]
            except:
                pass
            return None

        # get all our images in meta data
        if tags is not None and len(tags) > 0:
            for tag in tags:
                logging.debug('og:image tag: %s' % tag)
                try:
                    url = self.screen_and_fix_url(
                            _get_tag_attr(tag, 'content'),
                            base_url
                        )
                    if url is not None:
                        image_urls.append(url)
                except:
                    pass
        else:
            tags = pool.findAll('link', attr={
                    'rel': re.compile('(?i)img_src')
                }
            )
            if tags is not None and len(tags) > 0:
                for tag in tags:
                    logging.debug('img_src tag: %s' % tag)
                    url = self.screen_and_fix_url(
                            _get_tag_attr(tag, 'img_src'),
                            fetch_image_url
                        )
                    if url is not None:
                        image_urls.append(url)

        # Get all our images in content
        tags = pool.findAll('img')
        if tags is not None and len(tags) > 0:
            for tag in tags:
                logging.debug('img tag: %s' % tag)
                url = self.screen_and_fix_url(
                        _get_tag_attr(tag, 'src'),
                        fetch_image_url
                    )
                image_urls.append(url)

        return image_urls

    def get_base_url(self, page_url):
        """get the base url from a url"""
        parsed_url = urlparse(page_url)
        return "%s://%s" % (parsed_url[0], parsed_url[1])

    def get_base_path(self, page_url):
        """get the base url from a url"""
        parsed_url = urlparse(page_url)
        return "%s://%s" % (parsed_url[0], parsed_url[1])

    def screen_and_fix_url(self, url, fetch_image_url):
        logging.debug("screen_and_fix_url('%s', '%s')" % (url, fetch_image_url))
        # first screen it
        if url is None or self.screen_url(url) == False:
            return None
        # and if needed fix it
        return self.fix_url(url, fetch_image_url)

    def screen_url(self, url):
        """we don't want things like ads"""
        if url == None or url.find("/ad/") > -1:
            return False;
        return True

    def fix_url(self, url, fetch_image_url):
        """Give a url an absolute path if it does not have one"""
        logging.debug("fix_url('%s', '%s')" % (url, fetch_image_url))
        base_url = self.get_base_url(fetch_image_url)
        base_path = self.get_base_path(fetch_image_url)
        if url[0:4] == 'http':
            return url
        if url[0:2] == '//':
            url = "%s:%s" % (urlparse(base_url)[0], url)
        elif url[0:1] == '/':
            url = "%s%s" % (base_url, url)
        else:
            url = "%s/%s" % (base_url, url)
        return url

    def join_list(self, l, d = ''):
        """Joins a list like string.join"""
        logging.debug("join_list('%s', '%s')" % (l, d))
        return d.join(v for v in l)


class UploadHandler(ServiceMessageHandler, BrubeckUploaderBaseHandler):
    """A sevice to upload an image, process it and push it to S3"""

    def put(self):
        logging.debug("UploadHandler put()")

        try:
            # save the file
            file_content = self.message.get_argument('file_content', '').decode('base64')
            file_name = self.message.get_argument('file_name', None)
            href = self.message.get_argument('href', None)

            logging.debug("file_name: %s" % file_name)
            hash = self.message.get_argument('hash', None)
            if self.settings is None:
                self._settings = self.message.get_argument('settings', '')

            image_infos = self.settings[self.message.get_argument('image_info_key', 'IMAGE_INFO')]
            logging.debug("image_infos: %s" % image_infos)
            if not href is None and (hash is None or hash != file_name):
                self.saveFile(href,
                    is_url=True,
                    hash=hash,
                )
            elif len(file_content) > 0 and len(self._settings) > 0:
                self.saveFile(file_name,
                    is_url=False,
                    hash=hash,
                    file_content=file_content
                )
            else:
                raise Exception('No file was uploaded')

            if self.uploader.upload_to_S3(hash, image_infos):
                # success
                self.set_status(200, "Uploaded to S3!")
            else:
                self.set_status(500, "Failed to upload to S3!")

                self.add_to_payload("file_name", file_name)
                self.add_to_payload("settings_image_info", image_infos)
                    
        except Exception as e:
            logging.debug(e.message)
            self.set_status(500)
            self.add_to_payload('error', e.message)
            raise


        self.headers = {"METHOD": "response"}
        return self.render()
