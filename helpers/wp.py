import asyncio
import os
from signal import SIGINT

from webwhatsapi.async_driver import WhatsAPIDriverAsync
from webwhatsapi.objects.message import Message

from helpers import check_filter, get_links
from helpers.DB import DB
from helpers.telegram import Telegram


class Whatsapp:
    def __init__(self, loop):
        self._loop = loop
        self._db = DB()
        self._driver = None
        self._tg = Telegram()
        self.is_cancelled = False
        self._config_dir = os.path.join(".", "firefox_cache")
        if not os.path.exists(self._config_dir):
            os.makedirs(self._config_dir)

    async def make(self):
        self._db.save_json()
        await self.sleep(10)
        self._driver = WhatsAPIDriverAsync(
            loadstyles=True,
            loop=self._loop,
            profile=self._config_dir,
            client="remote",
            command_executor=os.environ["SELENIUM"],
        )

    async def sleep(self, sleep_time):
        await asyncio.sleep(sleep_time, loop=self._loop)

    async def start(self):
        await self.make()
        self._loop.add_signal_handler(SIGINT, self.stop)
        task1 = self.monitor_messages()
        await asyncio.wait([task1], loop=self._loop)

    async def monitor_messages(self):
        print("Connecting...")
        await self._driver.connect()

        # get qr code
        print("Checking for login...")
        login_status = await self._driver.wait_for_login()
        if not login_status:
            filepath = await self._driver.get_qr()
            print("The QR is at", filepath.replace("/tmp", "qrs"))

        # wait for user to login
        tries = 0
        while not login_status:
            print("Wait for login...")
            login_status = await self._driver.wait_for_login()
            if tries > 30:
                raise Exception("Couldn't login")
            else:
                tries += 1

        await self._driver.save_firefox_profile(remove_old=True)
        self._db.add_json()

        while True:
            try:
                print("Checking for more messages, status", await self._driver.get_status())

                for cnt in await self.get_unread_messages():
                    if self.is_cancelled:
                        break

                    for message in cnt.messages:
                        if isinstance(message, Message):
                            shit = message.get_js_obj()
                            name = message.sender.push_name
                            if name is None:
                                name = message.sender.get_safe_name()
                            chat = shit['chat']['contact']['formattedName']

                            # By default, message should be sent
                            newline = "\n"
                            if links := get_links(message.content) and not check_filter(message.content):
                                try:
                                    self._tg.log_link(chat, name, f"{newline.join(links)}\n\n---\n\n{message.content}")
                                except Exception as e:
                                    self._tg.log_message(
                                        f"New invite link failed to deliver!, Check phone asap | error log_message = {e}"
                                    )

            except Exception as e:
                print(e)
                continue

            await self.sleep(3)

    def stop(self, *args, **kwargs):
        self.is_cancelled = True

    async def get_unread_messages(self):
        cnts = []
        for contact in await self._driver.get_unread():
            print(f"Found Contact: {contact}")
            cnts.append(contact)
        return cnts
