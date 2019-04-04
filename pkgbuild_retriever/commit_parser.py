def get_pkgbuild_location(payload):
    pkgbuild = [x for x in payload['commits'][0]['modified'] if x.endswith("PKGBUILD")]
    if len(pkgbuild) == 0:
        return None

    return pkgbuild[0]


def get_full_name(payload):
    return payload['repository']['full_name']
