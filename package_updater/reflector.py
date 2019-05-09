#!/usr/bin/env python3

# Copyright (C) 2012-2019  Xyne
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

import calendar
import http.client
import json
import queue
import socket
import threading
import time
import urllib.error
import urllib.request

URL = 'https://www.archlinux.org/mirrors/status/json/'

PARSE_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

DB_SUBPATH = 'core/os/x86_64/core.db'
MIRROR_URL_FORMAT = '{0}{1}/os/{2}'

DEFAULT_CONNECTION_TIMEOUT = 5
DEFAULT_CACHE_TIMEOUT = 300
DEFAULT_N_THREADS = 5


def sort(mirrors, n_threads=DEFAULT_N_THREADS):
    """
    Sort mirrors by different criteria.
    """
    # Ensure that "mirrors" is a list that can be sorted.
    if not isinstance(mirrors, list):
        mirrors = list(mirrors)

    rates = rate(mirrors, n_threads=n_threads)
    mirrors = sorted(mirrors, key=lambda m: rates[m['url']], reverse=True)

    yield from mirrors


def rate_http(db_url, connection_timeout=DEFAULT_CONNECTION_TIMEOUT):
    """
    Download a database via any protocol supported by urlopen and return the time
    and rate of the download.
    """
    req = urllib.request.Request(url=db_url)
    try:
        with urllib.request.urlopen(req, None, connection_timeout) as f:
            t0 = time.time()
            size = len(f.read())
            dt = time.time() - t0
        r = size / (dt)
        return dt, r
    except (OSError, urllib.error.HTTPError, http.client.HTTPException):
        return 0, 0


def rate(mirrors, n_threads=DEFAULT_N_THREADS, connection_timeout=DEFAULT_CONNECTION_TIMEOUT):
    """
    Rate mirrors by timing the download the core repo's database for each one.
    """
    # Ensure that mirrors is not a generator so that its length can be determined.
    if not isinstance(mirrors, tuple):
        mirrors = tuple(mirrors)

    if not mirrors:
        return None

    # At least 1 thread and not more than the number of mirrors.
    n_threads = max(1, min(n_threads, len(mirrors)))

    # URL input queue.
    q_in = queue.Queue()
    # URL, elapsed time and rate output queue.
    q_out = queue.Queue()

    def worker():
        while True:
            # To stop a thread, an integer will be inserted in the input queue. Each
            # thread will increment it and re-insert it until it equals the
            # threadcount. After encountering the integer, the thread exits the loop.
            url = q_in.get()

            if isinstance(url, int):
                if url < n_threads:
                    q_in.put(url + 1)

            else:
                db_url = url + DB_SUBPATH
                dt, r = rate_http(db_url, connection_timeout)
                q_out.put((url, dt, r))

            q_in.task_done()

    workers = tuple(threading.Thread(target=worker) for _ in range(n_threads))
    for w in workers:
        w.daemon = True
        w.start()

    for m in mirrors:
        url = m['url']
        q_in.put(url)

    # To exit the threads.
    q_in.put(0)
    q_in.join()

    # Loop over the mirrors just to ensure that we get the rate for each mirror.
    # The value in the loop does not (necessarily) correspond to the mirror.
    rates = dict()
    for _ in mirrors:
        url, dt, r = q_out.get()
        rates[url] = r
        q_out.task_done()

    return rates


def format_last_sync(mirrors):
    """
    Parse and format the "last_sync" field.
    """
    for m in mirrors:
        last_sync = calendar.timegm(time.strptime(m['last_sync'], PARSE_TIME_FORMAT))
        m.update(last_sync=last_sync)
        yield m


def filter_mirrors(mirrors, countries):
    # Filter unsynced mirrors.
    mirrors = (m for m in mirrors if m['last_sync'])

    # Parse the last sync time.
    mirrors = format_last_sync(mirrors)

    # Filter by countries.
    mirrors = (
        m for m in mirrors
        if m['country'].upper() in countries
           or m['country_code'].upper() in countries
    )

    # Filter by protocols.
    mirrors = (m for m in mirrors if m['protocol'] in ["https"])

    # Filter by age. The age is given in hours and converted to seconds. Servers
    # with a last refresh older than the age are omitted.
    t = time.time()
    a = 12 * 60 ** 2
    mirrors = (m for m in mirrors if (m['last_sync'] + a) >= t)

    yield from mirrors


def get_mirrorstatus(connection_timeout=DEFAULT_CONNECTION_TIMEOUT):
    """
    Retrieve the mirror status JSON object.
    """
    try:
        with urllib.request.urlopen(URL, None, connection_timeout) as h:
            obj = json.loads(h.read().decode())

        return obj
    except (IOError, urllib.error.URLError, socket.timeout) as e:
        raise MirrorStatusError(str(e))


class MirrorStatusError(Exception):
    """
    Common base exception raised by this module.
    """
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def find_best_mirror(countries):
    mirrors = get_mirrorstatus()
    mirrors = filter_mirrors(mirrors['urls'], countries)
    mirrors = sort(mirrors)
    mirror = next(mirrors)
    return MIRROR_URL_FORMAT.format(mirror['url'], '$repo', '$arch')
