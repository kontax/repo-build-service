import lzma
import gzip
import requests

from io import BytesIO
from tarfile import TarFile


def _extract_archive_from_stream(stream):
    """Extracts a TarFile from the byte stream specified.

    The byte-stream should be a downloaded LZMA or gzip compressed tarfile.

    Args:
        stream (BytesIO): The byte stream containing the compressed archive.

    Returns:
        TarFile: The decompressed TarFile object
    """
    try:
        tar = TarFile(fileobj=gzip.open(stream), mode='r')
    except OSError:
        stream.seek(0)
        tar = TarFile(fileobj=lzma.open(stream), mode='r')
    return tar


def _extract_pkg_name(tar, files):
    """
    Extracts a list of package names from the tarfile and list of paths for each 'desc' file
    within the archive.

    Args:
        tar (TarFile): The archive containing package details
        files (list): A list of paths to every 'desc' file within the archive

    Returns:
        list: A list of strings containing the package names for each package within the archive
    """
    filenames = []

    for desc_file in files:

        # Extract and read the "desc" file
        desc = tar.extractfile(desc_file.path).read().decode('utf-8')

        # Each property is split out by two newlines
        desc_list = list(filter(None, desc.split('\n\n')))

        desc_dict = {}
        for x in desc_list:

            # The header is the first line, and is surrounded with % (eg. %NAME%)
            splits = x.split('\n')
            key = splits[0]

            # There can be multiple values per header
            value = splits[1:]
            desc_dict[key] = value

        # We only want the list of names, which should only have one value
        filenames.append(desc_dict['%NAME%'][0])

    return filenames


def get_packages(uri):
    """Gets a collection of packages contained within the repository URL specified.

    Args:
        uri (str): The full path of the package database location.
    
    Returns:
        list: A collection of package names within the repository
    """

    # Pull the DB file from the URI
    print(f"Pulling package database from {uri}")
    stream = BytesIO(requests.get(uri).content)

    # Decompress and unpack the DB file
    print("Decompressing downloaded DB file")
    tar = _extract_archive_from_stream(stream)

    # Get a list of all "desc" files within the archive
    print("Extracting files...")
    files = [x for x in tar.getmembers() if x.isfile() and x.name.endswith("desc")]
    print(f"{len(files)} desc files found")

    # Extract the package names from their desc files
    filenames = _extract_pkg_name(tar, files)

    return filenames
