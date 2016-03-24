import os
import re
import json
import argparse
from datetime import datetime
from sys import stderr
from urlparse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

#
#   Title:  pb_shovel.py
#   Author: Daxda
#   Date:   15.03.2014
#   Desc:   This script extracts the images on the image hosting site 'Photobucket'
#           you pass either a single url with the -u/--url flag which points to
#           either an album or a single image, the script then will extract the
#           direct links to the image and saves it under a custom path which you
#           can specify with the -o/--output-directory flag, when this argument
#           is not defined the output directory will fall back to the current
#           working directory.
#
#           This project originates not from myself, but my dear friend Kulverstukas
#           he came up with the idea and asked me if I could rewrite, his now outdated,
#           scraper. I gladly accepted and here we are! You should check out his
#           website, he has lots of interessting projects going on, http://9v.lt/blog/
#
#

# Name of the file that contains the links scraped in a session:
LINKS_FNAME = 'links-' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.txt'

class ImageInfo(object):
    """ Stores image information, contains the direct link to the image and
        various other information. """
    def __init__(self, filename, **kwargs):
        self.filename = filename
        self.title = kwargs.get("title")
        self.link = kwargs.get("originalUrl").replace("~original", "")
        self.mediaType = kwargs.get("mediaType")
        self.likeCount = kwargs.get("likeCount")
        self.commentCount = kwargs.get("commentCount")
        self.viewCount = kwargs.get("viewCount")
        self.username = kwargs.get("username")


class Photobucket():
    """ Scrapes the well known image hosting site Photobucket, either whole albums
        or single images. """
    def __init__(self, args):
        self._args = args
        self._session = requests.session()
        self._configure_session()
        self._authenticated = False
        self.collected_links = []
        self._downloaded_images = 0

    def _load_links(self):
        """ Load the links which were passed with the args and return them. """
        if(self._args.file):
            try: # Open the file the user passed with the -f/--file arg
                with open(self._args.file) as f:
                    links = [line.strip() for line in f.readlines() if line.strip()]
            except(IOError):
                stderr.write("Failed to open the specified file!\n")
                stder.flush()
                exit(1)
        else:
            links = [u for u in self._args.urls if u.strip()]
        return links

    def _get_password_from_url(self, url):
        """ Returns the password which is concatenated with the URL, as well as
            the actual URL. """
        if "@http://" not in url:
            return None, url
        password = url[:url.rindex("@http://")]
        if not password:
            return None, url
        up = urlparse(url[url.rindex("@http://")+1:])
        url = up.geturl()
        return password, url

    def _append_page_iter(self, link):
        """ Returns the passed URL modified to be able to iterate over the 'page='
            parameter easier. """
        up = urlparse(link)
        if "page=" in up.query:
            link = link[:link.rfind("page=")]
            link += "page="
        elif "sort=" in up.query:
            link += "page="
        elif "sort=" not in up.query and "page=" not in up.query:
                link += "?sort=3&page="
        else:
            return
        return link

    def _extract_album(self, link, source):
        """ Extracts the album pointed to by the passed link. """
        i = 1
        link = self._append_page_iter(link)
        collected_links = []
        try:
            if not link:
                raise ValueError
            while 1: # Iterate over each album page and extract all images
                source = self._get_source("{0}{1}".format(link, i), True)
                if not source:
                    break
                elif "End of album" in source:
                    break
                image_links = self._album(source)
                if not image_links or image_links == "End of album":
                    break
                collected_links.extend(image_links)
                collected_links = list(set(collected_links))
                stderr.write("\rCollected links: {0}".format(len(collected_links)))
                stderr.flush()
                i += 1
        except ValueError:
            stderr.write("Error: {0} appears to be an invalid link, skipping.\n".format(link))
            stderr.flush()
        except KeyboardInterrupt:
            pass
        finally:
            stderr.write("\n")
            stderr.flush()
            return collected_links

    def _extract_image(self, link, source):
        """ Returns the direct link to the passed link. """
        image_link = self._image(source)
        if not image_link:
            stderr.write("\rFailed to obtain image from {0}!\n".format(link))
            stderr.flush()
            return
        return image_link

    def _has_invalid_message(self, source):
        """ Returns bool when the passed source contains strings which indicate
            that the album/library is private or that a page doesn't exist. """
        invalid_strings = ("This album is empty.",
                           "Sorry, the requested page does not exist.",
                           "Library is Private.",
                           "This album is Private")
        for invalid_string in invalid_strings:
            if invalid_string in source:
                stderr.write("Error: {0}\n".format(invalid_string))
                stderr.flush()
                return True
        return False

    def extract(self):
        """ Starts the whole extraction process. """
        collected_links = []
        for link in self._load_links():
            if not link or "photobucket.com" not in link:
                continue
            password, link = self._get_password_from_url(link)
            source = self._get_source(link)
            if not source:
                stderr.write("Couldn't connect to {0}\n".format(link))
                stderr.flush()
                continue
            stderr.write("Processing: {0}\n".format(link))
            stderr.flush()
            try:
                # Determine which extraction method to use for the current link
                extraction_type = self._get_extraction_type(link, source)
                # Albums, Guest password protected albums and buckets are mostly
                # extracted the same with some few modifications in the routine
                if(extraction_type in ("Album", "Gpwd album", "Bucket")):
                    # Try to enter the guest password
                    if extraction_type == "Gpwd album":
                        if not password:
                            stderr.write("Error: No password for {0}\n".format(link))
                            stderr.flush()
                            continue
                        source = self._enter_guest_password(link, source, password)
                    # Act upon the -r/--recursive argument
                    if self._args.recursive:
                        collected_links.extend(self._extract_recursive(link))
                    else:
                        collected_links.extend(self._extract_album(link, source))
                elif extraction_type == "Image":
                    collected_links.append(self._image(source))
                else:
                    if self._has_invalid_message(source):
                        continue
            except(KeyboardInterrupt, EOFError):
                pass
            finally:
                stderr.write("\n")
                stderr.flush()

        collected_links = list(set(collected_links))
        self.collected_links.extend(collected_links)
        return collected_links

    def _get_extraction_type(self, url, source=""):
        """ Returns the passed url and source's type of image, the following
            return values are possible:

            Bucket..........Is the root directory of a profile, it contains ALL
                            albums.
            Album...........Can contain images/videos with sub-albums.
            Gpwd album......Guest password protected album, is the same as an
                            album but with a shared password which is not
                            obtainable from the source, and thus needs to be known.
            Image...........A single image (not direct link) on Photobucket.
            Not supported...Either the type couldn't be determined or it's not
                            supported. """
        up = urlparse(url)
        extraction_type = "Not supported"
        if up.path.endswith("/library") or up.path.endswith("/library/"):
            extraction_type = "Bucket"
        elif "/library/" in up.path and not up.path.endswith("/library/"):
            extraction_type = "Album"
        elif "/images/" in up.path or "/videos/" in up.path:
            extraction_type = "Album"
        elif "/media/" in up.path:
            extraction_type = "Image"
        elif "@http://" in up.path:
            extraction_type = "Gpwd album"

        if extraction_type == "Not supported":
            if "<h2>All Categories</h2>" in source:
                extraction_type = "Album"

        if self._is_guest_password_protected(source):
            extraction_type = "Gpwd album"

        if extraction_type == "Album" and source:
            # Check if the album requires a guest password
            # Check if the album is private
            if self._is_private_album(source):
                extraction_type = "Not supported"
        return extraction_type

    def _get_output_dir(self):
        """ Returns the output directory, either the pwd or the directory
            defined in the passed arguments.
            Subalbums are given a subdirectory to store their images in.
        """
        out = self._args.output_directory
        if not out:
            # Define the present working directory if it wasn't passed explicitly
            # with the -o/--output-directory argument.
            out = os.path.join(os.getcwd(), 'photobucket')
        elif out.startswith("~"):
            # Resolve the tilde char (which is the home directory on *nix) to
            # it's actual destination.
            home = os.environ.get("HOME")
            if not home:
                out = os.getcwd()
            else:
                out = os.path.join(home, out[1:])

        if not os.path.isdir(out) and not os.path.isfile(out):
            try:
                os.makedirs(out)
            except(OSError, IOError):
                stderr.write("Failed to create output directory,",\
                             "does it already exist?\n")
                stderr.flush()
                exit(1)

        # Add a trailing slash (or backslash) to the download directory, this is
        # necessary otherwise we would get an error when trying to write the down-
        # loaded file to the directory. (we want to write to file - not to the
        # directory itself)
        if not out.endswith(os.sep):
            out += os.sep
        return out

    def download_file(self, file_info):
        """ Downloads the file defined inside the passed fileinfo object. """
        # Skip certain file types when the arguments --images-only or videos-only
        # has been passed.
        if(self._args.images_only and file_info.mediaType.lower() == "video"
           or self._args.videos_only and file_info.mediaType.lower() == "image"):
            return

        # Write url to a file if the --links-only parameter was passed.
        if(self._args.links_only):
            print(file_info.link)
            with open(os.path.join(os.getcwd(), LINKS_FNAME), 'a+') as f:
                f.write(file_info.link + '\n')
            return

        out = self._get_output_dir()

        if not self._args.omit_existing:
            # Make sure we don't overwrite any photos with the same name,
            # we generate an unique filename in the format 'photo(1).jpg',
            # 'photo(2).jpg' when the file already exists.
            out = os.path.join(out, file_info.filename)
            if os.path.isfile(out):
                out = self._generate_unique_name(out)
        else:
            out += file_info.filename
            files = [f for f in os.listdir(self._get_output_dir()) if f]
            if file_info.filename in files:
                msg = "\rSkipping download for already existing file: {0}\n"
                stderr.write(msg.format(file_info.filename))
                stderr.flush()
                return

        # Fetch the url stored inside the fileinfo object and write the fetched
        # data into a file with the filename which is also stored inside the object.
        try:
            with open(out, "wb") as f:
                try:
                    req = requests.get(file_info.link, stream=True)
                    if req.status_code != requests.codes.ok:
                        return
                except requests.exceptions.RequestException:
                    stderr.write("\rFailed to download {0}\n".format(file_info.link))
                    stderr.flush()
                    return
                for chunk in req.iter_content():
                    if chunk:
                        f.write(chunk)
        except IOError as e:
            stderr.write("\nFailed to save the downloaded file ({0})\n".format(e.strerror))
            stderr.flush()
            exit(1)

        self._downloaded_images += 1

    def _generate_unique_name(self, filename):
        """ Handle duplicate file names. """
        unique = 1
        new_filename = filename
        while os.path.isfile(new_filename):
            # Store the file extension and add a number between the name and the
            # extension, then rebuild the path and check if it exists, if it does
            # the whole process is repeated until an unique file name was built.
            file_extension = filename[filename.rindex("."):]
            new_filename = "{0}({1}){2}".format(filename[:filename.rindex(".")],
                                                unique,
                                                file_extension)
            if(not os.path.isfile(new_filename)):
                return new_filename
            unique += 1

    def download_all_images(self):
        """ Downlods all collected images. """
        self._log_download_status()
        for file_obj in self.collected_links:
            try:
                self.download_file(file_obj)
            except(KeyboardInterrupt, EOFError):
                break
            else:
                if (not self._args.links_only): # don't display progress bar for just urls
                    self._log_download_status
                
        if (not self._args.links_only): # don't display progress bar for just urls
            stderr.write("\r                                             ")
            stderr.write("\n")
            self._log_download_status()
            stderr.write("\n")
            stderr.flush()

    def display_image_urls(self):
        for file_obj in self.collected_links:
            try:
                print(file_obj.link)
            except(KeyboardInterrupt, EOFError):
                break

    def _log_download_status(self):
        """ Prints the number of downloaded images and the total of images collected
            to stderr. """
        stderr.write("\rDownloaded files: {0}/{1}".format(self._downloaded_images,
                                                          len(self.collected_links)))
        stderr.flush()

    def _configure_session(self):
        """ Assignes the default headers to the session and obtains the session
            cookie when account credentials have been declared. """
        headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64;"+\
                                 " rv:29.0) Gecko/20100101 Firefox/29.0",
                   "Connection": "close"}
        self._session.headers.update(headers)
        # Try to authenticate
        if self._args.username and self._args.password:
         source = self._get_source("http://photobucket.com/")
         if source:
             token = self._get_token(source)
             if token:
                 self._login(self._args.username, self._args.password, token)

    def _get_source(self, url, check_for_eof=False):
        """ Returns the passed url's source code. """
        try: # Make the request with the passed url
            req = self._session.get(url, timeout=20)
            if req.status_code != requests.codes.ok:
                raise requests.exceptions.RequestException
            if check_for_eof and "page=" not in req.url:
                raise EOFError
        except(requests.exceptions.RequestException) as e:
            return
        except(EOFError):
            return "End of album"
        return req.content

    def _get_token(self, source):
        """ Returns the token of the passed source. """
        try:
            soup = BeautifulSoup(source)
            token = soup.find(id="token")["value"]
        except(TypeError, KeyError):
            return
        return token

    def _image(self, source):
        """ Returns the an ImageInfo object when the passed source contains the
            required data, None if the image couldn't get extracted. """
        # Try to find the json formated data blob which contains all info we need
        data = re.search("Pb\.Data\.Shared\.put\(Pb\.Data\.Shared\.MEDIA,.*?\);",
                         source)
        if not data:
            return
        # Form the data to a valid json body
        data = data.group().replace("Pb.Data.Shared.put(Pb.Data.Shared.MEDIA,", "")\
                   .strip()
        if(data.endswith(");")):
            data = data[:-2]
        try: # Parse the data blob
            j = json.loads(data)
        except(Exception):
            return
        # Build the image info object and return it
        return ImageInfo(j["name"], **j)

    def _get_var_albumJson(self, source):
        """ Returns the 'var albumJson' json data from the passed source, this
            blob of data contains various library(Bucket) information. """
        assert "var albumJson =" in source
        data = re.search("var albumJson.*\n", source)
        data = data.group().replace("var albumJson = ", "").strip()[:-1]
        return json.loads(data)

    def _get_sub_albums(self, source, album_name="Library"):
        """ Returns a list of sub-albums of the passed source. """
        token = self._get_token(source)
        library_info = self._get_var_albumJson(source)
        username = library_info.get("ownername")

        if not token or not library_info or not username:
            return

        # Build the api URL, fill in the token, username and optional album name
        # to obtain the sub-album data
        api_url = "http://photobucket.com/api/user/{0}/album/".format(username)
        if album_name != "Library":
            api_url += "{}/".format(album_name)
        api_url += "get?subAlbums=8&json=1&hash={}".format(token)
        # Make the request with the new assembled URL
        req = self._session.get(api_url)
        if req.status_code != requests.codes.ok:
            return
        try:
            return req.json()
        except ValueError:
            return

    def _get_var_collectionData(self, source, collectionId="libraryAlbums"):
        """ Extracts the 'collectionData' json data from the passed source and
            returns it. """
        assert "collectionData:" in source
        soup = BeautifulSoup(source)
        data = None
        for blob in soup.find_all("script"):
            if "collectionId: '{0}'".format(collectionId) in blob.text:
                data = re.search("collectionData:.*?\n", blob.text).group().strip()
                data = data.replace("collectionData: ", "").strip()
                if(data.endswith("},")):
                    data = data[:-1]
        assert bool(data)
        return json.loads(data)

    def _album(self, source):
        """ Returns a list of image files from the passed source on success. """
        try:
            # Obtain the album image objects from the json data which is found
            # in the passed source
            if "<h2>All Categories</h2>" in source or "<a id=\"images\"" in source:
                j = self._get_var_collectionData(source, "search")
            else:
                j = self._get_var_collectionData(source)
            if not j:
                raise EOFError
            images = j.get("items").get("objects")
            if not images:
                raise EOFError
        except(EOFError):
            return "End of album"
        # Try to detect the first page and print the estimated file count
        # to stderr.
        if(j["pageNumber"] == 1):
            self._print_album_stats(source)
            stderr.flush()
        image_objects = []
        for obj in images:
            new_link = obj.get("fullsizeUrl")
            up = urlparse(new_link)
            new_link = "{0}~original".format(up.geturl())
            obj["originalUrl"] = new_link
            image_objects.append(ImageInfo(obj["name"], **obj))

        image_objects = [ImageInfo(obj["name"], **obj) for obj in images if obj]
        return image_objects

    def _get_album_stats(self, json_data):
        """ Returns a dictionary containing the amount of images, videos, views
            and sub-albums. """
        if json_data.get("data"):
            stats = json_data["data"]["albumStats"]
        else:
            stats = json_data["albumStats"]
        return {"Images": stats["images"]["count"],
                "Videos": stats["videos"]["count"],
                "Sub-albums": stats["subalbums"]["count"]}

    def _print_album_stats(self, source):
        """ Prints out the album stats for the passed source. """
        if "albumJson" not in source:
            return
        album_json = self._get_var_albumJson(source)
        stats = self._get_album_stats(album_json)
        for k, v in stats.items():
            stderr.write("{0}: {1}\n".format(k, v))
        stderr.write("\n")
        stderr.flush()

    def _extract_recursive(self, start_url):
        """ Recursively extracts all images and videos from the passed start URL,
            this means that each sub-album in albums is visited, as well as their
            sub-sub-albums until sub-sub-ception is reached. """
        unvisited = [start_url]
        visited = []
        collected_links = []
        try:
            while unvisited:
                # Pop an URL from the unvisited list
                url = unvisited.pop()
                if url in visited:
                    continue
                # Get the images of the current URL
                source = self._get_source(url)
                collected_links.extend(self._extract_album(url, source))
                album_json = self._get_var_albumJson(source)
                if album_json.get("isRootAlbum"):
                    album_info = self._get_sub_albums(source)
                else:
                    album_info = self._get_sub_albums(source, album_json.get("location"))

                # Print the album stats for the current URL
                self._print_album_stats(self._get_album_stats(album_json))
                # Add sub-album links to the unvisited list when there are any
                if album_info.get("data").get("subAlbumCount") > 0:
                    for album in album_info.get("data").get("subAlbums"):
                        unvisited.append(album.get("url")+"?sort=3&page=")
                visited.append(url)
        except KeyboardInterrupt:
            pass
        finally:
            return collected_links

    def _login(self, username, password, token):
        """ Tries to authenticate with the Photubucket servers. """
        post_url = "https://secure.photobucket.com/action/auth/login"
        post_data = {"hash": token, "returnUrl": "", "username": username,
                     "password": password}
        try:
            req = self._session.post(post_url, data=post_data)
        except requests.exceptions.RequestException:
            pass
        self._authenticated = "pbauth" in self._session.cookies
        if not self._authenticated:
            stderr.write("ERROR: Failed to login with the passed credentials!\n")
            stderr.flush()
        return "pbauth" in self._session.cookies

    def _is_private_album(self, source):
        """ Returns bool if the passed source's album is private. """
        return "This album is Private." in source

    def _is_guest_password_protected(self, source):
        """ Returns bool if the passed source has the guest password input element. """
        soup = BeautifulSoup(source)
        identifier = soup.find("form", id="guestLoginForm")
        return bool(identifier)

    def _enter_guest_password(self, url, source, password):
        """ Tries to authenticate with a passed guest password to be able to
            extract images from guest password protected albums, returns the
            source of the album on success and None on failure. """
        # Return the passed source without modification when it contains the
        # indications that the album doesn't require a password
        if("This album is Password-Protected." not in source):
            return source

        # The authentication requires the following parameters to be posted back
        # to Photobucket's server:
        #
        #   POST to http://s326.photobucket.com/action/album/login
        #
        #   albumPath:.........../albums/k402/daxda/private_test
        #   albumType:...........album
        #   albumView:...........library
        #   visitorPassword:.....password
        #   hash:................07fc142dc0c867a9a9881e222ca6c57f
        #
        #
        post_data = {"albumPath": "", "albumType": "", "albumView": "",
                     "hash": "", "visitorPassword": password}
        try: # Fill up the post_data dictionary with the required values
            soup = BeautifulSoup(source)
            form = soup.find(id="guestLoginForm")
            post_data["albumPath"] = form.find_all("input")[0]["value"]
            post_data["albumType"] = form.find_all("input")[1]["value"]
            post_data["albumView"] = form.find_all("input")[2]["value"]
            post_data["hash"] = self._get_token(source)
            post_url = urljoin(url, form["action"])
        except(AttributeError, IndexError):
            stderr.write("Failed to authenticate\n")
            stderr.flush()
            return

        try: # Post the data
            req = self._session.post(post_url, data=post_data)
            if req.status_code != requests.codes.ok:
                message = "Failed to authenticate with {0}, status code was {1}\n"
                raise ValueError(message.format(post_url, req.status_code))
            if "Password is incorrect." in req.content:
                raise ValueError("Invalid password for {0}\n".format(url))
        except(requests.exceptions.RequestException, ValueError) as e:
            stderr.write(e.message)
            stderr.flush()
            return
        return req.content


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--recursive",
                        help="Recursively extracts images and videos from all"+\
                             " passed sources.",
                        action="store_true")
    parser.add_argument("-o", "--output-directory",
                        help="The directory the extracted images getting saved in.",
                        required=False)
    parser.add_argument("--omit-existing", action="store_true", required=False)
    parser.add_argument("-v", "--verbose", required=False)

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-f", "--file",
                             help="A file containing one or more Photobucket links"+\
                                  " which you want to download.")
    input_group.add_argument("-u", "--urls",
                             help="One or more links which point to an album or"+\
                                  " image which is hosted on Photobucket.",
                             nargs="+")

    type_group = parser.add_mutually_exclusive_group(required=False)
    type_group.add_argument("--images-only",
                        help="Do not download any other filetype besides image.",
                        action="store_true")
    type_group.add_argument("--videos-only",
                        help="Do not download any other filetype besides video.",
                        action="store_true")
    type_group.add_argument("--links-only",
                        help="Only store the links to the images in a text file: links-<datetime>.txt.",
                        action="store_true")

    auth_grp = parser.add_argument_group("Authentication")
    auth_grp.add_argument("-n", "--username",
                          help="The username or email which is used to authenticate"+\
                               " with Photobucket.")
    auth_grp.add_argument("-p", "--password",
                          help="The matching password for your account. ")



    args = parser.parse_args()

    # When the username has been passed the password must be set aswell
    if args.username and not args.password or args.password and not args.username:
        stderr.write("Both username and password are required, either pass both"+\
                     " or ommit the authentication arguments.\n")
        stderr.flush()
        exit(1)

    pb = Photobucket(args)
    pb.extract()
    pb.download_all_images()

