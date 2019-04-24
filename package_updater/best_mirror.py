import os
import sys
from io import StringIO

import Reflector as Reflector

NEXT_FUNC = os.environ.get('NEXT_FUNC')


def _get_best_mirror(countries, refl):
    """Gets the best mirror for downloading the official package list from

    Args:
        countries (list): The list of 2 letter country codes to search
        refl (Reflector): The class used to compare Arch mirrors

    Returns:
        str: A URL for the best mirror found
    """
    print(f"Pulling best mirrors using Reflector")

    # Save the stdout result to a string
    old_stdout = sys.stdout
    result = StringIO()
    sys.stdout = result

    # Parse the options for reflector
    options = ["-p", "http", "-f", "1", "--sort", "rate", "--age", "12"]
    for country in countries:
        options.append("-c")
        options.append(country)
    refl.run_main(options)

    # Restore stdout
    sys.stdout = old_stdout
    best_mirror = [x for x in result.getvalue().split('\n') if x.startswith('Server = ')][0]
    return best_mirror


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
        mirrors.append(mirror)

    return mirrors


def get_best_mirror(countries, repos):
    best_mirror = _get_best_mirror(countries, Reflector)
    mirrors = _get_all_repo_mirrors(best_mirror, repos)
    return mirrors
