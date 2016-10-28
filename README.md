Example
=======

Download a single image to the default `./photobucket/` directory:

```
python pb_shovel.py -u 'http://s160.photobucket.com/user/Spinningfox/media/Internet Fads/b217a64d.gif.html'
```

Obtain all the urls of a Photobucket Album, even subalbums, and put them in `links-<datetime>.txt`. This url file can be given to `wget` (just download all images) or [grab-site](https://github.com/ludios/grab-site) (archive all links as WARC).

```
python pb_shovel.py -u 'http://s160.photobucket.com/user/Spinningfox/library/Internet Fads' -r --links-only
wget -i links-2016-03-20_02-03-01.txt # or you can use curl
```

Usage
=====

```
usage: pb_shovel.py [-h] [-r] [-o OUTPUT_DIRECTORY] [--omit-existing]
                    [-v VERBOSE] (-f FILE | -u URLS [URLS ...])
                    [--images-only | --videos-only] [-n USERNAME]
                    [-p PASSWORD]

optional arguments:
  -h, --help            show this help message and exit
  -r, --recursive       Recursively extracts images and videos from all passed
                        sources.
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        The directory the extracted images getting saved in.
                        Default: `photobucket/` in current working directory
  --omit-existing
  -v VERBOSE, --verbose VERBOSE
  -f FILE, --file FILE  A file containing one or more Photobucket links which
                        you want to download.
  -u URLS [URLS ...], --urls URLS [URLS ...]
                        One or more links which point to an album or image
                        which is hosted on Photobucket.
  --images-only         Do not download any other filetype besides image.
  --videos-only         Do not download any other filetype besides video.
  --links-only          Only store the links to the images in a text file: links-<datetime>.txt

Authentication:
  -n USERNAME, --username USERNAME
                        The username or email which is used to authenticate
                        with Photobucket.
  -p PASSWORD, --password PASSWORD
                        The matching password for your account.

```

Recursive Album Downloads
=========================

If you're an archivist, you would obviously want to download all nested folders in the current
album. This script supports this feature: just add `-r` to download these nested folders. Done.

Extracting URLs
===============

The `--links-only` parameter can be used to store all the image URLs in a text file:

`links-<datetime>.txt`

This file can then be passed into `wget`, `wpull`, or `grab-site` to archive the 
images to a sane directory structure, or to to WARC format.

Guest password
=====================
Got guest password protected albums which you want to download?
simply pass the password with the URL you define with the
-u/--urls argument like so:
```
python pb_shovel.py -u "password@http://photobucket.com/example"
```
