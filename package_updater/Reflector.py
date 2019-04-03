#!/usr/bin/env python3

# Copyright (C) 2012, 2013  Xyne
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# (version 2) as published by the Free Software Foundation.
#
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import argparse
import calendar
import datetime
import errno
import getpass
import http.client
import json
import logging
import os
import pipes
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


# Generic MirrorStatus Exception
class MirrorStatusError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def get_cache_file():
    bname = 'mirrorstatus.json'
    path = os.getenv('XDG_CACHE_HOME')
    if path:
        try:
            os.makedirs(path, exist_ok=True)
        # Raised if permissions do not match umask
        except FileExistsError:
            pass
        return os.path.join(path, bname)
    else:
        return '/tmp/.{}.{}'.format(getpass.getuser(), bname)


class MirrorStatus(object):
    # JSON URI
    URL = 'https://www.archlinux.org/mirrors/status/json/'
    # Mirror URL format. Accepts server base URL, repository, and architecture.
    MIRROR_URL_FORMAT = '{0}{1}/os/{2}'
    MIRRORLIST_ENTRY_FORMAT = "Server = " + MIRROR_URL_FORMAT + "\n"
    DISPLAY_TIME_FORMAT = '%Y-%m-%d %H:%M:%S UTC'
    PARSE_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
    # Required for the last_check field, which oddly includes microseconds.
    PARSE_TIME_FORMAT_WITH_USEC = '%Y-%m-%dT%H:%M:%S.%fZ'
    # Recognized list sort types and their descriptions.
    SORT_TYPES = {
        'age': 'last server synchronization',
        'rate': 'download rate',
        'country': 'server\'s location',
        'score': 'MirrorStatus score',
        'delay': 'MirrorStatus delay',
    }
    # Known repositories, i.e. those that should be on each mirror.
    # Used to replace the "$repo" variable.
    # TODO
    # Avoid using a hard-coded list.
    # See https://bugs.archlinux.org/task/32895
    REPOSITORIES = (
        'community',
        'community-staging',
        'community-testing',
        'core',
        'extra',
        'gnome-unstable',
        'kde-unstable',
        'multilib',
        'multilib-testing'
        'staging',
        'testing'
    )

    # Known system architectures, as used to replace the "$arch" variable.
    ARCHITECTURES = ['x86_64']

    # Initialize
    # refresh_interval:
    #   The cached list will be replaced after this many seconds have passed.
    #   0 effectively disables caching.
    #   Caching is only useful if the object persists, e.g. if it were embedded
    #   in a server.
    def __init__(
            self,
            refresh_interval=0,
            verbose=False,
            connection_timeout=5,
            #     download_timeout=None,
            cache_timeout=300,
            min_completion_pct=1.,
            threads=5
    ):
        self.refresh_interval = refresh_interval

        # Last modification time of the json object.
        self.json_mtime = 0
        # The parsed JSON object.
        self.json_obj = {}
        # Display extra information.
        self.verbose = verbose
        # Connection timeout
        self.connection_timeout = connection_timeout
        # Download timeout
        #     self.download_timeout = download_timeout
        # Cache timeout
        self.cache_timeout = cache_timeout
        # Minimum completion percent, for filtering mirrors.
        self.min_completion_pct = min_completion_pct
        # Threads
        self.threads = threads

    def retrieve(self):
        """Retrieve the current mirror status JSON data."""
        self.json_obj = None
        json_str = None
        save_json = False

        cache_file = get_cache_file()
        if self.cache_timeout > 0:
            save_json = True
            try:
                mtime = os.path.getmtime(cache_file)
                if time.time() - mtime < self.cache_timeout:
                    try:
                        with open(cache_file) as f:
                            self.json_obj = json.load(f)
                        self.json_mtime = mtime
                        save_json = False
                    except IOError as e:
                        raise MirrorStatusError('failed to load cached JSON data ({})'.format(e))
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise MirrorStatusError('failed to get cache file mtime ({})'.format(e))

        if not self.json_obj:
            try:
                with urllib.request.urlopen(MirrorStatus.URL, None, self.connection_timeout) as f:
                    json_str = f.read()
                    self.json_obj = json.loads(json_str.decode())
                    self.json_mtime = time.time()
            except (urllib.error.URLError, socket.timeout) as e:
                raise MirrorStatusError('failed to retrieve mirror data: ({})'.format(e))
            except ValueError as e:
                raise MirrorStatusError('failed to parse retrieved mirror data: ({})'.format(e))

        try:
            # Remove servers that have not synced, and parse the "last_sync" times for
            # comparison later.
            mirrors = self.json_obj['urls']
            # Filter incomplete mirrors  and mirrors that haven't synced.
            mirrors = list(
                m for m in mirrors
                if m['last_sync']
                and m['completion_pct'] >= self.min_completion_pct
            )
            # Parse 'last_sync' times for future comparison.
            for mirror in mirrors:
                mirror['last_sync'] = calendar.timegm(
                    time.strptime(mirror['last_sync'],
                                  MirrorStatus.PARSE_TIME_FORMAT)
                )
            self.json_obj['urls'] = mirrors
        except KeyError:
            raise MirrorStatusError(
                'failed to parse retrieved mirror data (the format may have changed or there may be a transient error)')

        if save_json and json_str:
            try:
                with open(cache_file, 'wb') as f:
                    f.write(json_str)
            except IOError as e:
                raise MirrorStatusError('failed to cache JSON data ({})'.format(e))

    def get_obj(self):
        """Return the JSON object, retrieving new data if necessary."""
        if not self.json_obj \
                or time.time() > (self.json_mtime + self.refresh_interval):
            self.retrieve()

        return self.json_obj

    def get_mirrors(self):
        """Get the mirrors."""
        return self.get_obj()['urls']

    def filter(
            self,
            mirrors=None,
            countries=None,
            regexes=None,  # TODO: remove
            include=None,
            exclude=None,
            age=None,
            protocols=None
    ):
        """Filter using different parameters."""
        # TODO: remove
        if regexes:
            #       raise MirrorStatusError('The "regexes" keyword has been deprecated and replaced by "include" and "exclude".')
            if not include:
                include = regexes
            sys.stderr.write('''WARNING: The "regexes" keyword has been deprecated and replaced by "include" and "exclude".
         Support will be soon removed without further warning.''')
        if mirrors is None:
            mirrors = self.get_mirrors()

        t = time.time()
        n = 0

        # Make country arguments case-insensitive.
        uc_countries = tuple(c.upper() for c in countries) if countries else None
        for mirror in mirrors:
            # Filter by country.
            if countries \
                    and not ( \
                            mirror['country'].upper() in uc_countries or \
                            mirror['country_code'].upper() in uc_countries \
                    ):
                continue
            # Filter by protocol.
            if protocols and not mirror['protocol'] in protocols:
                continue
            # Filter by regex.
            # TODO: Find a better way to do this.
            if include:
                for regex in include:
                    if re.search(regex, mirror['url']):
                        break
                else:
                    continue
            if exclude:
                discard = False
                for regex in exclude:
                    if re.search(regex, mirror['url']):
                        discard = True
                        break
                if discard:
                    continue
            # Filter by hours since last sync.
            if age and t > (age * 60 ** 2 + mirror['last_sync']):
                continue

            # Yield if we're still here.
            yield mirror

    def sort(self, mirrors=None, by=None):
        """Sort using different parameters."""
        if mirrors is None:
            mirrors = self.get_mirrors()
        # Ensure that "mirrors" is a list that can be sorted.
        if not isinstance(mirrors, list):
            mirrors = list(mirrors)

        if by == 'age':
            mirrors.sort(key=lambda m: m['last_sync'], reverse=True)
        elif by == 'rate':
            mirrors = self.rate(mirrors)
        elif by in ('country', 'country_code', 'delay', 'score'):
            mirrors.sort(key=lambda m: m[by])
        return mirrors

    # Sort mirrors by download speed. Download speed will be calculated from the
    # download time of the [core] database from each server.
    # TODO: Consider ways to improve this.
    # TODO: Consider the effects of threading (do the threads affect the results
    #       by competing for bandwidth?)
    def rate(self, mirrors=None, threads=5):
        if mirrors is None:
            mirrors = self.get_mirrors()
        if not threads:
            threads = self.threads
        # Ensure that "mirrors" is a list and not a generator.
        if not isinstance(mirrors, list):
            mirrors = list(mirrors)

        if not mirrors:
            logging.warning('no mirrors selected for rating')
            return mirrors

        # Ensure a sane number of threads.
        if threads < 1:
            threads = 1
        else:
            threads = min(threads, len(mirrors))

        rates = {}

        # URL input queue.Queue
        q_in = queue.Queue()
        # URL and rate output queue.Queue
        q_out = queue.Queue()

        def worker():
            while True:
                url = q_in.get()
                db_subpath = 'core/os/x86_64/core.db'
                db_url = url + db_subpath
                scheme = urllib.parse.urlparse(url).scheme
                # Leave the rate as 0 if the connection fails.
                # TODO: Consider more graceful error handling.
                rate = 0
                dt = float('NaN')

                # urllib cannot handle rsync protocol
                if scheme == 'rsync':
                    rsync_cmd = [
                        'rsync',
                        '-avL', '--no-h', '--no-motd',
                        '--contimeout={}'.format(self.connection_timeout),
                        db_url
                    ]
                    try:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            t0 = time.time()
                            subprocess.check_call(
                                rsync_cmd + [tmpdir],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                            dt = time.time() - t0
                            size = os.path.getsize(os.path.join(
                                tmpdir,
                                os.path.basename(db_subpath)
                            ))
                            rate = size / dt
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                        pass
                else:
                    req = urllib.request.Request(url=db_url)
                    try:
                        t0 = time.time()
                        with urllib.request.urlopen(req, None, self.connection_timeout) as f:
                            size = len(f.read())
                            dt = time.time() - t0
                            rate = size / (dt)
                    except (OSError, urllib.error.HTTPError, http.client.HTTPException):
                        pass
                q_out.put((url, rate, dt))
                q_in.task_done()

        # Launch threads
        for i in range(threads):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()

        # Load the input queue.Queue
        url_len = max(len(m['url']) for m in mirrors)
        for mirror in mirrors:
            logging.info("rating {}".format(mirror['url']))
            q_in.put(mirror['url'])

        q_in.join()

        # Get the results
        # The "in mirrors" loop is just used to ensure that the right number of
        # items is retrieved.

        # Display some extra data.
        header_fmt = '{{:{:d}s}}  {{:>14s}}  {{:>9s}}'.format(url_len)
        logging.info(header_fmt.format('Server', 'Rate', 'Time'))
        fmt = '{{:{:d}s}}  {{:8.2f}} KiB/s  {{:7.2f}} s'.format(url_len)

        # Loop over the mirrors just to ensure that we get the rate for each mirror.
        # The value in the loop does not (necessarily) correspond to the mirror.
        for _ in mirrors:
            url, rate, dt = q_out.get()
            kibps = rate / 1024.0
            logging.info(fmt.format(url, kibps, dt))
            rates[url] = rate
            q_out.task_done()

        # Sort by rate.
        rated_mirrors = [m for m in mirrors if rates[m['url']] > 0]
        rated_mirrors.sort(key=lambda m: rates[m['url']], reverse=True)

        return rated_mirrors + [m for m in mirrors if rates[m['url']] == 0]

    def display_time(self, t=None):
        '''Format a time for display.'''
        return time.strftime(self.DISPLAY_TIME_FORMAT, t)

    # Return a Pacman-formatted mirrorlist
    # TODO: Reconsider the assumption that self.json_obj has been retrieved.
    def get_mirrorlist(self, mirrors=None, include_country=False, cmd=None):
        if mirrors is None:
            mirrors = self.get_mirrors()
        if cmd is None:
            cmd = '?'
        else:
            cmd = 'reflector ' + ' '.join(pipes.quote(x) for x in cmd)

        last_check = self.json_obj['last_check']
        # For some reason the "last_check" field included microseconds.
        try:
            parsed_last_check = datetime.datetime.strptime(
                last_check,
                self.PARSE_TIME_FORMAT_WITH_USEC,
            ).timetuple()
        except ValueError:
            parsed_last_check = datetime.datetime.strptime(
                last_check,
                self.PARSE_TIME_FORMAT,
            ).timetuple()

        width = 80
        colw = 11
        header = '# Arch Linux mirrorlist generated by Reflector #'.center(width, '#')
        border = '#' * len(header)
        mirrorlist = '{}\n{}\n{}\n'.format(border, header, border) + \
                     '\n' + \
                     '\n'.join(
                         '# {{:<{:d}s}} {{}}'.format(colw).format(k, v) for k, v in (
                             ('With:', cmd),
                             ('When:', self.display_time(time.gmtime())),
                             ('From:', MirrorStatus.URL),
                             ('Retrieved:', self.display_time(time.gmtime(self.json_mtime))),
                             ('Last Check:', self.display_time(parsed_last_check)),
                         )
                     ) + \
                     '\n\n'

        country = None

        # mirrors may be a generator so "if mirrors" will not work
        no_mirrors = True
        for mirror in mirrors:
            no_mirrors = False
            # Include country tags. This is intended for lists that are sorted by
            # country.
            if include_country:
                c = '{} [{}]'.format(mirror['country'], mirror['country_code'])
                if c != country:
                    if country:
                        mirrorlist += '\n'
                    mirrorlist += '# {}\n'.format(c)
                    country = c
            mirrorlist += MirrorStatus.MIRRORLIST_ENTRY_FORMAT.format(mirror['url'], '$repo', '$arch')

        if no_mirrors:
            return None
        else:
            return mirrorlist

    def list_countries(self):
        countries = dict()
        for m in self.get_mirrors():
            k = (m['country'], m['country_code'])
            try:
                countries[k] += 1
            except KeyError:
                countries[k] = 1
        return countries


class ListCountries(argparse.Action):
    '''
  Action to list countries along with the number of mirrors in each.
  '''

    def __call__(self, parser, namespace, values, option_string=None):
        ms = MirrorStatus()
        countries = ms.list_countries()
        w = max(len(c) for c, cc in countries)
        n = len(str(max(countries.values())))
        fmt = '{{:{:d}s}} {{}} {{:{:d}d}}'.format(w, n)
        for (c, cc), n in sorted(countries.items(), key=lambda x: x[0][0]):
            print(fmt.format(c, cc, n))
        sys.exit(0)


def print_mirror_info(mirrors, time_fmt=MirrorStatus.DISPLAY_TIME_FORMAT):
    '''
  Print information about each mirror to STDOUT.
  '''
    if mirrors:
        if not isinstance(mirrors, list):
            mirrors = list(mirrors)
        ks = sorted(k for k in mirrors[0].keys() if k != 'url')
        l = max(len(k) for k in ks)
        fmt = '{{:{:d}s}} : {{}}'.format(l)
        for m in mirrors:
            print('{}$repo/os/$arch'.format(m['url']))
            for k in ks:
                v = m[k]
                if k == 'last_sync':
                    v = time.strftime(time_fmt, time.gmtime(v))
                print(fmt.format(k, v))
            print()


def add_arguments(parser):
    '''
  Add reflector arguments to the argument parser.
  '''
    parser = argparse.ArgumentParser(description='retrieve and filter a list of the latest Arch Linux mirrors')

    parser.add_argument(
        '--connection-timeout', type=int, metavar='n', default=5,
        help='The number of seconds to wait before a connection times out.'
    )

    #   parser.add_argument(
    #     '--download-timeout', type=int, metavar='n',
    #     help='The number of seconds to wait before a download times out. The threshold is checked after each chunk is read, so the actual timeout may take longer.'
    #   )

    parser.add_argument(
        '--list-countries', action=ListCountries, nargs=0,
        help='Display a table of the distribution of servers by country.'
    )

    parser.add_argument(
        '--cache-timeout', type=int, metavar='n', default=300,
        help='The cache timeout in seconds for the data retrieved from the Arch Linux Mirror Status API. The default is 300 (5 minutes).'
    )

    parser.add_argument(
        '--save', metavar='<filepath>',
        help='Save the mirrorlist to the given path.'
    )

    sort_help = '; '.join('"{}": {}'.format(k, v) for k, v in MirrorStatus.SORT_TYPES.items())
    parser.add_argument(
        '--sort', choices=MirrorStatus.SORT_TYPES,
        help='Sort the mirrorlist. {}.'.format(sort_help)
    )

    parser.add_argument(
        '--threads', type=int, metavar='n',
        help='The number of threads to use when rating mirrors.'
    )

    parser.add_argument(
        '--verbose', action='store_true',
        help='Print extra information to STDERR. Only works with some options.'
    )

    parser.add_argument(
        '--info', action='store_true',
        help='Print mirror information instead of a mirror list. Filter options apply.'
    )

    filters = parser.add_argument_group(
        'filters',
        'The following filters are inclusive, i.e. the returned list will only contain mirrors for which all of the given conditions are met.'
    )

    filters.add_argument(
        '-a', '--age', type=float, metavar='n',
        help='Only return mirrors that have synchronized in the last n hours. n may be an integer or a decimal number.'
    )

    filters.add_argument(
        '-c', '--country', dest='countries', action='append', metavar='<country>',
        help='Match one of the given countries (case-sensitive). Use "--list-countries" to see which are available.'
    )

    filters.add_argument(
        '-f', '--fastest', type=int, metavar='n',
        help='Return the n fastest mirrors that meet the other criteria. Do not use this option without other filtering options.'
    )

    filters.add_argument(
        '-i', '--include', metavar='<regex>', action='append',
        help='Include servers that match <regex>, where <regex> is a Python regular express.'
    )

    filters.add_argument(
        '-x', '--exclude', metavar='<regex>', action='append',
        help='Exclude servers that match <regex>, where <regex> is a Python regular express.'
    )

    filters.add_argument(
        '-l', '--latest', type=int, metavar='n',
        help='Limit the list to the n most recently synchronized servers.'
    )

    filters.add_argument(
        '--score', type=int, metavar='n',
        help='Limit the list to the n servers with the highest score.'
    )

    filters.add_argument(
        '-n', '--number', type=int, metavar='n',
        help='Return at most n mirrors.'
    )

    filters.add_argument(
        '-p', '--protocol', dest='protocols', action='append', metavar='<protocol>',
        help='Match one of the given protocols, e.g. "http", "ftp".'
    )

    filters.add_argument(
        '--completion-percent', type=float, metavar='[0-100]', default=100.,
        help='Set the minimum completion percent for the returned mirrors. Check the mirrorstatus webpage for the meaning of this parameter. Default value: %(default)s.'
    )

    return parser


def parse_args(args=None):
    '''
  Parse command-line arguments.
  '''
    parser = argparse.ArgumentParser(
        description='retrieve and filter a list of the latest Arch Linux mirrors'
    )
    parser = add_arguments(parser)
    options = parser.parse_args(args)
    return options


# Process options
def process_options(options, ms=None, mirrors=None):
    '''
  Process options.

  Optionally accepts a MirrorStatus object and/or the mirrors as returned by
  the MirrorStatus.get_mirrors method.
  '''
    if not ms:
        ms = MirrorStatus(
            verbose=options.verbose,
            connection_timeout=options.connection_timeout,
            #       download_timeout=options.download_timeout,
            cache_timeout=options.cache_timeout,
            min_completion_pct=(options.completion_percent / 100.),
            threads=options.threads
        )

    if mirrors is None:
        mirrors = ms.get_mirrors()

    # Filter
    mirrors = ms.filter(
        mirrors,
        countries=options.countries,
        include=options.include,
        exclude=options.exclude,
        age=options.age,
        protocols=options.protocols
    )

    if options.latest and options.latest > 0:
        mirrors = ms.sort(mirrors, by='age')
        mirrors = mirrors[:options.latest]

    if options.score and options.score > 0:
        mirrors = ms.sort(mirrors, by='score')
        mirrors = mirrors[:options.score]

    if options.fastest and options.fastest > 0:
        mirrors = ms.sort(mirrors, by='rate')
        mirrors = mirrors[:options.fastest]

    if options.sort and not (options.sort == 'rate' and options.fastest):
        mirrors = ms.sort(mirrors, by=options.sort)

    if options.number:
        mirrors = list(mirrors)[:options.number]

    return ms, mirrors


def main(args=None, configure_logging=False):
    if args:
        cmd = tuple(args)
    else:
        cmd = sys.argv[1:]

    options = parse_args(args)

    if configure_logging:
        if options.verbose:
            level = logging.INFO
        else:
            level = logging.WARNING
        logging.basicConfig(
            format='[{asctime:s}] {levelname:s}: {message:s}',
            style='{',
            datefmt='%Y-%m-%d %H:%M:%S',
            level=level
        )

    try:
        ms, mirrors = process_options(options)
        if mirrors is not None and not isinstance(mirrors, list):
            mirrors = list(mirrors)
        if not mirrors:
            sys.exit('error: no mirrors found')
        include_country = options.sort == 'country'
        # Convert the generator object to a list for re-use later.
        if options.info:
            print_mirror_info(mirrors)
            return
        else:
            mirrorlist = ms.get_mirrorlist(mirrors, include_country=include_country, cmd=cmd)
            if mirrorlist is None:
                sys.exit('error: no mirrors found')
    except MirrorStatusError as e:
        sys.exit('error: {}\n'.format(e.msg))

    if options.save:
        try:
            with open(options.save, 'w') as f:
                f.write(mirrorlist)
        except IOError as e:
            sys.exit('error: {}\n'.format(e.strerror))
    else:
        print(mirrorlist)


def run_main(args=None, **kwargs):
    try:
        main(args, **kwargs)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_main(configure_logging=True)
