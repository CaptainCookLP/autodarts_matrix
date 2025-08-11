"""Utilities for authenticating against the AutoDarts Keycloak server.

This module provides :class:`AutodartsKeycloakClient`, a small wrapper around
``python-keycloak`` that periodically refreshes the access token in a
background thread.  Only the minimal feature set required by this repository is
implemented.  All networking is handled by ``python-keycloak``.
"""

from datetime import datetime, timedelta
from time import sleep
import threading

from keycloak import KeycloakOpenID


class AutodartsKeycloakClient:
    """Maintain an access token for the AutoDarts API.

    Parameters are passed via keyword-only arguments to make call sites
    self-documenting.  After construction the client immediately requests an
    access token and starts tracking its expiry time.  :meth:`start` can be used
    to spawn a thread that keeps the token fresh.
    """

    token_lifetime_fraction = 0.9
    tick: int = 3
    run: bool = True
    username: str = None
    password: str = None
    debug: bool = False
    kc: KeycloakOpenID = None
    access_token: str = None
    refresh_token: str = None
    user_id: str = None
    expires_at: datetime = None
    refresh_expires_at: datetime = None
    t: threading.Thread = None

    def __init__(
        self,
        *,
        username: str,
        password: str,
        client_id: str,
        client_secret: str = None,
        debug: bool = False,
    ) -> None:
        """Create a new client and retrieve an initial access token."""

        self.kc = KeycloakOpenID(
            server_url="https://login.autodarts.io",
            client_id=client_id,
            client_secret_key=client_secret,
            realm_name="autodarts",
            verify=True,
        )
        self.username = username
        self.password = password
        self.debug = debug

        self.__get_token()
        self.user_id = self.kc.userinfo(self.access_token)["sub"]

    def __set_token(self, token: dict) -> None:
        """Persist token information and calculate expiry timestamps."""

        self.access_token = token["access_token"]
        self.refresh_token = token["refresh_token"]
        self.expires_at = datetime.now() + timedelta(
            seconds=int(self.token_lifetime_fraction * token["expires_in"])
        )
        self.refresh_expires_at = datetime.now() + timedelta(
            seconds=int(self.token_lifetime_fraction * token["refresh_expires_in"])
        )

    def __get_token(self) -> None:
        """Retrieve a new access/refresh token pair."""

        self.__set_token(self.kc.token(self.username, self.password))
        if self.debug:
            print("Getting token", self.expires_at, self.refresh_expires_at)

    def __refresh_token(self) -> None:
        """Refresh the access token using the current refresh token."""

        self.__set_token(self.kc.refresh_token(self.refresh_token))
        if self.debug:
            print("Refreshing token", self.expires_at, self.refresh_expires_at)

    def _refresh_loop(self) -> None:
        """Background worker keeping the token valid."""

        while self.run:
            try:
                if not self.access_token:
                    self.__get_token()

                now = datetime.now()
                if self.expires_at < now:
                    if now < self.refresh_expires_at:
                        self.__refresh_token()
                    else:
                        self.__get_token()
            except Exception:
                self.access_token = None
                print("Receive Token failed")

            sleep(self.tick)

    def start(self) -> threading.Thread:
        """Start the background refresh thread."""

        self.t = threading.Thread(target=self._refresh_loop, name="autodarts-tokenizer")
        self.t.start()
        return self.t

    def stop(self) -> None:
        """Stop the background refresh thread."""

        self.run = False
        self.t.join()
        print(self.t.name + " EXIT")



