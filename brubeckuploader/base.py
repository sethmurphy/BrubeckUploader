#!/usr/bin/env python
# Copyright 2012 Brooklyn Code Incorporated. See LICENSE.md for usage
# the license can also be found at http://brooklyncode.com/LICENSE.md
##
## Just some basic file upload/s3 methods that know about brubeck settings
##
import os
import logging
import urllib2
import md5
import time
from urlparse import urlparse
from PIL import Image as PilImage

import gevent
import magic
import boto
from boto.s3.key import Key

class Uploader(object):

    def __init__(self, settings):
        self.settings = settings
        
    def download_image_from_url(self, url):
        """downloads and saves an image from given url
        returns the MD5 name of the file needed to upload to S3
        """
        # make a simple get request
        response = urllib2.urlopen(url)

        content = response.read()

        hash = str(md5.new(url + str(time.time())).hexdigest())
        download_file_name = self.settings['TEMP_UPLOAD_DIR'] + '/' + hash

        fd = os.open(download_file_name, os.O_RDWR|os.O_CREAT)
        os.write(fd, content)

        # get our mime-type
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(download_file_name)

        logging.debug("url: %s" % url)
        logging.debug("hash: %s" % hash)
        logging.debug("download_file_name: %s" % download_file_name)
        logging.debug("mime_type: %s" % mime_type)

        if not mime_type in self.settings['ACCEPTABLE_UPLOAD_MIME_TYPES']:
            raise Exception("unacceptable mime type: %s" % mime_type)
            os.remove(download_file_name)

        return hash

    def create_images_for_S3(self, file_path, file_name,color=(255,255,255)):
        """create our standard image sizes for upload to S3
           TODO: Not very happy with image quality.
            peppered with gevent.sleep(0) to be a little less blocking.
        """
        logging.debug("create_images_for_S3")
        logging.debug("file_path: %s" % file_path)
        logging.debug("file_name: %s" % file_name)
        file_names = []
        image_infos = self.settings['IMAGE_INFO']
        filename = "%s/%s" % (file_path, file_name)
        logging.debug("filename: %s" % filename)
        im = PilImage.open(filename)
        im.load()
        im = im.convert('RGBA')

        im.save( "%s/%s%s.%s" % (file_path, file_name,'_o', 'png'), format='png')
        file_names.append("%s%s.%s" % (file_name, '_o', 'png'))


        bgcolor = PilImage.new('RGBA', size = im.size, color = color)
        gevent.sleep(0)

        im = self._alpha_composite(im, bgcolor)
        gevent.sleep(0)

        if im.mode != "RGB":
            background = PilImage.new('RGB', im.size, color)
            gevent.sleep(0)
            background.paste(im, mask=im.split()[3])
            gevent.sleep(0)
            im = background
            #im = im.convert("RGB")

        for image_info in image_infos:
            # convert to thumbnail image
            # imp = PilImage.new("RGB", im.size, (255,255,255,255))
            #imp.paste(im)
            # [([WIDTH], [HEIGHT]), [PIL FORMAT], [POSTFIX], [EXTENSION]]
            if image_info[0] != None:
                width = image_info[0][0]
                height = image_info[0][1]
                if width == 0 or height == 0:
                    # width or height full other scaled
                    imsize = im.size
                    im_width = imsize[0]
                    im_height = imsize[1]
                    if width == 0 and height == 0:
                        width = im_width
                        height = im_height
                    elif width == 0:
                        # use height given and scale width
                        width = im_width * (height * 1000 / im_height) / 1000
                    else:
                        # use width given and scale height
                        height = im_height * (width * 1000 / im_width) / 1000

                    logging.debug("original height: %s" % im_height)
                    logging.debug("given height:    %s" % image_info[0][1])
                    logging.debug("new height:      %s" % height)

                    logging.debug("original width:  %s" % im_width)
                    logging.debug("given width:     %s" % image_info[0][0])
                    logging.debug("new width:       %s" % width)
                    nim = im.resize((width, height), PilImage.ANTIALIAS)
                    gevent.sleep(0)
                    nim.save( "%s/%s%s.%s" % (file_path, file_name,image_info[2], image_info[3]), image_info[1])
                    gevent.sleep(0)
                else:
                    # thumb
                    im.thumbnail((width, height), PilImage.ANTIALIAS)
                    gevent.sleep(0)
                    im.save( "%s/%s%s.%s" % (file_path, file_name,image_info[2], image_info[3]), image_info[1])
                    gevent.sleep(0)
            else:
                # full size
                gevent.sleep(0)
                im.save( "%s/%s%s.%s" % (file_path, file_name,image_info[2], image_info[3]), image_info[1])
                gevent.sleep(0)

            file_names.append("%s%s.%s" % (file_name, image_info[2], image_info[3]))

        logging.debug(file_names)
        return file_names    

    def _alpha_composite(self, src, dst):
        """places a background in place of transparancy.
        We need this because we are converting to jpeg.
        peppered with gevent.sleep(0) to be a little less blocking.
        """
        r, g, b, a = src.split()
        src = PilImage.merge("RGB", (r, g, b))
        gevent.sleep(0)
        mask = PilImage.merge("L", (a,))
        gevent.sleep(0)
        dst.paste(src, (0, 0), mask)
        gevent.sleep(0)
        return dst

    def upload_to_S3(self, file_name):
        """upload a file to S3 and return the path name"""
        logging.debug("upload_to_S3 : %s" % file_name)

        file_path = self.settings['TEMP_UPLOAD_DIR']
        file_names = self.create_images_for_S3(file_path, file_name)

        key = self.settings["AMAZON_KEY"]
        secret = self.settings["AMAZON_SECRET"]
        bucket_name = self.settings["AMAZON_BUCKET"]
        conn = boto.connect_s3(key, secret)

        if "INIT_BUCKET" not in self.settings or self.settings["INIT_BUCKET"] == False:
            # bucket must exist
            bucket = conn.get_bucket(bucket_name)
        else:
            ##
            ## If we wanted to always make sure we have a bucket we could do this, 
            ## but it is much more expensive
            ## We should set the INIT_BCUKET flag in the config when we start running, 
            ## then disable it when we are sure we have a bucket for performance reasons
            ## create or just get our bucket
            bucket = conn.create_bucket(bucket_name)
            # Set our policy so people can view new items 
            # (create bucket wipes permissions every time)
            bucket.set_policy("""{
                    "Version": "2008-10-17",
                    "Statement": [
                        {
                            "Sid": "AddPerm",
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": "*"
                            },
                            "Action": "s3:GetObject",
                            "Resource": "arn:aws:s3:::%s/*"
                        }
                    ]
                }
            """ % bucket_name)

        images = self.create_images_for_S3(file_path, file_name)
        for image_file_name in file_names:
            logging.debug( 'Uploading %s to Amazon S3 bucket %s' % (image_file_name, bucket_name))
            k = Key(bucket)
            k.key = image_file_name
            k.set_contents_from_filename("%s/%s" % (file_path, image_file_name))
            acl = 'public-read'
            logging.debug("acl: %s" % acl)
            k.set_acl(acl)

        return True

    def delete_from_S3(self, file_name):
        """Delete files originally uploaded to S3 with the give filename.
        This is just based on a pattern from the config file, not an actual log.
        """
        logging.debug("delete_from_S3 : %s" % file_name)

        key = self.settings["AMAZON_KEY"]
        secret = self.settings["AMAZON_SECRET"]
        bucket_name = self.settings["AMAZON_BUCKET"]
        conn = boto.connect_s3(key, secret)
        bucket = conn.get_bucket(bucket_name)
        image_infos = self.settings['IMAGE_INFO']

        for image_info in image_infos:
            image_file_name = "%s%s.%s" % (file_name, image_info[2], image_info[3])
            logging.debug( 'Deleting %s from Amazon S3 bucket %s' % (image_file_name, bucket_name))
            k = Key(bucket)
            k.key = image_file_name
            bucket.delete_key(k)

        # delete our original
        image_file_name = "%s_o.png" % file_name
        logging.debug( 'Deleting %s from Amazon S3 bucket %s' % (image_file_name, bucket_name))
        k = Key(bucket)
        k.key = image_file_name
        bucket.delete_key(k)

        return True
