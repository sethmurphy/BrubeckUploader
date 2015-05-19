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
import os.path
from urlparse import urlparse
from PIL import Image as PilImage

import gevent
import magic
import boto
from boto.s3.key import Key

class Uploader(object):

    def __init__(self, settings):
        self.settings = settings
        self.conn = None

    def download_image_from_url(self, url, hash=None):
        """downloads and saves an image from given url
        returns the MD5 name of the file needed to upload to S3
        """
        # make a simple get request
        response = urllib2.urlopen(url)

        content = response.read()
        if hash is None:
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

    def create_images_for_S3(self, file_path, file_name,
                              color=(255,255,255), image_infos=None, arguments = None):
        """create our standard image sizes for upload to S3
        image_infos provides settings to customise sizes.
           TODO: Not very happy with image quality.
            peppered with gevent.sleep(0) to be a little less blocking.
        """
        logging.debug("create_images_for_S3")
        logging.debug("file_path: %s" % file_path)
        logging.debug("file_name: %s" % file_name)
        file_names = []
        quality_val = 100
        if image_infos is None:
            image_infos = self.settings['IMAGE_INFO']
        filename = "%s/%s" % (file_path, file_name)
        logging.debug("path and filename: %s" % filename)
        try:
            im = None
            logging.debug("create_images_for_S3 image_infos: %s " % str(image_infos))
            nim = None
            for image_info in image_infos:
                # convert to thumbnail image
                # imp = PilImage.new("RGB", im.size, (255,255,255,255))
                #imp.paste(im)
                # [([WIDTH], [HEIGHT]), [PIL FORMAT], [POSTFIX], [EXTENSION]]
                logging.debug("create_images_for_S3  image_info: %s " % str(image_info))
                temp_filename = "%s%s.%s" % (file_name,image_info[2], image_info[3])
                temp_fullfilename = "%s/%s" % (file_path, temp_filename)
                logging.debug("create_images_for_S3  temp_filename: %s " % temp_filename)
                logging.debug("create_images_for_S3  temp_fullfilename: %s " % temp_fullfilename)

                if os.path.isfile(temp_fullfilename):
                    logging.debug("create_images_for_S3 temp image already generated: %s " % temp_fullfilename)
                else:
                    logging.debug("create_images_for_S3 generating temp image: %s " % temp_fullfilename)
                    try:

                        if im is None:
                            logging.debug("create_images_for_S3  creating initial image to manipulate: %s " % str(file_name))
                            im = PilImage.open(filename)
                            im.load()
                            logging.debug("create_images_for_S3  converting initial image to RGB")
                            im = im.convert('RGBA')

                            logging.debug("create_images_for_S3 saving unscaled image as png")
                            im.save( "%s/%s%s.%s" % (file_path, file_name,'_o', 'png'), format='png', quality=quality_val)
                            file_names.append("%s%s.%s" % (file_name, '_o', 'png'))

                            # crop or not?
                            if (not arguments is None and
                                        "crop_x" in arguments and
                                        "crop_y" in arguments and
                                        "crop_width" in arguments and
                                        "crop_height" in arguments):
                                crop_x = arguments["crop_x"]
                                crop_y = arguments["crop_y"]
                                crop_width = arguments["crop_width"]
                                crop_height = arguments["crop_height"]
                                if (crop_x > 0 or
                                    crop_y > 0 or
                                    crop_width > 0 or
                                    crop_height > 0):
                                    im = im.crop((
                                                crop_x,
                                                crop_y,
                                                crop_x + crop_width,
                                                crop_y + crop_height
                                            ))

                                logging.debug("create_images_for_S3 saving cropped but unscaled image as png")
                                im.save( "%s/%s%s.%s" % (file_path, file_name,'_oc', 'png'), format='png', quality=quality_val)
                                file_names.append("%s%s.%s" % (file_name, '_oc', 'png'))

                            logging.debug("create_images_for_S3 rgba conversion on initial image")

                            logging.debug("create_images_for_S3 rgba bgcolor")
                            bgcolor = PilImage.new('RGBA', size = im.size, color = color)
                            logging.debug("create_images_for_S3 rgba _alpha_composite")
                            im = self._alpha_composite(im, bgcolor)
                            if im.mode != "RGB":
                                logging.debug("create_images_for_S3 rgba new background")
                                background = PilImage.new('RGB', im.size, color)
                                logging.debug("create_images_for_S3 rgba new background paste")
                                background.paste(im, mask=im.split()[3])
                                im = background
                                #im = im.convert("RGB")

                        if image_info[0] != None:
                            logging.debug("image_info[0]: %s" % str(image_info[0]))
                            logging.debug("image_info[1]: %s" % str(image_info[1]))
                            logging.debug("image_info[2]: %s" % str(image_info[2]))
                            logging.debug("image_info[3]: %s" % str(image_info[3]))
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

                                logging.debug("create_images_for_S3 resizing: %s, %s" % (width, height))
                                nim = im.resize((width, height), resample = PilImage.LANCZOS) # PILImage.ANTIALIAS
                                logging.debug(image_info[2])
                                if image_info[2] == '_blur':
                                    logging.debug('_blurblurblurblur')
                                    crop_box = (0, 0, 1920, 1080)
                                    ib = nim.crop(box)
                                    for i in range(100):  # with the BLUR filter, you can blur a few times to get the effect you're seeking
                                        ib = ib.filter(ImageFilter.BLUR)
                                    nim.paste(ib, crop_box)
                                    nim = nim.filter(ImageFilter.BLUR)
                                # check if we have a crop value
                                crop_x = 0
                                crop_y = 0
                                crop_width = 0
                                crop_height = 0
                                logging.debug("arguments: %s" % str(arguments))
                                if arguments and 'crop_x' in arguments:
                                    crop_x = arguments['crop_x']
                                if arguments and 'crop_y' in arguments:
                                    crop_y = arguments['crop_y']
                                if arguments and 'crop_width' in arguments:
                                    crop_width = arguments['crop_width']
                                if arguments and 'crop_height' in arguments:
                                    crop_height = arguments['crop_height']

                                logging.debug("crop_x: %s" % str(crop_x))
                                logging.debug("crop_y: %s" % str(crop_y))
                                logging.debug("crop_width: %s" % str(crop_width))
                                logging.debug("crop_height: %s" % str(crop_height))
                                if crop_x != 0 or crop_y!= 0 or crop_width != 0 or crop_height != 0 :
                                    logging.debug("Time to CROP!!")
                                else:
                                    logging.debug("No CROP for you!!")

                                logging.debug("create_images_for_S3 resizing save: %s, %s" % (temp_fullfilename, image_info[1]))
                                nim.save(temp_fullfilename, format=image_info[1], quality=quality_val)
                                nim = None
                            else:
                                # thumb
                                logging.debug("create_images_for_S3 thumbnail: %s, %s" % (width, height))
                                im.thumbnail((width, height), PilImage.ANTIALIAS)
                                logging.debug("create_images_for_S3 thumbnail save: %s, %s" % (temp_fullfilename, image_info[1]))
                                im.save(temp_fullfilename, format=image_info[1], quality=quality_val)
                        else:
                            # full size
                            logging.debug("create_images_for_S3 fullsize save: %s, %s" % (temp_fullfilename, image_info[1]))
                            im.save(temp_fullfilename, format=image_info[1], quality=quality_val)
                        logging.debug("filename created: %s" % (temp_filename))
                        file_names.append(temp_filename)
                    except Exception, ige:
                        logging.debug("image error inner loop: %s, %s" % (file_name, repr(ige)))
                        raise
            logging.debug("create_images_for_S3 return filenames: %s " % file_names)
        except Exception, e:
            logging.debug("image error outer loop: %s, %s" % (file_name, repr(e)))
            raise

        return file_names

    def _alpha_composite(self, src, dst):
        """places a background in place of transparancy.
        We need this because we are converting to jpeg.
        peppered with gevent.sleep(0) to be a little less blocking.
        """
        r, g, b, a = src.split()
        src = PilImage.merge("RGB", (r, g, b))
        mask = PilImage.merge("L", (a,))
        dst.paste(src, (0, 0), mask)
        return dst

    def get_connection_s3(self):
        """ create our s3 connection or return it if exists"""
        if self.conn is None:
            key = self.settings["AMAZON_KEY"]
            secret = self.settings["AMAZON_SECRET"]
            bucket_name = self.settings["AMAZON_BUCKET"]
            host = self.settings["S3_HOST"]
            port = self.settings["S3_PORT"]
            self.conn = boto.connect_s3(key, secret, host = host, port = port)
        return self.conn

    def upload_to_S3(self, file_name, image_infos = None, arguments = None, dest_bucket = None, hash=None):
        """upload a file to S3 and return the path name"""
        logging.debug("BrubeckUploader upload_to_S3 file_name : %s" % file_name)
        logging.debug("BrubeckUploader upload_to_S3 image_infos : %s" % image_infos)
        logging.debug("BrubeckUploader upload_to_S3 arguments : %s" % arguments)
        logging.debug("BrubeckUploader upload_to_S3 dest_bucket : %s" % dest_bucket)

        file_path = self.settings['TEMP_UPLOAD_DIR']
        file_names=[]
        if not image_infos is None:
            logging.debug("BrubeckUploader upload_to_S3 saving original file and generating images from image_infos: %s, %s" % (file_name, image_infos))
            file_names = self.create_images_for_S3(file_path, file_name, (255,255,255), image_infos, arguments)
        else:
            logging.debug("BrubeckUploader upload_to_S3 saving original file only: %s" % file_name)
            # write content to tmp
            if not hash is None:
                file_names=[hash]
            else:
                file_names=[file_name]
        logging.debug("BrubeckUploader upload_to_S3 file_names: %s" % file_names)
        logging.debug("BrubeckUploader upload_to_S3 len(file_names): %s" % len(file_names))
        bucket_name = self.settings["AMAZON_BUCKET"]
        if not dest_bucket is None:
            bucket_name = dest_bucket

        conn = self.get_connection_s3()

        if "INIT_BUCKET" not in self.settings or self.settings["INIT_BUCKET"] == False:
            # bucket must exist
            bucket = conn.get_bucket(bucket_name)
        else:
            logging.debug("BrubeckUploader upload_to_S3 init_bucket action")
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

        # images = self.create_images_for_S3(file_path, file_name)
        logging.debug("BrubeckUploader upload_to_S3 file_names: %s" % file_names)
        #logging.debug("images: %s" % images)
        for image_file_name in file_names:
            logging.debug("BrubeckUploader upload_to_S3 image_file_name: %s" % image_file_name)
            logging.debug( 'BrubeckUploader upload_to_S3 uploading %s to Amazon S3 bucket %s' % (image_file_name, bucket_name))
            k = Key(bucket)
            k.key = image_file_name
            k.set_contents_from_filename("%s/%s" % (file_path, image_file_name))
            acl = 'public-read'
            #logging.debug("acl: %s" % acl)
            k.set_acl(acl)

        return True

    def delete_from_S3(self, file_name):
        """Delete files originally uploaded to S3 with the give filename.
        This is just based on a pattern from the config file, not an actual log.
        """
        logging.debug("delete_from_S3 : %s" % file_name)

        bucket_name = self.settings["AMAZON_BUCKET"]
        conn = self.get_connect_s3()
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
