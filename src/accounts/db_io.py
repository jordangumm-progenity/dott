"""
This module manages all I/O from the DB, and handles the population of the
AccountStore.
"""

from twisted.internet.defer import inlineCallbacks, returnValue

from src.accounts.account import PlayerAccount
from src.utils.db import txPGDictConnection, get_db_connection_kwargs


class DBManager(object):
    """
    This class serves as an abstraction layer between the AccountStore
    and the underlying database. It handles the loading of objects at
    server start time, and all CRUD operations on the DB side. DBManager is
    allowed to manipulate the self.store._objects dict.
    """

    # TODO: Add last_login_dtime column.

    # This is the base SELECT statement we'll use in a few methods for
    # retrieving one or all account rows. To retrieve a subset, tack on a
    # WHERE clause by string concatenation.
    BASE_ACCOUNT_SELECT = (
        "SELECT "
        "  id, username, currently_controlling_id, email, password, created_time "
        "  FROM dott_accounts"
    )

    def __init__(self, store, db_mode='production'):
        """
        :keyword AccountStore store: The account store this instance manages.
        :keyword str mode: Either 'test' or 'production'.
        """

        self.store = store
        self._db_mode = db_mode
        # This eventually contains a txpostgres Connection object, which is
        # where we can query.
        self._db = None

    @inlineCallbacks
    def prepare_and_load(self):
        """
        Prepares the store for duty, then loads all objects from the DB into
        the object store.
        """

        # Just in case this is a code reload.
        self.store._accounts = {}
        # Instantiate the connection to Postgres.
        self._db = txPGDictConnection()
        conn_info = get_db_connection_kwargs(db_mode=self._db_mode)
        yield self._db.connect(**conn_info)

    @inlineCallbacks
    def get_account_count(self):
        """
        :rtype: int
        :returns: A total count of active accounts.
        """

        results = yield self._db.runQuery("SELECT count(*) as count FROM dott_accounts")
        returnValue(results[0][0])

    @inlineCallbacks
    def get_account_by_id(self, account_id):
        """
        Given an account's ID, return a matching PlayerAccount instance.

        :param int account_id: The account's ID (pk).
        :rtype: PlayerAccount
        """

        modified_query = "{base_query} WHERE id=%s".format(
            base_query=self.BASE_ACCOUNT_SELECT
        )
        results = yield self._db.runQuery(modified_query, (account_id,))

        for row in results:
            returnValue(self.instantiate_account_from_row(row))
        else:
            returnValue(None)

    @inlineCallbacks
    def get_account_by_username(self, account_username):
        """
        Given an account's username, return a matching PlayerAccount instance.

        :param str account_username: The account's username.
        :rtype: PlayerAccount
        """

        modified_query = "{base_query} WHERE username ILIKE %s".format(
            base_query=self.BASE_ACCOUNT_SELECT
        )
        results = yield self._db.runQuery(modified_query, (account_username,))

        for row in results:
            returnValue(self.instantiate_account_from_row(row))
        else:
            returnValue(None)

    def instantiate_account_from_row(self, row):
        """
        Given a txpostgres row, return a PlayerAccount instance for it.

        :param row:
        :rtype: PlayerAccount
        :returns: The newly loaded player account.
        """

        # Instantiate the object, using the values from dict-based row.
        return PlayerAccount(account_store=self.store, **row)

    @inlineCallbacks
    def save_account(self, account):
        """
        Saves an account to the DB.

        :param PlayerAccount account: The account to save to the DB.
        """

        if not account.id:
            result = yield self._db.runQuery(
                "INSERT INTO dott_accounts"
                "  (username, currently_controlling_id, email, password)"
                "  VALUES (%s, %s, %s, %s) "
                " RETURNING id, created_time",
                (
                    account.username,
                    account.currently_controlling_id,
                    account.email,
                    account.password,
                )
            )
            # Populate a few things that we can only get once the DB has
            # created the row.
            account.id = result[0][0]
            account.created_time = result[0][1]
        else:
            yield self._db.runOperation(
                "UPDATE dott_accounts SET"
                "  username=%s,"
                "  currently_controlling_id=%s,"
                "  email=%s,"
                "  password=%s "
                " WHERE ID=%s",
                (
                    account.username,
                    account.currently_controlling_id,
                    account.email,
                    account.password,
                    account.id)
            )

        returnValue(account)

    @inlineCallbacks
    def destroy_account(self, account):
        """
        Destroys an account.

        :param PlayerAccount account: The account to save to delete in the DB.
        """

        yield self._db.runOperation(
            "DELETE FROM dott_accounts WHERE id=%s", (account.id,)
        )
