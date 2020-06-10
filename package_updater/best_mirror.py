import os

from reflector import find_best_mirror

NEXT_FUNC = os.environ.get('NEXT_FUNC')


def _get_all_repo_mirrors(best_mirror, repos):
    """Reference each repository with the best mirror found.

    Args:
        best_mirror (str): The best mirror found to search the package list with
        repos (list): List of repositories to search

    Returns:
        list: A collection of mirrors for each repo as a URL
    """
    print(f"Using {best_mirror} for the following repos: {repos}")

    mirrors = []
    for repo in repos:
        mirror = best_mirror \
                     .replace('Server = ', '') \
                     .replace('$arch', 'x86_64') \
                     .replace('$repo', repo) + f'/{repo}.db'
        mirrors.append({'repo': repo, 'mirror': mirror})

    return mirrors


def get_best_mirror(countries, repos):
    best_mirror = find_best_mirror(countries)
    mirrors = _get_all_repo_mirrors(best_mirror, repos)
    return mirrors
