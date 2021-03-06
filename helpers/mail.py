import logging
from email import message_from_bytes
from email.header import decode_header
from imaplib import IMAP4_SSL, IMAP4
from re import sub, DOTALL
from time import sleep
from traceback import print_exc
from typing import List, Set

from decouple import config, Csv

from helpers import check_filter, get_links
from helpers.telegram import Telegram


class Email:
    """
    Class to represent a single email
    """

    def __init__(self, mail_bytes: bytes):
        """
        Initialize the object
        :param mail_bytes: bytes object representing the mail
        """
        email = message_from_bytes(mail_bytes)

        # get sender
        self.sender, _ = decode_header(email.get('From'))[0]
        if isinstance(self.sender, bytes):
            self.sender = self.sender.decode('utf-8')

        # get subject
        self.subject = decode_header(email['Subject'])[0][0]
        if isinstance(self.subject, bytes):
            self.subject = self.subject.decode('utf-8')

        # get message body
        if email.is_multipart():
            body = ""
            for part in email.walk():
                if "text" in part.get_content_type():
                    try:
                        body += part.get_payload(decode=True).decode('utf-8')
                    except:
                        continue
        else:
            body = email.get_payload(decode=True).decode('utf-8')

        # check if message is to be filtered
        if check_filter(body) or check_filter(self.subject):
            self.links = set()
        else:
            # remove all quoted messages and footers to get just the message content
            body = sub(
                r"On (Mon|Tue|Wed|Thu|Fri|Sat|Sun), (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d+, \d+ at \d+:\d+ [AP]M [\w\s]+ <.+@.+> wrote:.*",
                "",
                body,
                flags=DOTALL,
            )
            body = body.split("--")[0]

            # get all needed links from body
            self.links: Set[str] = get_links(body)


class MailService:
    """
    Class to represent a mail _service
    """

    def __init__(self):
        self._tg = Telegram()
        self._links_to_check = config('Links-to-Check', cast=Csv(strip=' %*'))

        self._service = IMAP4_SSL(config('Email-IMAP'))
        self._service.login(config('Email-ID'), config('Email-Password'))  # login

    def _get_new_meetings(self) -> List[Email]:
        """
        Fetch all the unread emails
        :return: List of all unread email objects
        """
        # fetch unread emails
        try:
            print("fetching unread mails")
            self._service.select('inbox')
            status, mail_ids = self._service.search(None, '(UNSEEN)')

            # format all mails into Email objects
            mails = []  # list of all mails to be logged
            all_mails = mail_ids[0].decode('utf-8').split()  # list of all unread mails
            for n, mail_id in enumerate(all_mails):
                # fetch the mail
                print(f"fetching mail {n+1}/{len(all_mails)}")
                status, mail_content = self._service.fetch(mail_id, '(RFC822)')
                if status != "OK":
                    continue

                for content in mail_content:
                    if isinstance(content, tuple):
                        email = Email(content[1])
                        if email.links:
                            mails.append(email)
                        else:
                            # mark the mail as unread
                            self._service.store(mail_id, '-FLAGS', r'\SEEN')

            return mails

        except IMAP4.abort as e:
            logging.error(e)
            # close existing service and start new one
            self._service.close()
            self._service = IMAP4_SSL(config('Email-IMAP'))
            self._service.login(config('Email-ID'), config('Email-Password'))  # login

        except Exception as e:
            logging.error(e)
            return []

    def log_new_meetings(self):
        """
        Function to log all unread mails with meeting links to telegram channel
        """
        while True:
            mails = self._get_new_meetings()
            for n, email in enumerate(mails):
                try:
                    print(f"logging mail {n+1}/{len(mails)}")
                    response = self._tg.log_link(
                        email.sender.replace("<", "&lt;").replace(">", "&gt;"), email.subject, "\n\n".join(email.links)
                    )
                    if response.status != 200:
                        self._tg.log_message(
                            f"<b>New invite link failed to deliver!\nCheck mail asap</b>\n\n"
                            f"response status = <code>{response.status}</code>\n"
                            f"response data = <code>{response.data.decode('utf-8')}</code>\n"
                        )
                except Exception as e:
                    self._tg.log_message(
                        f"New invite link failed to deliver!\nCheck mail asap\n\nerror log_message = <code>{e}</code>"
                    )
                    print_exc()

            sleep(7)
