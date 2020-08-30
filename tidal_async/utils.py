
def snake_to_camel(attr):
    return "".join(c if i == 0 else c.capitalize() for i, c in enumerate(attr.split('_')))


async def cli_auth_url_getter(authorization_url):
    # raise NotImplemented
    # Test (bad) implementation, it's blocking and should be overwritten in code using this API
    print("Authorization prompt URL:", authorization_url)
    print("Paste this URL to your browser, login to Tidal when asked,\n"
          "copy URL from your browser after successful authentication (it will show Not found error)\n"
          "Paste it in prompt below")

    return input("Enter auth_url: ")


def parse_title(result, artists=None):
    # https://github.com/divadsn/tidal-telegram-bot/blob/master/tidalbot/utils.py#L60
    if artists and len(artists) > 1:
        title = result.name.strip()  # just in case

        # add featuring artists if not already
        if "(feat." not in title:
            title += f' (feat. {" & ".join([x.name for x in artists[1:]])})'

        return f'{title}{f" [{result.version}]" if result.version and result.version not in result.name else ""}'
    else:
        return f'{result.name}{f" ({result.version})" if result.version and result.version not in result.name else ""}'


try:
    from androguard.core.bytecodes.axml import ARSCParser

    from zipfile import ZipFile

    def extract_client_id(apk_file):
        with ZipFile(apk_file) as apk:
            with apk.open("resources.arsc") as res:
                return ARSCParser(res.read()).get_string("com.aspiro.tidal", "default_client_id")[1]

except ImportError:
    def extract_client_id(apk_file):
        raise
