import lzma
import gzip
import urllib.request

from io import BytesIO
from tarfile import TarFile
from zstandard import ZstdDecompressor


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
        try:
            tar = TarFile(fileobj=lzma.open(stream), mode='r')
        except lzma.LZMAError:
            stream.seek(0)
            d = ZstdDecompressor()
            decompressed = BytesIO()
            d.copy_stream(stream, decompressed)
            decompressed.seek(0)
            tar = TarFile(fileobj=decompressed, mode='r')

    return tar


def _extract_pkg_name(tar, files):
    """
    Extracts a list of package names from the tarfile and list of paths for
    each 'desc' file within the archive.

    Args:
        tar (TarFile): The archive containing package details
        files (list): A list of paths to every 'desc' file within the archive

    Returns:
        list: A list of strings containing the package names for each package
              within the archive
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


def get_packages(repo):
    """Gets a collection of packages contained within the repository URL
    specified.

    Args:
        repo (dict): The mirror name and URI to download from, in the format:
                     { 'repo': `repo_name`, 'mirror': `uri` }

    Returns:
        dict: The repo name with a collection of package names
    """

    # Pull the DB file from the URI
    print(f"Pulling package database from {repo['mirror']}")
    with urllib.request.urlopen(repo['mirror']) as h:
        stream = BytesIO(h.read())

    # Decompress and unpack the DB file
    print("Decompressing downloaded DB file")
    tar = _extract_archive_from_stream(stream)

    # Get a list of all "desc" files within the archive
    print("Extracting files...")
    files = [x for x in tar.getmembers() if x.isfile() and x.name.endswith("desc")]
    print(f"{len(files)} desc files found")

    # Extract the package names from their desc files
    filenames = _extract_pkg_name(tar, files)

    return {'repo': repo['repo'], 'packages': filenames}
