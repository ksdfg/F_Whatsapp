from re import compile, sub
from typing import Set

from decouple import config, Csv


def check_filter(message: str) -> bool:
    """
    Function to check if a message is to be filtered out or not
    :param message: Message body to be checked
    :return: True if it is to be filtered, else false
    """
    # Check if any filter mode is enabled
    filter_mode = config('Filter-Mode', None)

    if filter_mode:
        # If we have any filters, assume message shouldn't be sent
        filter_triggered = True

        if filter_mode == 'blacklist':
            # Retrieve a comma-separate list of disallowed text
            disallowed_text = config('blacklist', cast=Csv(cast=lambda x: x.lower(), strip=' %*'))
            for text in disallowed_text:
                # If any of the disallowed phrases are in the links, do not send the message
                if text in message.lower():
                    filter_triggered = True
                    break
            else:
                filter_triggered = False

        else:
            # Retrieve a comma-separate list of disallowed text
            allowed_text = config('whitelist', cast=Csv(cast=lambda x: x.lower(), strip=' %*'))
            for text in allowed_text:
                # If any of the allowed phrases are in the message content, send the message
                if text in message.lower():
                    filter_triggered = False
                    break
    else:
        filter_triggered = False  # False if there are no filters

    return filter_triggered


def get_links(message: str) -> Set[str]:
    """
    Fetch all meeting links in a message body
    :param message: message body
    :return: set of all the meeting links in the message body
    """
    url_regex = compile(r"(?:[a-zA-Z]|[0-9]|[$-_@.&+%]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
    links_to_check = config('Links-to-Check', cast=Csv(cast=lambda x: x.lower(), strip=' %*'))
    safe_link = compile(r"^http[s]?://.+")
    meeting_regex = compile(f"^http[s]?://(?!www.google.com).*({'|'.join(links_to_check)}).+")

    links = set()
    for url in url_regex.findall(message):
        url = sub(r"(<.+>.*|<|>)", "", url)
        if not safe_link.match(url.lower()):
            url = "https://" + url
        if meeting_regex.match(url.lower()):
            links.add(url)

    return links
