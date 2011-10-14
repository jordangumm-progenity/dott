"""
Contains the protocols, commands, and client factory needed for the server
to service the MUD proxy.
"""
from twisted.protocols import amp
from twisted.internet import protocol
import settings

class AmpServerFactory(protocol.ServerFactory):
    """
    This factory creates new ProxyAMP protocol instances to use for accepting
    connections from TCPServer.
    """
    def __init__(self, server):
        """
        :attr ProxyService _mud_service: The global :class:`MudService` instance.
        :attr ProxyAMP protocol: The protocol the factory creates instances of.
        """
        self._mud_service = server
        self.protocol = ProxyAMP

    def buildProtocol(self, addr):
        """
        Creates new ProxyAMP instances for the MUD server (MudService) to
        accept connections from the proxy with. This method also sets
        the :attr:`proxyamp` attribute on the :class:`MudService` instance,
        which is used for piping input fron MUD server to the proxy.

        :rtype: ProxyAMP
        :returns: A newly minted ProxyAMP instance. MudService uses this to
            accept connections from ProxyService.
        """
        self._mud_service.proxyamp = ProxyAMP()
        self._mud_service.proxyamp.factory = self
        return self._mud_service.proxyamp

class AmpClientFactory(protocol.ReconnectingClientFactory):
    """
    This factory creates new ProxyAMP protocol instances to use to connect
    to the MUD server. It also maintains the :attr:`proxyamp` attribute
    on the :class:`ProxyService` instance, which is used for piping input
    fron Telnet to the MUD server.
    """
    # Initial reconnect delay in seconds.
    initialDelay = 1
    maxDelay = 1

    def __init__(self, server):
        """
        :attr ProxyService server: The global :class:`ProxyService` instance.
        """
        self._proxy_service = server

    def startedConnecting(self, connector):
        """
        Called when starting to try to connect to the MUD server.
        """
        print 'Attempting to connect to MUD server...'

    def buildProtocol(self, addr):
        """
        Pops out ProxyAMP instances. Only one should ever be in use at a
        time. This method also sets the :attr:`proxyamp` attribute
        on the :class:`ProxyService` instance, which is used for piping input
        from the proxy to the MUD server.

        :rtype: ProxyAMP
        :returns: A newly minted ProxyAMP instance. ProxyService uses this
            to connect to the MUD server (MudService).
        """
        # Bring reconnect delay back down to initial value, in case the AMP
        # connection is broken later on.
        self.resetDelay()
        # Update the MudService instance's proxyamp attribute to be the
        # currently active ProxyAMP() instance, which we can communicate
        # to the MUD server with.
        self._proxy_service.proxyamp = ProxyAMP()
        self._proxy_service.proxyamp.factory = self
        return self._proxy_service.proxyamp

    def clientConnectionLost(self, connector, reason):
        """
        Called when the AMP connection to the MUD server is lost.
        """
        print 'Lost connection.  Reason:', reason
        protocol.ReconnectingClientFactory.clientConnectionLost(
            self,
            connector,
            reason
        )

    def clientConnectionFailed(self, connector, reason):
        """
        Called when an AMP connection attempt to the MUD server fails.
        """
        print 'Proxy->MUD server Connection failed. Reason:', reason
        protocol.ReconnectingClientFactory.clientConnectionFailed(
            self,
            connector,
            reason
        )

#
## MUD Server to Proxy commands.
#

class DisconnectSessionsOnObjectCmd(amp.Command):
    """
    AMP command for disconnecting all sessions that control the specified
    object. Used in the voluntary 'quit' command and forceful '@boot'.
    """
    arguments = [
        ('object_id', amp.Unicode()),
    ]
    response = [
        ('num_sessions_closed', amp.Integer()),
    ]


class WhoConnectedCmd(amp.Command):
    """
    Command for asking the proxy for which accounts are connected.
    """
    arguments = []
    response = [
        ('accounts', amp.ListOf(amp.Unicode())),
    ]

#
## Proxy to MUD Server commands.
#

class NotifyFirstSessionConnectedOnObjectCmd(amp.Command):
    """
    Sent to an object upon a controlling PlayerAccount connecting via
    a Session on the proxy. This is only sent with the first connection. Any
    subsequent duplicate connections (IE: player connects with three different
    clients at the same time) will not trigger the event repeatedly.
    """
    arguments = [
        ('object_id', amp.Unicode()),
    ]
    response = []

class CreatePlayerObjectCmd(amp.Command):
    """
    AMP command for creating a new PlayerObject for a new PlayerAccount.
    Called by the proxy during character creation.
    """
    arguments = [
        ('username', amp.Unicode()),
    ]
    response = [
        ('object_id', amp.Unicode()),
    ]


class SendThroughObjectCmd(amp.Command):
    """
    AMP command for sending player input from the proxy to the MUD server.
    """
    arguments = [
        ('object_id', amp.Unicode()),
        ('input', amp.Unicode()),
    ]
    response = []


class EmitToObjectCmd(amp.Command):
    """
    AMP command for sending output to a player connected on the proxy.
    """
    arguments = [
        ('object_id', amp.Unicode()),
        ('message', amp.Unicode()),
    ]
    response = []


class TriggerAtSessionDisconnectForObjectCmd(amp.Command):
    """
    When a Session disconnects that was controlling an object, this AMP
    command asks the MUD Server to run said object's
    ``after_session_disconnect_event()`` method.
    """
    arguments = [
        ('object_id', amp.Unicode()),
    ]
    response = []


class ProxyAMP(amp.AMP):
    """
    This is the protocol that the MUD server and the proxy server
    communicate to each other with. AMP is a bi-directional protocol, so
    both the proxy and the MUD use the same commands and protocol.

    Each valid command has a public method on this class, and specifies
    a responder, which is an amp.Command sub-class. The responder class
    dictates data types for arguments and response.
    """

    #
    ## MUD Server to Proxy commands.
    #

    def emit_to_object_command(self, object_id, message):
        """
        Pipe output to a player connected on the proxy, who controls the
        specified object (if any).

        :param str object_id: The object whose session to emit to.
        :param str message: The message to emit to any sessions on the object.
        """
        # The root ProxyService instance.
        service = self.factory._proxy_service
        # Emit to the any Session objects responsible for object_id.
        service.session_manager.emit_to_object(object_id, message)

        return {}
    EmitToObjectCmd.responder(
        emit_to_object_command
    )

    def who_connected_command(self):
        """
        Asks the proxy for a list of connected/authenticated accounts.
        """
        # The root ProxyService instance.
        service = self.factory._proxy_service
        sessions = service.session_manager.get_sessions()

        accounts = []
        for session in sessions:
            accounts.append(session.account.username)

        return {
            'accounts': accounts,
        }
    WhoConnectedCmd.responder(
        who_connected_command
    )

    def disconnect_sessions_on_object_command(self, object_id):
        """
        Given an object ID on the MUD Server side, tells the Proxy to disconnect
        any sessions controlling the object with the given ``object_id``.

        :param str object_id: Sessions that are controlling this object will
            be disconnected.
        """
        service = self.factory._proxy_service
        session_mgr = service.session_manager

        sessions = session_mgr.get_sessions_for_object_id(object_id)
        disco_counter = 0
        for session in sessions:
            session.disconnect_client()
            disco_counter += 1

        return {
            'num_sessions_closed': disco_counter,
        }
    DisconnectSessionsOnObjectCmd.responder(
        disconnect_sessions_on_object_command
    )

    #
    ## Proxy to MUD Server commands.
    #

    def send_through_object_command(self, object_id, input):
        """
        Handles sending the input through the given object, and ultimately
        the command handler.

        :param str object_id: The object ID to send this command as.
        :param str input: The command to send to the command handler through
            the object.
        """
        # The root MudService instance.
        service = self.factory._mud_service
        # Get a reference to the object that will send the command.
        obj = service.object_store.get_object(object_id)
        # Send the command to the command handler as this object.
        obj.execute_command(input)

        return {}
    SendThroughObjectCmd.responder(
        send_through_object_command
    )

    def create_player_object_command(self, username):
        """
        Creates a PlayerObject to match a newly created PlayerAccount.

        :param str username: The username of the PlayerAccount.
        """
        # The root MudService instance.
        service = self.factory._mud_service

        # Create the new PlayerObject.
        player_obj = service.object_store.create_object(
            'src.game.parents.base_objects.player.PlayerObject',
            name=username,
            original_account_id=username,
            controlled_by_account_id=username,
            location_id=settings.NEW_PLAYER_LOCATION_ID,
        )

        # The object's ID gets returned so the account creation code can
        # set the account to control the new object.
        return {
            'object_id': player_obj._id,
        }
    CreatePlayerObjectCmd.responder(
        create_player_object_command
    )

    def trigger_after_session_disconnect_event_object_command(self, object_id):
        """
        Triggers an object's ``after_session_disconnect_event()`` method when
        all sessions disconnect from an object.

        :param str object_id: The ID of the object who lost its last
            controlling session to disconnection.
        """
        # The root MudService instance.
        service = self.factory._mud_service
        # Get a reference to the object that is disconnecting.
        obj = service.object_store.get_object(object_id)
        # Fire the event.
        obj.after_session_disconnect_event()

        return {}
    TriggerAtSessionDisconnectForObjectCmd.responder(
        trigger_after_session_disconnect_event_object_command
    )

    def notify_first_session_connected_on_object_command(self, object_id):
        """
        Sent to an object upon a controlling PlayerAccount connecting via
        a Session on the proxy. This is only sent with the first connection.
        Any subsequent duplicate connections (IE: player connects with three
        different clients at the same time) will not trigger the event
        repeatedly.

        :param str object_id: The object ID to trigger the
            ``after_session_connect_event`` for.
        """
        # The root MudService instance.
        service = self.factory._mud_service
        # Get a reference to the object that will send the command.
        obj = service.object_store.get_object(object_id)
        # Fire off the connection event.
        obj.after_session_connect_event()

        return {}
    NotifyFirstSessionConnectedOnObjectCmd.responder(
        notify_first_session_connected_on_object_command
    )