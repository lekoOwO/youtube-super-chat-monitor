"""
YouTube Super Chat Monitor
Copyright (C) 2020 Remington Creative

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from threading import Timer
from .event import YTSCEvent

import google_auth_oauthlib.flow as oauth
import googleapiclient.discovery
import googleapiclient.errors

import os
import sqlite3

class YTSCMonitor:
    """
    Monitors YouTube Super Chat events and triggers an update function if a
    new Super Chat is received.
    """

    # youtube client
    __youtube = None

    # update function
    __update = None

    # autofetch timer
    __autofetch_timer = None

    def __init__(self, client_secrets_file, progress_db, update_function=None, init=True):
        """
        Creates a new super chat monitor from a client secrets file
        :param client_secrets_file: the client secrets file
        :param update_function: the function to call when a new Super Chat is
        received
        """

        # api context
        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        api_service_name = "youtube"
        api_version = "v3"

        # instantiate credentials
        flow = oauth.InstalledAppFlow.from_client_secrets_file(
            client_secrets_file=client_secrets_file,
            scopes=scopes,
        )

        credentials = flow.run_console()

        # get youtube client
        self.__youtube = googleapiclient.discovery.build(
            api_service_name,
            api_version,
            credentials=credentials
        )

        # fetch the initial list of super chats
        if init:
            self.fetch()

        # set update function (must come after initial fetch)
        self.__update = update_function

        # progress sqlite3 database
        self.__progress_db = progress_db
        with sqlite3.connect(progress_db) as con:
            con.execute("CREATE TABLE IF NOT EXISTS superchats (id TEXT)")
            con.commit()

    def _is_fetched(self, id, db_connection):
        """
        Checks if a super chat has been fetched
        :param id: the id of the super chat
        :return: true if the super chat has been fetched, false otherwise
        """
        query = f"SELECT count(*) FROM superchats WHERE id = ?"
        cursor = db_connection.execute(query, (id,))
        fetched = cursor.fetchone()[0]
        return fetched == 1

    def fetch(self):
        """
        Fetches a new list of super chats from the YouTube client
        """

        buffer = []
        with sqlite3.connect(self.__progress_db) as con:
            token = None
            is_finished = False
            while True:
                is_finished = False

                request = self.__youtube.superChatEvents().list(
                    part = "snippet",
                    maxResults = 50,
                    pageToken=token,
                    hl="zh-TW"
                )

                response = request.execute()
                token = response["nextPageToken"]
                if len(response['items']) == 0:
                    break

                # iterate through super chats
                buffer = []
                for super_chat_json in response['items']:
                    if self._is_fetched(super_chat_json['id'], con):
                        is_finished = True
                        continue

                    super_chat_event = YTSCEvent(super_chat_json)
                    buffer.append(super_chat_event.get_id())
                    self.__update(super_chat_event)
                if len(buffer) > 0:
                    cur = con.cursor()
                    for x in buffer:
                        cur.execute(
                            f"INSERT INTO superchats VALUES (?)",
                            (x,)
                        )
                if is_finished:
                    break
            con.commit()

    def start(self, interval):
        """
        Begins automatically fetching and monitoring new super chats
        at a specified interval
        :param interval - the amount of time in seconds between fetches
        """
        self.__autofetch_timer = self.__AutoFetchTimer(interval, self.fetch)
        self.__autofetch_timer.start()
        print("Started monitoring Super Chats!")

    def stop(self):
        """
        Stops automatically fetching and monitoring new super chats
        """
        if self.__autofetch_timer is not None:
            self.__autofetch_timer.cancel()
        print("Stopped monitoring Super Chats!")

    class __AutoFetchTimer:
        """
        Repeating timer for autofetch functionality
        """

        def __init__(self, seconds, target):
            self._should_continue = False
            self.is_running = False
            self.seconds = seconds
            self.target = target
            self.thread = None

        def _handle_target(self):
            self.is_running = True
            self.target()
            self.is_running = False
            self._start_timer()

        def _start_timer(self):
            if self._should_continue:
                self.thread = Timer(self.seconds, self._handle_target)
                self.thread.start()

        def start(self):
            if not self._should_continue and not self.is_running:
                self._should_continue = True
                self._start_timer()

        def cancel(self):
            if self.thread is not None:
                self._should_continue = False
            self.thread.cancel()
