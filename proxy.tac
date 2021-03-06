"""
This module drives the proxy that sits in front of the MUD server. The proxy
is the only one of the two that handles Telnet connections from players.
It uses an auto-reconnect internet.TCPClient to speak to the MUD server
through the Twisted AMP protocol (a two-way async protocol).

The benefits are twofold:
  * Telnet handling is solely the domain of the proxy, and the actual MUD server
    itself is free to worry about more important things. Like the game.
  * The MUD can restart without interrupting player connections. As a result of
    this, we don't need to implement any crazy code reloading junk. We can
    just cold restart without many players even noticing.
"""

import time

from twisted.application import internet, service
from twisted.internet import reactor

import settings
from src.daemons.proxy.protocols.telnet import MudTelnetServerFactory
from src.daemons.proxy.sessions.session_manager import SessionManager
from src.accounts.account_store import AccountStore
from src.daemons.server.protocols.proxyamp import AmpClientFactory


class ProxyService(service.Service):
    """
    This is the main Service class that ties the proxy together. It listens
    for telnet connections and maintains a client connection to the MUD
    server over AMP.
    """

    def __init__(self):
        """
        :attr ProxyAMP proxyamp: The currently active ProxyAMP instance.
            This can be used to communicate with the MUD server through.
        """

        self.session_manager = SessionManager(self)
        self.account_store = AccountStore()
        # Check the DB, load accounts into RAM.
        self.account_store.prep_and_load()

        self.proxyamp = None

        self.start_time = time.time()

    def start_services(self, app_to_start):
        """
        Starts all of the TCP services.
        """
        self.service_collection = service.IServiceCollection(app_to_start)

        telnet_factory = MudTelnetServerFactory(self)

        print('\n' + '-' * 50)
        print(' Starting %s proxy server' % settings.GAME_NAME)
        print(' Version: %s' % settings.VERSION)
        print(' Listening for telnet connections on ports:')
        for port in settings.PROXY_LISTEN_PORTS:
            telnet_server = internet.TCPServer(port, telnet_factory)
            telnet_server.setName('dott_telnet_%s' % port)
            telnet_server.setServiceParent(self.service_collection)
            print('  * %s' % port)
        print('-'*50)

        amp_client = internet.TCPClient(
            settings.SERVER_AMP_HOST,
            settings.SERVER_AMP_PORT,
            AmpClientFactory(self)
        )
        amp_client.setName('dott_amp')
        amp_client.setServiceParent(self.service_collection)

    def shutdown(self):
        """
        Gracefully shuts down the service.
        """
        reactor.callLater(0, reactor.stop)

    def is_connected_to_mud_server(self):
        """
        Determines whether the proxy has connected to the MUD server.

        :rtype: boo
        :returns: ``True`` if the proxy has established a connection to the
            MUD server over AMP. ``False`` if not.
        """
        return self.proxyamp.transport is not None

# Putting it all together.
application = service.Application('dott_proxy')
mud_service = ProxyService()
mud_service.start_services(application)
